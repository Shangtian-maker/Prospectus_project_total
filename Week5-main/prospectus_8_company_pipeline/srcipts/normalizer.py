from __future__ import annotations
from datetime import datetime
from decimal import Decimal, InvalidOperation
from dateutil import parser as date_parser
import re
from typing import Any, Dict, Iterable, Optional

FULLWIDTH_MAP = str.maketrans(
    "０１２３４５６７８９％，．（）",
    "0123456789%,.()"
)

COMPANY_SUFFIXES = (
    "股份有限公司", "有限责任公司", "有限公司", "股份公司", "公司"
)

def clean_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).translate(FULLWIDTH_MAP)
    text = re.sub(r"\s+", "", text)
    return text or None

def normalize_name(value: Any, aliases: Dict[str, str] | None = None) -> Optional[str]:
    text = clean_text(value)
    if not text:
        return None
    text = re.sub(r"[（(].*?[）)]", "", text)
    if aliases and text in aliases:
        text = aliases[text]
    return text

def normalize_name_for_match(value: Any, aliases: Dict[str, str] | None = None) -> str:
    text = normalize_name(value, aliases) or ""
    for suffix in COMPANY_SUFFIXES:
        if text.endswith(suffix):
            text = text[:-len(suffix)]
            break
    return re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]", "", text).lower()

def normalize_date(value: Any) -> Optional[str]:
    text = clean_text(value)
    if not text:
        return None
    text = text.replace("年", "-").replace("月", "-").replace("日", "")
    text = text.replace(".", "-").replace("/", "-")
    try:
        dt = date_parser.parse(text, fuzzy=True, dayfirst=False)
        return dt.strftime("%Y-%m-%d")
    except Exception:
        year_month = re.search(r"((?:19|20)\d{2})[-](\d{1,2})$", text)
        if year_month:
            return f"{int(year_month.group(1)):04d}-{int(year_month.group(2)):02d}"
        return text

def normalize_number(value: Any, percent: bool = False) -> Optional[float]:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return number * 100 if percent and 0 <= number <= 1 else number

    text = clean_text(value)
    if not text:
        return None
    text = text.replace(",", "")
    multiplier = Decimal("1")
    if "亿元" in text:
        multiplier = Decimal("100000000")
    elif "万元" in text:
        multiplier = Decimal("10000")
    elif "千元" in text:
        multiplier = Decimal("1000")
    elif "万股" in text:
        multiplier = Decimal("10000")
    elif "亿股" in text:
        multiplier = Decimal("100000000")

    is_percent = "%" in text or "百分之" in text
    m = re.search(r"-?\d+(?:\.\d+)?", text)
    if not m:
        return None
    try:
        number = Decimal(m.group()) * multiplier
    except InvalidOperation:
        return None
    result = float(number)
    if percent and not is_percent and 0 <= result <= 1:
        result *= 100
    return result

def aliases_to_map(company: Dict[str, Any]) -> Dict[str, str]:
    canonical = company.get("company_name", "")
    mapping = {canonical: canonical}
    for alias in company.get("aliases", []) or []:
        mapping[str(alias)] = canonical
    return mapping

def normalize_record(record: Dict[str, Any], record_type: str,
                     aliases: Dict[str, str] | None = None) -> Dict[str, Any]:
    out = dict(record)
    for field in ("date",):
        if field in out:
            out[field] = normalize_date(out[field])

    name_fields = {
        "capital_increase": ("subscriber",),
        "equity_transfer": ("transferor", "transferee"),
        "equity_snapshot": ("shareholder_name",),
    }.get(record_type, ())
    for field in name_fields:
        if field in out:
            out[field] = normalize_name(out[field], aliases)

    percent_fields = ("shareholding_after", "equity_percent", "shareholding_percent")
    number_fields = (
        "subscribed_amount", "paid_amount", "price_per_share",
        "registered_capital_before", "registered_capital_after",
        "shares", "consideration", "confidence"
    )
    for field in percent_fields:
        if field in out:
            out[field] = normalize_number(out[field], percent=True)
    for field in number_fields:
        if field in out:
            out[field] = normalize_number(out[field], percent=False)

    if out.get("source_page") not in (None, ""):
        try:
            out["source_page"] = int(float(out["source_page"]))
        except (TypeError, ValueError):
            out["source_page"] = None
    return out

def deduplicate(records: Iterable[Dict[str, Any]], key_fields: tuple[str, ...]) -> list[Dict[str, Any]]:
    seen = set()
    result = []
    for rec in records:
        key = tuple(rec.get(k) for k in key_fields)
        if key in seen:
            continue
        seen.add(key)
        result.append(rec)
    return result
