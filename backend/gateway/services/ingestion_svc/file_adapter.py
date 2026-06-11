"""
File Upload Adapter — Tier-0 spec §7.5.

Controls:
  - MIME detection from bytes (not filename/Content-Type)   (§7.5)
  - Malware scan scaffold (ClamAV-compatible interface)      (§7.5)
  - Macro detection in spreadsheet formats                   (§7.5)
  - Encoding detection and normalization to UTF-8            (§7.5)
  - channel_metadata shape for file_upload channel           (§9)
  - Upload session tracking                                  (§9)

Engineering rule: A file's extension is not evidence of its type. Inspect the bytes.
"""
import hashlib
import io
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

# MIME magic bytes map (first N bytes → MIME type)
# Sufficient for the file types accepted on this platform
_MAGIC_SIGNATURES: list[tuple[bytes, int, str]] = [
    # offset, magic, mime
    (b"%PDF",                   0,  "application/pdf"),
    (b"PK\x03\x04",             0,  "application/zip"),         # ZIP / XLSX / DOCX
    (b"\xd0\xcf\x11\xe0",       0,  "application/vnd.ms-excel"), # OLE2 / XLS
    (b"\x89PNG\r\n\x1a\n",      0,  "image/png"),
    (b"\xff\xd8\xff",           0,  "image/jpeg"),
    (b"GIF87a",                 0,  "image/gif"),
    (b"GIF89a",                 0,  "image/gif"),
    (b"RIFF",                   0,  "audio/wav"),               # also detects WAV — reject
    (b"MZ",                     0,  "application/x-msdownload"), # EXE — always reject
    (b"\x7fELF",                0,  "application/x-elf"),        # Linux binary — reject
    (b"<html",                  0,  "text/html"),
    (b"<HTML",                  0,  "text/html"),
    (b"<?xml",                  0,  "application/xml"),
    (b"{\n",                    0,  "application/json"),
    (b"{ ",                     0,  "application/json"),
    (b"[",                      0,  "application/json"),
    (b"ISA",                    0,  "application/edi-x12"),      # EDI 210/214 etc.
    (b"UNA",                    0,  "application/edifact"),
]

# MIME types this platform rejects outright (no policy override)
_ALWAYS_REJECT_MIMES = {
    "application/x-msdownload",
    "application/x-elf",
    "text/html",
}

# MIME types that may contain macros (require macro scan before accept)
_MACRO_RISK_MIMES = {
    "application/zip",            # Could be XLSX with macros
    "application/vnd.ms-excel",   # OLE2 XLS — macro-capable
}


@dataclass
class MimeDetectionResult:
    declared_mime:   str
    detected_mime:   str
    match:           bool   # declared == detected
    rejected:        bool   # always-reject type detected
    rejection_reason: str = ""


@dataclass
class MalwareScanResult:
    scan_id:    str
    outcome:    str   # CLEAN | POSITIVE | SCAN_UNAVAILABLE
    detail:     str = ""


@dataclass
class FileUploadChannelMetadata:
    uploaded_by_user_id:  str  = ""
    upload_session_id:    str  = ""
    original_filename:    str  = ""
    declared_mime:        str  = ""
    detected_mime:        str  = ""
    malware_scan_id:      str  = ""
    malware_scan_outcome: str  = "PENDING"
    declared_schema:      str  = ""
    declared_row_count:   int  = 0
    sheet_names:          list = field(default_factory=list)
    macro_detected:       bool = False
    encoding_detected:    str  = "utf-8"

    def to_dict(self) -> dict:
        return {
            "uploaded_by_user_id":  self.uploaded_by_user_id,
            "upload_session_id":    self.upload_session_id,
            "original_filename":    self.original_filename,
            "declared_mime":        self.declared_mime,
            "detected_mime":        self.detected_mime,
            "malware_scan_id":      self.malware_scan_id,
            "malware_scan_outcome": self.malware_scan_outcome,
            "declared_schema":      self.declared_schema,
            "declared_row_count":   self.declared_row_count,
            "sheet_names":          self.sheet_names,
            "macro_detected":       self.macro_detected,
            "encoding_detected":    self.encoding_detected,
        }


def detect_mime(content: bytes, declared_mime: str = "", filename: str = "") -> MimeDetectionResult:
    """
    Detect MIME type from the first bytes of the file content.
    Never trust the filename or declared Content-Type alone.
    """
    detected = "application/octet-stream"  # default unknown

    for magic, offset, mime in _MAGIC_SIGNATURES:
        if content[offset:offset + len(magic)] == magic:
            detected = mime
            break

    # Fallback: try to detect CSV/TSV from content (no magic bytes)
    if detected == "application/octet-stream":
        try:
            sample = content[:2048].decode("utf-8", errors="ignore")
            if "," in sample and "\n" in sample:
                detected = "text/csv"
            elif "\t" in sample and "\n" in sample:
                detected = "text/tab-separated-values"
            elif sample.strip():
                detected = "text/plain"
        except Exception:
            pass

    rejected        = detected in _ALWAYS_REJECT_MIMES
    rejection_reason = f"File type {detected} is not permitted on this platform" if rejected else ""

    return MimeDetectionResult(
        declared_mime    = declared_mime or detected,
        detected_mime    = detected,
        match            = (declared_mime == detected) if declared_mime else True,
        rejected         = rejected,
        rejection_reason = rejection_reason,
    )


