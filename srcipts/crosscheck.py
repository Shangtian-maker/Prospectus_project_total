from __future__ import annotations
from dataclasses import dataclass, asdict
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, Any, Iterable, List, Tuple
import pandas as pd

from .normalizer import (
    normalize_name_for_match, normalize_date, normalize_number, clean_text
)

SHEET_ALIASES = {
    "capital_increase": ["capital_increase", "认购增资", "增资", "历次增资"],
    "equity_transfer": ["equity_transfer", "股权转让", "股份转让"],
    "equity_snapshot": ["equity_snapshot", "股权快照", "股东快照", "股权结构"],
}

KEY_FIELDS = {
    "capital_increase": ("date", "subscriber"),
    "equity_transfer": ("date", "transferor", "transferee"),
    "equity_snapshot": ("date", "shareholder_name"),
}

FIELD_ALIASES = {
    "date": ["date", "日期", "时间"],
    "subscriber": ["subscriber", "认购人", "增资方", "股东名称"],
    "transferor": ["transferor", "转让方"],
    "transferee": ["transferee", "受让方"],
    "shareholder_name": ["shareholder_name", "股东名称", "股东"],
    "subscribed_amount": ["subscribed_amount", "认购金额", "认购股数", "新增出资"],
    "paid_amount": ["paid_amount", "实缴金额"],
    "price_per_share": ["price_per_share", "每股价格", "增资价格"],
    "registered_capital_before": ["registered_capital_before", "增资前注册资本"],
    "registered_capital_after": ["registered_capital_after", "增资后注册资本", "注册资本"],
    "shareholding_after": ["shareholding_after", "增资后持股比例"],
    "equity_percent": ["equity_percent", "转让比例", "股权比例"],
    "shares": ["shares", "股数", "转让股数"],
    "consideration": ["consideration", "转让价款", "对价"],
    "shareholding_percent": ["shareholding_percent", "持股比例"],
    "source_page": ["source_page", "来源页码", "页码"],
}

@dataclass
class CompareRow:
    table: str
    extracted_row: int | None
    gold_row: int | None
    match_score: float
    result: str
    field: str
    extracted_value: Any
    gold_value: Any
    message: str

    def to_dict(self):
        return asdict(self)

def _find_sheet(xls: pd.ExcelFile, table: str) -> str | None:
    normalized = {str(s).strip().lower(): s for s in xls.sheet_names}
    for alias in SHEET_ALIASES[table]:
        if alias.lower() in normalized:
            return normalized[alias.lower()]
    for sheet in xls.sheet_names:
        if any(alias in str(sheet) for alias in SHEET_ALIASES[table]):
            return sheet
    return None

def _rename_columns(df: pd.DataFrame) -> pd.DataFrame:
    mapping = {}
    for canonical, aliases in FIELD_ALIASES.items():
        for col in df.columns:
            if str(col).strip() in aliases:
                mapping[col] = canonical
                break
    return df.rename(columns=mapping)

def load_gold(path: Path) -> Dict[str, List[Dict[str, Any]]]:
    xls = pd.ExcelFile(path)
    result = {}
    for table in SHEET_ALIASES:
        sheet = _find_sheet(xls, table)
        if sheet is None:
            result[table] = []
            continue
        df = _rename_columns(pd.read_excel(path, sheet_name=sheet))
        result[table] = df.where(pd.notna(df), None).to_dict("records")
    return result

def _norm(field: str, value: Any) -> Any:
    if field == "date":
        return normalize_date(value)
    if field in {"subscriber", "transferor", "transferee", "shareholder_name"}:
        return normalize_name_for_match(value)
    if field in {
        "subscribed_amount", "paid_amount", "price_per_share",
        "registered_capital_before", "registered_capital_after",
        "shares", "consideration"
    }:
        return normalize_number(value)
    if field in {"shareholding_after", "equity_percent", "shareholding_percent"}:
        return normalize_number(value, percent=True)
    return clean_text(value)

def _record_similarity(table: str, left: Dict[str, Any], right: Dict[str, Any]) -> float:
    fields = KEY_FIELDS[table]
    scores = []
    for field in fields:
        a, b = _norm(field, left.get(field)), _norm(field, right.get(field))
        if a in (None, "") or b in (None, ""):
            continue
        if field == "date":
            scores.append(1.0 if a == b else 0.0)
        else:
            scores.append(SequenceMatcher(None, str(a), str(b)).ratio())
    return sum(scores) / len(scores) if scores else 0.0

def _numeric_equal(a: Any, b: Any, abs_tol: float = 1e-6, rel_tol: float = 0.01) -> bool:
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    try:
        a, b = float(a), float(b)
        return abs(a - b) <= max(abs_tol, rel_tol * max(abs(a), abs(b), 1.0))
    except Exception:
        return False

def compare(extracted: Dict[str, Any], gold: Dict[str, Any],
            match_threshold: float = 0.62) -> List[Dict[str, Any]]:
    results: List[CompareRow] = []
    for table in SHEET_ALIASES:
        ext_rows = extracted.get(table, [])
        gold_rows = gold.get(table, [])
        unused = set(range(len(gold_rows)))

        for ei, ext in enumerate(ext_rows, start=1):
            scored = sorted(
                ((gi, _record_similarity(table, ext, gold_rows[gi])) for gi in unused),
                key=lambda x: x[1], reverse=True
            )
            if not scored or scored[0][1] < match_threshold:
                results.append(CompareRow(
                    table, ei, None, scored[0][1] if scored else 0.0,
                    "UNMATCHED_EXTRACTED", "", "", "", "抽取记录未匹配到Gold"
                ))
                continue

            gi, score = scored[0]
            unused.remove(gi)
            gold_rec = gold_rows[gi]
            fields = sorted(set(ext) | set(gold_rec))
            for field in fields:
                if field in {"source_text", "confidence", "event_id", "snapshot_id"}:
                    continue
                a, b = _norm(field, ext.get(field)), _norm(field, gold_rec.get(field))
                if isinstance(a, (int, float)) or isinstance(b, (int, float)):
                    equal = _numeric_equal(a, b)
                else:
                    equal = a == b
                results.append(CompareRow(
                    table, ei, gi + 1, score,
                    "PASS" if equal else "DIFF",
                    field, ext.get(field), gold_rec.get(field),
                    "" if equal else "字段值不一致"
                ))

        for gi in sorted(unused):
            results.append(CompareRow(
                table, None, gi + 1, 0.0,
                "MISSING_EXTRACTED", "", "", "", "Gold记录未被抽取"
            ))
    return [r.to_dict() for r in results]
