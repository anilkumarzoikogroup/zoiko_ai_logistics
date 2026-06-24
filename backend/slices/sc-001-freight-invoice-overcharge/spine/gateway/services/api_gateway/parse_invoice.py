"""SC-001 — AI invoice-PDF parsing route logic, relocated from
backend/gateway/services/api_gateway/app.py.

parse_invoice_file() is pure processing (no FastAPI dependency injection);
the @v1_router route in app.py reads the uploaded file (the only genuinely
async-IO part) and calls this. extract_first_json() is a private helper
used only by this function.
"""
import json
import os


def _extract_first_json(text: str) -> dict:
    """Extract the outermost JSON object from text, handling nested braces correctly.
    The old regex r'\\{[^{}]*\\}' breaks when Groq wraps any value in a nested object;
    this walk finds the matching closing brace instead.
    """
    start = text.find("{")
    if start == -1:
        return {}
    depth = 0
    for i, ch in enumerate(text[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start : i + 1])
                except (json.JSONDecodeError, ValueError):
                    return {}
    return {}


async def parse_invoice_file(content: bytes, filename: str, content_type: str) -> dict:
    """Parse a PDF or image invoice using Groq AI (vision for images, text for PDFs). Fallback: regex.

    The blocking pdfplumber + Groq work runs in the thread-pool executor so
    the event loop stays free during AI extraction.
    """
    import re as _re2, base64 as _b64, io as _io


    # ── City / carrier reference tables ──────────────────────────────────────
    INDIAN_CITIES_SET = {
        "hyderabad", "warangal", "mumbai", "bombay", "delhi", "new delhi",
        "bangalore", "bengaluru", "chennai", "madras", "kolkata", "calcutta",
        "pune", "ahmedabad", "jaipur", "lucknow", "surat", "kochi", "cochin",
        "nagpur", "vizag", "visakhapatnam", "gurgaon", "gurugram", "noida",
        "chandigarh", "coimbatore", "indore", "bhopal", "patna", "vadodara",
        "ludhiana", "agra", "nashik", "thane", "rajkot", "amritsar", "varanasi",
        "bhubaneswar", "raipur", "dehradun", "guwahati", "srinagar", "jodhpur",
        "mysore", "mangalore", "hubli", "tirupati", "madurai", "trivandrum",
        "thiruvananthapuram",
    }

    # IATA → city name (airports commonly found on freight invoices)
    IATA_MAP = {
        "bom": "Mumbai", "del": "Delhi", "blr": "Bangalore", "maa": "Chennai",
        "ccu": "Kolkata", "hyd": "Hyderabad", "pnq": "Pune", "amd": "Ahmedabad",
        "cok": "Kochi", "jfk": "New York", "lax": "Los Angeles", "ord": "Chicago",
        "lhr": "London", "cdg": "Paris", "fra": "Frankfurt", "ams": "Amsterdam",
        "dxb": "Dubai", "auh": "Abu Dhabi", "sin": "Singapore", "hkg": "Hong Kong",
        "icn": "Seoul", "nrt": "Tokyo", "pvg": "Shanghai", "pek": "Beijing",
        "syd": "Sydney", "mel": "Melbourne", "jnb": "Johannesburg", "cai": "Cairo",
        "bkk": "Bangkok", "kul": "Kuala Lumpur", "cgk": "Jakarta",
    }

    CITY_ALIASES = {
        "bombay": "Mumbai", "new delhi": "Delhi", "bengaluru": "Bangalore",
        "calcutta": "Kolkata", "madras": "Chennai", "visakhapatnam": "Vizag",
        "cochin": "Kochi", "gurugram": "Gurgaon", "trivandrum": "Thiruvananthapuram",
        "hongkong": "Hong Kong", "hong kong sar": "Hong Kong",
        "uae": "Dubai", "united arab emirates": "Dubai",
    }

    def _normalize_city(raw: str) -> str:
        """Strip country suffix, expand IATA codes, normalize aliases, title-case."""
        # Strip country: "Mumbai, India" → "Mumbai"
        city = _re2.split(r",\s*|\s+\(", raw)[0].strip()
        city = _re2.sub(r"\s*\([^)]+\)", "", city).strip()
        key = city.lower().strip()
        if key in IATA_MAP:
            return IATA_MAP[key]
        if key in CITY_ALIASES:
            return CITY_ALIASES[key]
        # Match against known Indian cities (fuzzy prefix)
        for c in INDIAN_CITIES_SET:
            if c == key or key.startswith(c) or c.startswith(key):
                return c.title()
        return city.title()

    def _is_indian(city: str) -> bool:
        """Handles 'Mumbai', 'Mumbai, India', 'BOM', etc."""
        norm = _normalize_city(city).lower()
        return norm in INDIAN_CITIES_SET or norm in {v.lower() for v in IATA_MAP.values() if _is_in_india_iata(norm)}

    def _is_in_india_iata(city_lower: str) -> bool:
        indian_iata = {"bom","del","blr","maa","ccu","hyd","pnq","amd","cok"}
        for code, name in IATA_MAP.items():
            if code in indian_iata and name.lower() == city_lower:
                return True
        return False

    _KNOWN_CARRIERS = [
        "BlueDart", "Delhivery", "FedEx India", "FedEx", "DTDC",
        "Ekart", "UPS India", "UPS", "V Express", "Gati", "DHL",
        "Aramex", "Maersk", "MSC", "CMA CGM", "Other"
    ]

    # ── Detect file type ──────────────────────────────────────────────────────
    fname = (filename or "").lower()
    ctype = (content_type or "").lower()
    is_image = ctype.startswith("image/") or fname.endswith((".png", ".jpg", ".jpeg", ".webp"))

    text = ""
    image_b64 = ""
    image_mime = ""

    if is_image:
        image_mime = ctype if ctype.startswith("image/") else (
            "image/png" if fname.endswith(".png") else "image/jpeg"
        )
        image_b64 = _b64.b64encode(content).decode("utf-8")
    else:
        try:
            import pdfplumber
            with pdfplumber.open(_io.BytesIO(content)) as pdf:
                text = "\n".join(p.extract_text() or "" for p in pdf.pages)
        except Exception:
            text = content.decode("utf-8", errors="ignore")

    carrier, amount, currency, origin, dest, email = "", 0.0, "INR", "", "", ""
    invoice_number   = ""
    invoice_date     = ""
    transport_mode   = ""
    equipment_type   = ""
    shipper_reference = ""
    charge_lines: list = []
    ai_parsed = False
    groq_key  = os.getenv("GROQ_API_KEY", "")

    # ── Pre-extract grand total from PDF text (before AI runs) ───────────────
    # Regex against labelled final-amount fields is more reliable than AI for
    # distinguishing grand total from subtotal.  We lock this in early so AI
    # cannot override it with a subtotal value.
    def _find_grand_total(t: str) -> float:
        def _num(raw: str) -> float:
            try:
                v = float(raw.replace(",", ""))
                return v if v >= 100 else 0.0
            except ValueError:
                return 0.0

        # Tier 1 — definitive final-amount labels, cross-line with non-greedy match
        pat1 = (
            r"(?:grand\s+total|amount\s+due|balance\s+due|net\s+payable"
            r"|total\s+payable|total\s+due|invoice\s+total"
            r"|total\s+invoice\s+value|amount\s+payable|final\s+amount"
            r"|total\s+charges|net\s+amount\s+payable)"
            r"[\s\S]{0,80}?([\d,]+\.\d{2})"
        )
        hits = [v for v in (_num(m.group(1)) for m in _re2.finditer(pat1, t, _re2.IGNORECASE)) if v]
        if hits:
            return hits[-1]  # last = bottom of invoice = final total

        # Tier 2 — bare "Total" / "Total Amount" not on a subtotal line
        pat2 = r"(?:total\s+amount|net\s+total|total)[\s\S]{0,40}?([\d,]+\.\d{2})"
        for m in _re2.finditer(pat2, t, _re2.IGNORECASE):
            seg = t[max(0, m.start() - 10): m.start() + 25].lower()
            if "sub" not in seg:
                v = _num(m.group(1))
                if v:
                    return v
        return 0.0

    pdf_amount = _find_grand_total(text) if text else 0.0

    # ── Groq AI extraction ───────────────────────────────────────────────────
    if groq_key and (image_b64 or text.strip()):
        try:
            import asyncio as _asyncio
            from groq import Groq as _Groq
            _groq = _Groq(api_key=groq_key)

            extraction_prompt = (
                "You are an expert freight/logistics invoice parser. "
                "Carefully read the invoice and extract exactly these fields.\n\n"
                "Return ONLY a single valid JSON object — no markdown, no explanation:\n"
                "{\n"
                '  "invoice_number": "<the invoice/bill/reference number printed on the document — e.g. INV-2025-001, DHL-90881, BL-12345; empty string if not found>",\n'
                '  "invoice_date": "<invoice/bill date in YYYY-MM-DD format — e.g. 2025-06-01; empty string if not found>",\n'
                '  "carrier": "<logistics company name, e.g. BlueDart, DHL, FedEx, Maersk, UPS, Aramex — use exact name from invoice>",\n'
                '  "charge_lines": [<array of charge line objects — see charge_lines rules below>],\n'
                '  "total_amount": <see amount rules below>,\n'
                '  "currency": "<3-letter ISO code from invoice: INR, USD, EUR, GBP, AED, SGD, AUD, etc.>",\n'
                '  "origin": "<shipment ORIGIN city only — no country suffix, e.g. Mumbai, Dubai, New York, Singapore>",\n'
                '  "destination": "<shipment DESTINATION city only — no country suffix, e.g. Delhi, London, Chicago>",\n'
                '  "route_type": "<national if both cities are within India, international if any city is outside India>",\n'
                '  "transport_mode": "<exact one of: TRUCKLOAD | AIR | SEA | RAIL | COURIER — match from invoice service description; COURIER if overnight/express/docket; empty string if unclear>",\n'
                '  "equipment_type": "<physical asset type — e.g. 53FT_DRY_VAN, 40FT_CONTAINER, 20FT_CONTAINER, FLATBED, TANKER, PARCEL_VAN; empty string if not mentioned>",\n'
                '  "shipper_reference": "<shipper/consignor reference, PO number, or AWB/BL number — NOT the invoice number; e.g. PO-2025-456, AWB-12345; empty string if not found>",\n'
                '  "email": "<any email address visible on the invoice — billing, contact, support or sender email; empty string if none>"\n'
                "}\n\n"
                "AMOUNT RULES — follow this priority strictly:\n"
                "  Priority 1 (highest): Grand Total, Grand Total Amount\n"
                "  Priority 2: Amount Due, Balance Due, Payment Due, Total Due\n"
                "  Priority 3: Net Payable, Total Payable, Amount Payable\n"
                "  Priority 4: Invoice Total, Total Invoice Value, Total Charges\n"
                "  Priority 5: Total Amount — ONLY when NO subtotal or sub-total line exists anywhere\n\n"
                "  CRITICAL EXAMPLE — for this invoice structure:\n"
                "    Subtotal (before tax)   12,119.00\n"
                "    IGST 18%                 2,197.62\n"
                "    TOTAL PAYABLE           14,316.62   ← YOU MUST RETURN THIS\n"
                "  Return 14316.62, NOT 12119.00. The subtotal is NEVER the answer.\n\n"
                "  FORBIDDEN — NEVER return these values:\n"
                "  Subtotal, Sub-total, Sub Total, Basic Freight, Assessable Value,\n"
                "  Taxable Value, Net Amount (before tax), any per-line-item amounts,\n"
                "  unit prices, or any figure that appears BEFORE a tax/surcharge row.\n\n"
                "  The answer is always the LAST and LARGEST summary figure — the amount\n"
                "  the customer actually pays after ALL taxes, surcharges, and fees.\n"
                "  Return as a plain decimal number only, no symbols or commas, e.g. 14316.62\n\n"
                "LOCATION RULES:\n"
                "  1. origin/destination = FROM/TO shipment cities, NOT company/billing address.\n"
                "  2. Expand IATA codes: BOM→Mumbai, DEL→Delhi, JFK→New York, DXB→Dubai, LHR→London.\n"
                "  3. City name only — no state, country, or ZIP.\n"
                "  4. If not found, return empty string.\n\n"
                "CHARGE LINES RULES:\n"
                "  Extract EVERY individual line item from the invoice into charge_lines array.\n"
                "  Each element must be: {\"description\": \"<line label>\", \"amount\": <number>, \"type\": \"<type>\"}\n"
                "  type must be exactly one of: BASE | FUEL | ACCESSORIAL | TAX | DISCOUNT | OTHER\n"
                "  Rules for type classification:\n"
                "    BASE        — Basic freight, base rate, freight charge, standard charge\n"
                "    FUEL        — Fuel surcharge, FSC, fuel levy, energy surcharge\n"
                "    ACCESSORIAL — Handling, accessorial, pickup, delivery, detention, demurrage, insurance, COD\n"
                "    TAX         — GST, IGST, CGST, SGST, VAT, tax, cess\n"
                "    DISCOUNT    — Discount, rebate, credit\n"
                "    OTHER       — Anything that does not fit above categories\n"
                "  IMPORTANT: do NOT include the grand total / total payable as a charge line.\n"
                "  If no line items are visible, return an empty array []."
            )

            if image_b64:
                # Try vision models in order of preference
                vision_models = [
                    os.getenv("GROQ_VISION_MODEL", ""),
                    "meta-llama/llama-4-scout-17b-16e-instruct",
                    "llama-3.2-90b-vision-preview",
                    "llama-3.2-11b-vision-preview",
                ]
                vision_models = [m for m in vision_models if m]  # drop empty
                chat = None
                for vm in vision_models:
                    try:
                        chat = _groq.chat.completions.create(
                            model=vm,
                            messages=[{
                                "role": "user",
                                "content": [
                                    {"type": "image_url", "image_url": {"url": f"data:{image_mime};base64,{image_b64}"}},
                                    {"type": "text", "text": extraction_prompt},
                                ],
                            }],
                            temperature=0,
                            max_tokens=900,
                        )
                        break
                    except Exception:
                        continue
                if chat is None:
                    raise RuntimeError("All vision models failed")
            else:
                text_model = os.getenv("GROQ_TEXT_MODEL", "llama-3.3-70b-versatile")
                _msg = [{"role": "user", "content": f"INVOICE TEXT:\n{text[:4000]}\n\n{extraction_prompt}"}]
                try:
                    # Run synchronous Groq SDK in thread pool so event loop stays free
                    chat = await _asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: _groq.chat.completions.create(
                            model=text_model, messages=_msg, temperature=0, max_tokens=900,
                        ),
                    )
                except Exception:
                    chat = await _asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: _groq.chat.completions.create(
                            model="llama-3.1-8b-instant", messages=_msg, temperature=0, max_tokens=900,
                        ),
                    )

            raw = chat.choices[0].message.content.strip()
            # Use the brace-counting extractor — the old r'\{[^{}]*\}' regex
            # matched the first INNERMOST object, failing whenever Groq nested
            # any value (e.g. "details": {"total": 123}) and returning {} instead.
            parsed    = _extract_first_json(raw)
            invoice_number    = str(parsed.get("invoice_number", "")).strip()
            invoice_date      = str(parsed.get("invoice_date", "")).strip()
            _valid_modes      = {"TRUCKLOAD","AIR","SEA","RAIL","COURIER"}
            _raw_mode         = str(parsed.get("transport_mode", "")).strip().upper()
            transport_mode    = _raw_mode if _raw_mode in _valid_modes else ""
            equipment_type    = str(parsed.get("equipment_type", "")).strip().upper()
            shipper_reference = str(parsed.get("shipper_reference", "")).strip()
            carrier   = str(parsed.get("carrier", "")).strip()
            # Parse and validate charge_lines array
            _raw_lines = parsed.get("charge_lines", [])
            if isinstance(_raw_lines, list):
                _valid_types = {"BASE", "FUEL", "ACCESSORIAL", "TAX", "DISCOUNT", "OTHER"}
                charge_lines = [
                    {
                        "description": str(cl.get("description", "")).strip(),
                        "amount":      float(cl.get("amount", 0) or 0),
                        "type":        cl.get("type", "OTHER").upper()
                                       if cl.get("type", "OTHER").upper() in _valid_types
                                       else "OTHER",
                    }
                    for cl in _raw_lines
                    if isinstance(cl, dict) and float(cl.get("amount", 0) or 0) > 0
                ]
            ai_amount = float(parsed.get("total_amount", 0) or 0)
            _cur_raw  = str(parsed.get("currency", "INR")).strip()
            _sym_map  = {"₹": "INR", "$": "USD", "€": "EUR", "£": "GBP", "¥": "JPY"}
            currency  = _sym_map.get(_cur_raw, _cur_raw.upper()) or "INR"
            origin    = _normalize_city(str(parsed.get("origin", "")).strip())
            dest      = _normalize_city(str(parsed.get("destination", "")).strip())
            if origin == dest:
                dest = ""
            email     = str(parsed.get("email", "")).strip().lower()
            # PDF amount from regex always wins; use AI amount only for images
            amount    = pdf_amount if pdf_amount else ai_amount
            ai_parsed = bool(origin or dest or carrier or amount)
        except Exception:
            ai_parsed = False

    # ── Regex fallback (PDF / text only) ─────────────────────────────────────
    if not ai_parsed and text:
        text_lower = text.lower()

        CARRIER_ALIASES = {
            "bluedart": "BlueDart", "blue dart": "BlueDart",
            "delhivery": "Delhivery",
            "fedex india": "FedEx India", "fedex": "FedEx",
            "dtdc": "DTDC", "ekart": "Ekart", "gati": "Gati",
            "ups india": "UPS India", "ups": "UPS",
            "v express": "V Express", "vexpress": "V Express",
            "dhl": "DHL", "aramex": "Aramex",
            "maersk": "Maersk", "msc ": "MSC", "cma cgm": "CMA CGM",
        }
        for alias, canonical in CARRIER_ALIASES.items():
            if alias in text_lower:
                carrier = canonical
                break

        # Use the pre-extracted PDF amount if already found
        if pdf_amount:
            amount = pdf_amount

        def _parse_num(raw: str) -> float:
            try:
                v = float(raw.replace(",", ""))
                return v if v >= 100 else 0.0
            except ValueError:
                return 0.0

        def _tier1_amounts(text: str) -> list[float]:
            """Find all definitive final-amount labels, allowing multi-line gaps."""
            pat = (
                r"(?:grand\s+total|amount\s+due|balance\s+due|net\s+payable"
                r"|total\s+payable|total\s+due|invoice\s+total"
                r"|total\s+invoice\s+value|amount\s+payable|final\s+amount"
                r"|total\s+charges|net\s+amount\s+payable)"
                r"[\s\S]{0,80}?"           # cross newlines, non-greedy
                r"([\d,]+\.\d{2})"         # require decimal — final amounts always have paise/cents
            )
            return [v for v in (_parse_num(m.group(1)) for m in _re2.finditer(pat, text, _re2.IGNORECASE)) if v]

        # Tier 1 — definitive labels; take the last match (totals are at the bottom)
        # Skip if pdf_amount already resolved above
        tier1 = [] if amount else _tier1_amounts(text)
        if tier1:
            amount = tier1[-1]

        # Tier 2 — bare "Total" or "Total Amount" but never on a subtotal line
        if not amount:
            tier2 = []
            pat2 = (
                r"(?:total\s+amount|net\s+total|total)"
                r"[\s\S]{0,40}?([\d,]+\.\d{2})"
            )
            for m in _re2.finditer(pat2, text, _re2.IGNORECASE):
                # Reject if "sub" appears on the same logical line as the label
                seg = text[max(0, m.start() - 10): m.start() + 30].lower()
                if "sub" not in seg:
                    v = _parse_num(m.group(1))
                    if v:
                        tier2.append(v)
            if tier2:
                amount = tier2[-1]

        # Tier 3 — currency-symbol / currency-code; take max (last resort)
        if not amount:
            for pat in [
                r"[₹$€£]\s*([\d,]+(?:\.\d{1,2})?)",
                r"([\d,]+(?:\.\d{2}))\s*(?:INR|USD|EUR|GBP|AED|SGD)",
            ]:
                candidates = [v for v in (_parse_num(m.group(1)) for m in _re2.finditer(pat, text, _re2.IGNORECASE)) if v]
                if candidates:
                    amount = max(candidates)
                    break

        if "usd" in text_lower or "$ " in text:
            currency = "USD"
        elif "eur" in text_lower or "€" in text:
            currency = "EUR"
        elif "gbp" in text_lower or "£" in text:
            currency = "GBP"
        elif "aed" in text_lower:
            currency = "AED"

        # Email regex fallback
        if not email:
            email_match = _re2.search(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}', text)
            if email_match:
                email = email_match.group(0).lower()

        for pat in [
            r"(?:from|origin|shipper['\s]?city|pickup\s*(?:city|location))[:\s]+([A-Za-z][a-zA-Z .'-]{2,30}?)\s{0,3}(?:to|dest(?:ination)?|consignee['\s]?city|delivery\s*(?:city|location))[:\s]+([A-Za-z][a-zA-Z .'-]{2,30})(?:\s*\n|,|\.|$)",
            r"\b([A-Z][a-z]{2,}(?:[\s][A-Z][a-z]+)?)\s*(?:[-–→]|to)\s*([A-Z][a-z]{2,}(?:[\s][A-Z][a-z]+)?)\b",
        ]:
            m = _re2.search(pat, text, _re2.IGNORECASE)
            if m:
                c1 = _normalize_city(m.group(1))
                c2 = _normalize_city(m.group(2))
                if c1 and c2 and c1.lower() != c2.lower():
                    origin, dest = c1, c2
                break

        # Last resort: extract from filename  (e.g. bluedart_mumbai_delhi.pdf)
        if not origin:
            name_parts = _re2.split(r"[_\-\s]+", fname.replace(".pdf","").replace(".png","").replace(".jpg",""))
            found = []
            for part in name_parts:
                norm = _normalize_city(part)
                if norm and len(norm) > 2:
                    # Check if it looks like a city (known or at least title-cased word)
                    if norm.lower() in INDIAN_CITIES_SET or norm.lower() in IATA_MAP:
                        found.append(norm)
            if len(found) >= 2:
                origin, dest = found[0], found[1]

    # ── Equipment type fallback — keyword scan ────────────────────────────────────
    if not equipment_type and text:
        _tl = text.lower()
        if any(k in _tl for k in ("53ft","53-ft","dry van","dryvan")): equipment_type = "53FT_DRY_VAN"
        elif any(k in _tl for k in ("40ft container","40-ft","40ft hc")): equipment_type = "40FT_CONTAINER"
        elif any(k in _tl for k in ("20ft","20-ft","20ft container")): equipment_type = "20FT_CONTAINER"
        elif "flatbed" in _tl: equipment_type = "FLATBED"
        elif "tanker" in _tl: equipment_type = "TANKER"
        elif any(k in _tl for k in ("parcel","courier van","two-wheeler","bike")): equipment_type = "PARCEL_VAN"

    # ── Shipper reference fallback — look for PO / AWB / BL / Docket ─────────────
    if not shipper_reference and text:
        _ref_pat = (
            r"(?:po\s*(?:no|number|#)?|purchase\s*order|awb|airway\s*bill"
            r"|b/?l\s*(?:no)?|docket\s*(?:no)?|shipment\s*ref(?:erence)?)"
            r"[\s:.\-]*([A-Z0-9][-A-Z0-9/]{3,30})"
        )
        _rm = _re2.search(_ref_pat, text, _re2.IGNORECASE)
        if _rm:
            shipper_reference = _rm.group(1).strip()

    # ── Transport mode fallback — keyword scan ────────────────────────────────────
    if not transport_mode and text:
        _tl = text.lower()
        if any(k in _tl for k in ("truckload","truck load","dry van","ftl","ltl","road","surface")):
            transport_mode = "TRUCKLOAD"
        elif any(k in _tl for k in ("air freight","airfreight","air cargo","air express","flight")):
            transport_mode = "AIR"
        elif any(k in _tl for k in ("sea freight","ocean","vessel","lcl","fcl","sea cargo")):
            transport_mode = "SEA"
        elif any(k in _tl for k in ("rail","train","railway")):
            transport_mode = "RAIL"
        elif any(k in _tl for k in ("courier","express","docket","overnight","next day")):
            transport_mode = "COURIER"

    # ── Charge lines fallback — regex when AI missed them ────────────────────────
    if not charge_lines and text:
        def _classify_charge(desc: str) -> str:
            dl = desc.lower()
            if any(k in dl for k in ("fuel", "fsc", "energy surcharge")): return "FUEL"
            if any(k in dl for k in ("basic freight", "base freight", "freight charge", "base rate")): return "BASE"
            if any(k in dl for k in ("gst", "igst", "cgst", "sgst", "vat", "tax", "cess")): return "TAX"
            if any(k in dl for k in ("handling", "accessorial", "pickup", "delivery", "detention",
                                     "demurrage", "insurance", "cod", "docket")): return "ACCESSORIAL"
            if any(k in dl for k in ("discount", "rebate", "credit")): return "DISCOUNT"
            return "OTHER"

        _line_pat = _re2.compile(
            r"^[ \t]*(.{4,50}?)[ \t]{2,}([\d,]+\.?\d{0,2})[ \t]*$",
            _re2.MULTILINE
        )
        _skip = {"total", "subtotal", "sub-total", "grand total", "amount due",
                 "total payable", "net payable", "balance due"}
        for _m in _line_pat.finditer(text):
            _desc = _m.group(1).strip()
            if any(s in _desc.lower() for s in _skip):
                continue
            try:
                _amt = float(_m.group(2).replace(",", ""))
            except ValueError:
                continue
            if _amt > 0:
                charge_lines.append({
                    "description": _desc,
                    "amount":      _amt,
                    "type":        _classify_charge(_desc),
                })

    # ── Invoice date fallback — regex when AI missed it ──────────────────────────
    if not invoice_date and text:
        # Matches formats: 01-Jun-2025, 01/06/2025, 2025-06-01, June 1 2025, 1 Jun 25
        _date_pat = (
            r"(?:invoice\s*date|bill\s*date|date\s*of\s*issue|date)[:\s]+?"
            r"(\d{1,2}[-/\s]\w+[-/\s]\d{2,4}|\d{4}[-/]\d{2}[-/]\d{2}|\w+\s+\d{1,2},?\s+\d{4})"
        )
        _dm = _re2.search(_date_pat, text, _re2.IGNORECASE)
        if _dm:
            _raw_date = _dm.group(1).strip()
            # Normalise to YYYY-MM-DD
            import datetime as _dt
            for _fmt in ("%d-%b-%Y", "%d/%m/%Y", "%Y-%m-%d", "%B %d %Y", "%d %b %Y", "%b %d %Y"):
                try:
                    invoice_date = _dt.datetime.strptime(_raw_date, _fmt).strftime("%Y-%m-%d")
                    break
                except ValueError:
                    continue

    # ── Invoice number fallback — regex when AI missed it ────────────────────────
    if not invoice_number and text:
        _inv_pat = (
            r"(?:invoice\s*(?:no|number|#|num)|bill\s*(?:no|number|#)|ref(?:erence)?\s*(?:no|#|:))"
            r"[\s:.\-]*([A-Z0-9][-A-Z0-9/]{3,30})"
        )
        _m = _re2.search(_inv_pat, text, _re2.IGNORECASE)
        if _m:
            invoice_number = _m.group(1).strip()

    # ── Carrier fallback: extract from filename when AI/regex found nothing ─────
    # e.g. "DHL_Invoice_with_Excel.pdf" → "DHL"
    if not carrier and fname:
        _FNAME_CARRIERS = {
            "bluedart": "BlueDart", "blue_dart": "BlueDart",
            "delhivery": "Delhivery", "fedex": "FedEx", "dtdc": "DTDC",
            "ekart": "Ekart", "gati": "Gati", "ups": "UPS",
            "vexpress": "V Express", "v_express": "V Express",
            "dhl": "DHL", "aramex": "Aramex",
            "maersk": "Maersk", "msc": "MSC", "cmacgm": "CMA CGM",
        }
        fname_lower = fname.lower()
        for key, canonical in _FNAME_CARRIERS.items():
            if key in fname_lower:
                carrier = canonical
                break

    # ── Email fallback: scan full text if AI missed it ────────────────────────
    if not email and text:
        em = _re2.search(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}', text)
        if em:
            email = em.group(0).lower()

    # ── Determine route type ──────────────────────────────────────────────────
    if origin and dest:
        both_indian = _is_indian(origin) and _is_indian(dest)
        route_type = "national" if both_indian else "international"
    elif origin or dest:
        single = origin or dest
        route_type = "national" if _is_indian(single) else "international"
    else:
        route_type = "unknown"

    route = f"{origin}-{dest}" if (origin and dest) else (origin or dest)

    return {
        "invoice_number":   invoice_number,
        "invoice_date":     invoice_date,
        "charge_lines":      charge_lines,
        "transport_mode":    transport_mode,
        "equipment_type":    equipment_type,
        "shipper_reference": shipper_reference,
        "carrier":           carrier,
        "route":            route,
        "origin":           origin,
        "destination":      dest,
        "amount":           amount,
        "currency":         currency,
        "route_type":       route_type,
        "email":            email,
        "parsed_by":        "groq_ai" if ai_parsed else "regex",
        "raw_text_preview": text[:300] if text else "",
    }
