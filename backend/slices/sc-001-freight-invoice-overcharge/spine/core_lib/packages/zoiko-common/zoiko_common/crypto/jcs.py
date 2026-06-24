"""RFC 8785 JSON Canonicalization Scheme (JCS) implementation.

Produces deterministic UTF-8 bytes from any JSON-compatible Python value.
Key ordering: Unicode code point order (Python's default str sort).
Number serialization: ECMAScript Number.prototype.toString(10).
String serialization: UTF-8 literal except for mandatory escapes (§3.2.4).
"""
from __future__ import annotations

import math
from typing import Any

# RFC 8785 §3.2.4 mandatory single-character escape sequences
_ESCAPE_MAP: dict[int, str] = {
    0x08: "\\b",
    0x09: "\\t",
    0x0A: "\\n",
    0x0C: "\\f",
    0x0D: "\\r",
    0x22: '\\"',
    0x5C: "\\\\",
}


def _serialize_string(value: str) -> str:
    buf: list[str] = ['"']
    for ch in value:
        cp = ord(ch)
        if cp in _ESCAPE_MAP:
            buf.append(_ESCAPE_MAP[cp])
        elif cp < 0x20 or 0x7F <= cp <= 0x9F:
            # Control characters (C0, DEL, C1) → \uXXXX
            buf.append(f"\\u{cp:04x}")
        elif 0xD800 <= cp <= 0xDFFF:
            # Lone surrogate → \uXXXX
            buf.append(f"\\u{cp:04x}")
        else:
            buf.append(ch)
    buf.append('"')
    return "".join(buf)


def _serialize_number(value: int | float) -> str:
    if isinstance(value, int):
        return str(value)
    if math.isnan(value) or math.isinf(value):
        raise ValueError(f"JCS: non-finite number {value!r} is not valid JSON")
    if value == 0.0:
        return "0"
    # Integer-valued floats within IEEE 754 safe integer range → integer string
    if value == math.trunc(value) and abs(value) <= 9007199254740992:
        return str(int(value))
    # Python 3.12 repr gives shortest round-trip decimal, matching ES ToString(n)
    return repr(value)


def _serialize(value: Any) -> str:  # noqa: PLR0911
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return _serialize_number(value)
    if isinstance(value, str):
        return _serialize_string(value)
    if isinstance(value, list):
        return "[" + ",".join(_serialize(v) for v in value) + "]"
    if isinstance(value, dict):
        pairs = ",".join(
            f"{_serialize_string(k)}:{_serialize(v)}"
            for k, v in sorted(value.items())
        )
        return "{" + pairs + "}"
    raise TypeError(f"JCS: unsupported type {type(value).__name__!r}")


def canonicalize(data: Any) -> bytes:
    """Return RFC 8785 JCS canonical UTF-8 bytes for *data*.

    *data* must be a JSON-compatible Python value (dict, list, str, int,
    float, bool, None).  Raises TypeError for unsupported types and
    ValueError for non-finite numbers.
    """
    return _serialize(data).encode("utf-8")
