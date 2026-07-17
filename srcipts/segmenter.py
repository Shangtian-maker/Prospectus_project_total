from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Dict, List, Iterable
import re

@dataclass
class Segment:
    segment_id: str
    section: str
    start_page: int
    end_page: int
    text: str

    def to_dict(self):
        return asdict(self)

SECTION_KEYWORDS: Dict[str, List[str]] = {
    "company_profile": [
        "发行人基本情况", "公司基本情况", "发行人概况", "基本情况"
    ],
    "equity_evolution": [
        "股本演变", "股权演变", "历史沿革", "设立及历次股本变化",
        "发行人设立", "历次增资", "历次股权转让"
    ],
    "shareholders": [
        "股东情况", "股权结构", "主要股东", "前十名股东", "发起人"
    ],
}

def _page_matches(text: str, keywords: Iterable[str]) -> bool:
    compact = re.sub(r"\s+", "", text)
    return any(re.sub(r"\s+", "", kw) in compact for kw in keywords)

def locate_segments(pages, padding_pages: int = 2) -> List[Segment]:
    n = len(pages)
    page_map = {p.page: p.text for p in pages}
    results: List[Segment] = []

    for section, keywords in SECTION_KEYWORDS.items():
        hits = [p.page for p in pages if _page_matches(p.text, keywords)]
        if not hits:
            continue
        ranges = []
        start = max(1, min(hits) - padding_pages)
        end = min(n, max(hits) + padding_pages)
        ranges.append((start, end))

        for i, (s, e) in enumerate(ranges, start=1):
            text_parts = [f"\n[PAGE {p}]\n{page_map.get(p, '')}" for p in range(s, e + 1)]
            results.append(Segment(
                segment_id=f"{section}_{i}",
                section=section,
                start_page=s,
                end_page=e,
                text="".join(text_parts)
            ))

    if not any(s.section == "equity_evolution" for s in results):
        # 兜底：全文按固定字符长度切分，避免完全漏掉股权演变章节。
        joined = "".join(f"\n[PAGE {p.page}]\n{p.text}" for p in pages)
        results.append(Segment(
            segment_id="equity_evolution_fallback",
            section="equity_evolution",
            start_page=1,
            end_page=n,
            text=joined
        ))
    return results

def split_segment(segment: Segment, chunk_chars: int, overlap_chars: int) -> List[Segment]:
    if len(segment.text) <= chunk_chars:
        return [segment]
    chunks = []
    start = 0
    i = 1
    while start < len(segment.text):
        end = min(len(segment.text), start + chunk_chars)
        chunks.append(Segment(
            segment_id=f"{segment.segment_id}_chunk_{i}",
            section=segment.section,
            start_page=segment.start_page,
            end_page=segment.end_page,
            text=segment.text[start:end]
        ))
        if end >= len(segment.text):
            break
        start = max(start + 1, end - overlap_chars)
        i += 1
    return chunks
