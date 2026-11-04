"""Reading euro amounts the way people write them: 1.240 / 1,240 / 1.240,50 / 1,240.50 / 1240.5 / € 1.240,-

One reader for the whole brain. Getting this wrong is expensive: "EUR 1.240" read as 1.24 makes an invoice look right
when it is not, and lets an invented price through the price check."""
from __future__ import annotations

import re

AMOUNT = re.compile(r"(?:€|\beur(?:o|os)?\b)\s?(\d[\d.,]*\d|\d)(?:,-)?|(\d[\d.,]*\d|\d)(?:,-)?\s?(?:€|\beur(?:o|os)?\b)", re.I)


def parse_amount(raw: str) -> float | None:
    s = raw.strip().rstrip(".,-")
    if not s or not re.fullmatch(r"\d[\d.,]*", s):
        return None
    if "." in s and "," in s:  # both: the last one is the decimal mark
        dec = "." if s.rfind(".") > s.rfind(",") else ","
        thou = "," if dec == "." else "."
        s = s.replace(thou, "").replace(dec, ".")
    elif "." in s or "," in s:
        sep = "." if "." in s else ","
        parts = s.split(sep)
        if len(parts) > 2 or (len(parts[-1]) == 3 and len(parts[0]) <= 3):
            s = s.replace(sep, "")  # 1.240 or 1,240 or 12.500.000: thousands
        else:
            s = s.replace(sep, ".")  # 1240,5 or 99.95: decimals
    try:
        return float(s)
    except ValueError:
        return None


def amounts(text: str) -> list[float]:
    out = []
    for m in AMOUNT.finditer(text or ""):
        v = parse_amount(m.group(1) or m.group(2))
        if v is not None:
            out.append(v)
    return out
