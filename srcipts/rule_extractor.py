from __future__ import annotations
import re
from typing import Dict, Any, List

DATE_RE = re.compile(r"((?:19|20)\d{2}\s*[年./-]\s*\d{1,2}(?:\s*[月./-]\s*\d{1,2}\s*日?)?)")
AMOUNT_RE = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(亿元|万元|元|万股|亿股|股)")
PERCENT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")
PAGE_RE = re.compile(r"\[PAGE\s+(\d+)\]")

def _page_of(text: str, pos: int) -> int | None:
    pages = list(PAGE_RE.finditer(text[:pos]))
    return int(pages[-1].group(1)) if pages else None

def extract_rule_candidates(text: str, company_id: str) -> Dict[str, List[Dict[str, Any]]]:
    """
    规则层只产生候选记录，不宣称完成语义识别。
    主要用于无LLM时保留页码、日期、金额和上下文，供人工复核或后续模型抽取。
    """
    capital_increase = []
    equity_transfer = []
    equity_snapshot = []

    event_index = 1
    for m in re.finditer(r"增资|认购|新增注册资本|增加注册资本", text):
        s, e = max(0, m.start() - 220), min(len(text), m.end() + 420)
        ctx = text[s:e]
        date = DATE_RE.search(ctx)
        amounts = AMOUNT_RE.findall(ctx)
        percents = PERCENT_RE.findall(ctx)
        capital_increase.append({
            "event_id": f"{company_id}_CI_{event_index:04d}",
            "date": date.group(1) if date else None,
            "subscriber": None,
            "subscribed_amount": "".join(amounts[0]) if amounts else None,
            "paid_amount": None,
            "price_per_share": None,
            "registered_capital_before": None,
            "registered_capital_after": "".join(amounts[-1]) if len(amounts) > 1 else None,
            "shareholding_after": percents[-1] if percents else None,
            "currency": "CNY",
            "approval": None,
            "source_page": _page_of(text, m.start()),
            "source_text": ctx,
            "confidence": 0.35
        })
        event_index += 1

    event_index = 1
    for m in re.finditer(r"股权转让|股份转让|转让其持有|受让", text):
        s, e = max(0, m.start() - 220), min(len(text), m.end() + 420)
        ctx = text[s:e]
        date = DATE_RE.search(ctx)
        amounts = AMOUNT_RE.findall(ctx)
        percents = PERCENT_RE.findall(ctx)
        equity_transfer.append({
            "event_id": f"{company_id}_ET_{event_index:04d}",
            "date": date.group(1) if date else None,
            "transferor": None,
            "transferee": None,
            "equity_percent": percents[0] if percents else None,
            "shares": "".join(amounts[0]) if amounts and "股" in amounts[0][1] else None,
            "consideration": "".join(amounts[-1]) if amounts else None,
            "price_per_share": None,
            "currency": "CNY",
            "approval": None,
            "source_page": _page_of(text, m.start()),
            "source_text": ctx,
            "confidence": 0.35
        })
        event_index += 1

    # 快照候选仅抓取“股东+比例”邻近文本，后续由LLM或人工拆分股东名称。
    event_index = 1
    for m in re.finditer(r"股东|持股比例|股权结构", text):
        s, e = max(0, m.start() - 160), min(len(text), m.end() + 320)
        ctx = text[s:e]
        percents = PERCENT_RE.findall(ctx)
        if not percents:
            continue
        date = DATE_RE.search(ctx)
        equity_snapshot.append({
            "snapshot_id": f"{company_id}_ES_{event_index:04d}",
            "date": date.group(1) if date else None,
            "shareholder_name": None,
            "shares": None,
            "shareholding_percent": percents[0],
            "shareholder_type": None,
            "source_page": _page_of(text, m.start()),
            "source_text": ctx,
            "confidence": 0.25
        })
        event_index += 1

    return {
        "capital_increase": capital_increase,
        "equity_transfer": equity_transfer,
        "equity_snapshot": equity_snapshot
    }
