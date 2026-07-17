from __future__ import annotations
from collections import defaultdict
from datetime import datetime
from typing import Dict, Any, List
from jsonschema import Draft202012Validator

def schema_validate(data: Dict[str, Any], schema: Dict[str, Any]) -> List[Dict[str, Any]]:
    validator = Draft202012Validator(schema)
    issues = []
    for error in sorted(validator.iter_errors(data), key=lambda e: list(e.path)):
        issues.append({
            "level": "ERROR",
            "rule": "SCHEMA",
            "path": ".".join(map(str, error.path)),
            "message": error.message
        })
    return issues

def _issue(level, rule, table, row, field, message, value=None):
    return {
        "level": level, "rule": rule, "table": table, "row": row,
        "field": field, "message": message, "value": value
    }

def business_validate(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []

    for table, records in (
        ("capital_increase", data.get("capital_increase", [])),
        ("equity_transfer", data.get("equity_transfer", [])),
        ("equity_snapshot", data.get("equity_snapshot", [])),
    ):
        for idx, rec in enumerate(records, start=1):
            page = rec.get("source_page")
            if page in (None, ""):
                issues.append(_issue("ERROR", "SOURCE_PAGE_REQUIRED", table, idx,
                                     "source_page", "缺少来源页码"))
            if not rec.get("source_text"):
                issues.append(_issue("WARN", "SOURCE_TEXT_REQUIRED", table, idx,
                                     "source_text", "缺少来源原文"))
            confidence = rec.get("confidence")
            if confidence is not None and not 0 <= float(confidence) <= 1:
                issues.append(_issue("ERROR", "CONFIDENCE_RANGE", table, idx,
                                     "confidence", "confidence应在0到1之间", confidence))

    for idx, rec in enumerate(data.get("capital_increase", []), start=1):
        before, after = rec.get("registered_capital_before"), rec.get("registered_capital_after")
        if before is not None and after is not None and after < before:
            issues.append(_issue("ERROR", "CAPITAL_DECREASE_IN_INCREASE_EVENT",
                                 "capital_increase", idx, "registered_capital_after",
                                 "增资事件中注册资本后值小于前值", after))
        p = rec.get("shareholding_after")
        if p is not None and not 0 <= p <= 100:
            issues.append(_issue("ERROR", "PERCENT_RANGE", "capital_increase", idx,
                                 "shareholding_after", "持股比例超出0到100", p))

    for idx, rec in enumerate(data.get("equity_transfer", []), start=1):
        p = rec.get("equity_percent")
        if p is not None and not 0 <= p <= 100:
            issues.append(_issue("ERROR", "PERCENT_RANGE", "equity_transfer", idx,
                                 "equity_percent", "转让比例超出0到100", p))
        if rec.get("transferor") and rec.get("transferee") and rec["transferor"] == rec["transferee"]:
            issues.append(_issue("ERROR", "SAME_PARTY", "equity_transfer", idx,
                                 "transferee", "转让方与受让方相同", rec.get("transferee")))

    groups = defaultdict(list)
    for rec in data.get("equity_snapshot", []):
        groups[rec.get("date")].append(rec)
    for date, records in groups.items():
        vals = [r.get("shareholding_percent") for r in records
                if r.get("shareholding_percent") is not None]
        if len(vals) >= 2:
            total = sum(vals)
            if not 99.0 <= total <= 101.0:
                issues.append(_issue(
                    "WARN", "SNAPSHOT_PERCENT_SUM", "equity_snapshot", None,
                    "shareholding_percent", f"{date or '未知日期'}股东持股比例合计为{total:.4f}，未接近100", total
                ))

    # 事件日期顺序只做提示，不强制，因为招股书原文可能倒序叙述。
    for table in ("capital_increase", "equity_transfer"):
        dates = []
        for idx, rec in enumerate(data.get(table, []), start=1):
            value = rec.get("date")
            try:
                dates.append((idx, datetime.strptime(value, "%Y-%m-%d")))
            except Exception:
                continue
        for (idx1, d1), (idx2, d2) in zip(dates, dates[1:]):
            if d2 < d1:
                issues.append(_issue("INFO", "EVENT_ORDER", table, idx2, "date",
                                     "记录日期早于上一条，建议按日期重新排序"))
    return issues