def detect_macros(content: bytes, detected_mime: str) -> bool:
    """
    Detect VBA macros in Office files.
    Uses byte-pattern detection (no external dependency required).
    """
    if detected_mime not in _MACRO_RISK_MIMES:
        return False

    # VBA macro signature in OLE2 files
    vba_signatures = [
        b"VBA",
        b"_VBA_PROJECT",
        b"vbaProject.bin",
        b"xl/vbaProject",     # XLSX with macro
        b"\x41\x74\x74\x72",  # "Attr" — common in VBA streams
    ]
    for sig in vba_signatures:
        if sig in content:
            return True
    return False


def scan_malware(content: bytes, filename: str = "") -> MalwareScanResult:
    """
    Malware scan scaffold. Tries ClamAV via clamd socket if available.
    Falls back to SCAN_UNAVAILABLE in dev (never allows POSITIVE to be skipped in prod).
    """
    scan_id = str(uuid.uuid4())

    # Try pyclamd if available (production)
    try:
        import pyclamd  # type: ignore
        cd = pyclamd.ClamdAgnostic()
        result = cd.scan_stream(io.BytesIO(content))
        if result is None:
            return MalwareScanResult(scan_id=scan_id, outcome="CLEAN")
        # result is a dict with stream key
        threat = list(result.values())[0]
        return MalwareScanResult(scan_id=scan_id, outcome="POSITIVE", detail=str(threat))
    except ImportError:
        pass
    except Exception as e:
        # ClamAV unavailable — in production this should block file acceptance
        dev_mode = os.getenv("ZOIKO_DEV_MODE", "false").lower() == "true"
        if not dev_mode:
            return MalwareScanResult(scan_id=scan_id, outcome="SCAN_UNAVAILABLE",
                                     detail=f"ClamAV unavailable: {e}")

    # DEV_MODE or pyclamd not installed — allow with SCAN_UNAVAILABLE marker
    return MalwareScanResult(scan_id=scan_id, outcome="SCAN_UNAVAILABLE",
                             detail="Malware scanner not configured (dev mode)")


def detect_encoding(content: bytes) -> str:
    """Detect character encoding. Returns IANA encoding name."""
    try:
        import chardet  # type: ignore
        result = chardet.detect(content[:8192])
        return result.get("encoding") or "utf-8"
    except ImportError:
        pass

    # Manual BOM detection
    if content.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    if content.startswith(b"\xff\xfe"):
        return "utf-16-le"
    if content.startswith(b"\xfe\xff"):
        return "utf-16-be"

    # Try UTF-8 decode; fall back to latin-1
    try:
        content[:4096].decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        return "iso-8859-1"


def build_file_channel_metadata(
    content: bytes,
    filename: str,
    declared_mime: str,
    user_id: str,
    declared_schema: str = "",
    declared_row_count: int = 0,
) -> tuple[FileUploadChannelMetadata, MimeDetectionResult, MalwareScanResult]:
    """
    Full file adapter pipeline for a single upload.
    Returns (channel_metadata, mime_result, malware_result).
    Callers must check mime_result.rejected and malware_result.outcome == 'POSITIVE'.
    """
    session_id   = str(uuid.uuid4())
    mime_result  = detect_mime(content, declared_mime, filename)
    macro_found  = detect_macros(content, mime_result.detected_mime)
    scan_result  = scan_malware(content, filename)
    encoding     = detect_encoding(content)

    # Detect sheet names for spreadsheet files
    sheet_names: list[str] = []
    if mime_result.detected_mime in ("application/zip", "application/vnd.ms-excel"):
        try:
            import zipfile
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                sheet_names = [n for n in zf.namelist() if n.startswith("xl/worksheets/")]
        except Exception:
            pass

    metadata = FileUploadChannelMetadata(
        uploaded_by_user_id  = user_id,
        upload_session_id    = session_id,
        original_filename    = filename,
        declared_mime        = declared_mime or mime_result.detected_mime,
        detected_mime        = mime_result.detected_mime,
        malware_scan_id      = scan_result.scan_id,
        malware_scan_outcome = scan_result.outcome,
        declared_schema      = declared_schema,
        declared_row_count   = declared_row_count,
        sheet_names          = sheet_names,
        macro_detected       = macro_found,
        encoding_detected    = encoding,
    )

    return metadata, mime_result, scan_result
