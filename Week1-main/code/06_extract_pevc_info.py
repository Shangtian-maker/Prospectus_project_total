# -*- coding: utf-8 -*-
"""
本地版 VC/PE 融资信息抽取脚本

依赖：
pip install pandas tqdm
"""

import re
import csv
import json
import time
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from tqdm import tqdm


BASE_DIR = Path(r"C:\Users\lenovo\Desktop\project")
COMPANY_CSV = BASE_DIR / "week1_public_samples.csv"
MD_DIR = BASE_DIR / "markdown_files"

OUTPUT_DIR = BASE_DIR / "output"
JSON_OUT_DIR = OUTPUT_DIR / "json_samples"
LOG_CSV = OUTPUT_DIR / "extraction_log.csv"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
JSON_OUT_DIR.mkdir(parents=True, exist_ok=True)


EMPTY_SCHEMA = {
    "company": {
        "company_name": "",
        "stock_code": "",
        "exchange": "",
        "board": "",
        "listing_date": "",
        "prospectus_title": "",
        "prospectus_url": "",
        "prospectus_version": "",
        "prospectus_date": ""
    },
    "financing_events": [],
    "processing": {
        "download_status": "success",
        "parse_status": "success",
        "locate_status": "success",
        "extract_status": "success",
        "review_status": "unchecked",
        "notes": ""
    }
}


ENCODINGS = [
    "utf-8-sig", "utf-8", "gb18030", "gbk", "gb2312",
    "big5", "latin1", "cp1252", "utf-16", "utf-16le", "utf-16be"
]


KEYWORDS = [
    "融资", "增资", "股权转让", "投资", "投资方", "投资人",
    "机构投资者", "私募", "PE", "VC", "风险投资", "财务投资者",
    "外部投资者", "估值", "每股价格", "入股", "股本演变",
    "历史沿革", "历次股权变动", "新增股东", "引入投资者"
]


ROUND_PATTERN = re.compile(
    r"(天使轮|种子轮|Pre[-\s]?A轮?|A轮|A\+轮|Pre[-\s]?B轮?|B轮|B\+轮|"
    r"Pre[-\s]?C轮?|C轮|C\+轮|D轮|E轮|战略投资|战略融资|IPO前融资|上市前融资)",
    re.I
)

DATE_PATTERN = re.compile(
    r"((?:19|20)\d{2}[年./-]\s?\d{1,2}[月./-]\s?\d{0,2}日?|"
    r"(?:19|20)\d{2}年\d{1,2}月|(?:19|20)\d{2}年)"
)

AMOUNT_PATTERN = re.compile(
    r"(?:(人民币|美元|港元|欧元|CNY|USD|HKD|EUR)\s*)?"
    r"([0-9]+(?:,[0-9]{3})*(?:\.\d+)?|[0-9]+(?:\.\d+)?)\s*"
    r"(万元|亿元|万人民币|亿人民币|元|万股|股)?"
)

SHARE_PRICE_PATTERN = re.compile(
    r"(?:每股价格|每股认购价格|认购价格|转让价格|增资价格|入股价格)"
    r"[为约是：:\s]*"
    r"([0-9]+(?:\.\d+)?)\s*元/?股"
)

VALUATION_PATTERN = re.compile(
    r"(投前估值|投后估值|整体估值|公司估值|估值)"
    r"[为约是：:\s]*"
    r"(?:(人民币|美元|港元|CNY|USD|HKD)\s*)?"
    r"([0-9]+(?:,[0-9]{3})*(?:\.\d+)?|[0-9]+(?:\.\d+)?)\s*"
    r"(万元|亿元|元)?"
)

RATIO_PATTERN = re.compile(
    r"([0-9]+(?:\.\d+)?)\s*%"
)

SHARES_PATTERN = re.compile(
    r"([0-9]+(?:,[0-9]{3})*(?:\.\d+)?|[0-9]+(?:\.\d+)?)\s*(万股|股)"
)


def safe_filename(name: str) -> str:
    name = str(name or "").strip()
    name = re.sub(r'[\\/:*?"<>|]+', "_", name)
    return name[:120] or "unknown_company"


def read_text(path: Path) -> Tuple[str, str]:
    for enc in ENCODINGS:
        try:
            return path.read_text(encoding=enc), enc
        except Exception:
            pass

    data = path.read_bytes()
    return data.decode("utf-8", errors="ignore"), "utf-8-ignore"


def read_csv_all_encodings(path: Path) -> Tuple[pd.DataFrame, str]:
    for enc in ENCODINGS:
        try:
            return pd.read_csv(path, dtype=str, encoding=enc).fillna(""), enc
        except Exception:
            pass
    return pd.read_csv(path, dtype=str, encoding="utf-8", errors="ignore").fillna(""), "utf-8-ignore"


def find_company_name_col(df: pd.DataFrame) -> str:
    candidates = ["company_name", "公司名称", "发行人", "企业名称", "name", "简称", "公司简称"]
    for c in candidates:
        if c in df.columns:
            return c
    return df.columns[0]


def find_md_file(company_name: str) -> Optional[Path]:
    files = list(MD_DIR.glob("*.md"))
    clean_name = re.sub(r"\s+", "", company_name)

    for f in files:
        stem = re.sub(r"\s+", "", f.stem)
        if clean_name and clean_name in stem:
            return f

    for f in files:
        stem = re.sub(r"\s+", "", f.stem)
        if clean_name and (stem in clean_name or clean_name in stem):
            return f

    return None


def split_sections(text: str) -> List[Dict[str, str]]:
    lines = text.splitlines()
    sections = []
    current_title = ""
    buffer = []

    heading_re = re.compile(r"^\s{0,3}(#{1,6}\s+.+|第[一二三四五六七八九十\d]+[章节].+|[一二三四五六七八九十]+、.+)")

    for line in lines:
        if heading_re.match(line.strip()):
            if buffer:
                sections.append({
                    "title": current_title,
                    "text": "\n".join(buffer)
                })
            current_title = line.strip().lstrip("#").strip()
            buffer = [line]
        else:
            buffer.append(line)

    if buffer:
        sections.append({
            "title": current_title,
            "text": "\n".join(buffer)
        })

    return sections


def relevant_blocks(text: str, window: int = 10) -> List[Dict[str, str]]:
    sections = split_sections(text)
    blocks = []

    for sec in sections:
        sec_text = sec["text"]
        lines = sec_text.splitlines()

        for i, line in enumerate(lines):
            if any(k.lower() in line.lower() for k in KEYWORDS):
                start = max(0, i - window)
                end = min(len(lines), i + window + 1)
                block = "\n".join(lines[start:end]).strip()
                if len(block) > 40:
                    blocks.append({
                        "source_section": sec["title"],
                        "text": block
                    })

    if not blocks:
        blocks.append({
            "source_section": "",
            "text": text[:8000]
        })

    return blocks


def normalize_money(num: str, unit: Optional[str]) -> Optional[float]:
    if not num:
        return None

    value = float(num.replace(",", ""))

    if unit in ["亿元", "亿人民币"]:
        return value * 100000000
    if unit in ["万元", "万人民币"]:
        return value * 10000
    if unit == "元" or unit is None:
        return value

    return value


def detect_currency(text: str) -> str:
    if any(x in text for x in ["美元", "USD"]):
        return "USD"
    if any(x in text for x in ["港元", "HKD"]):
        return "HKD"
    if any(x in text for x in ["欧元", "EUR"]):
        return "EUR"
    return "CNY"


def detect_event_type(text: str) -> str:
    has_zengzi = "增资" in text or "认购" in text
    has_transfer = "股权转让" in text or "股份转让" in text or "转让" in text

    if has_zengzi and has_transfer:
        return "增资及股权转让"
    if has_zengzi:
        return "增资"
    if has_transfer:
        return "股权转让"
    return "其他"


def detect_date_type(text: str) -> str:
    if "协议" in text and "签署" in text:
        return "协议签署日"
    if "工商变更" in text or "工商登记" in text:
        return "工商变更日"
    if "股东会" in text or "董事会" in text:
        return "股东会决议日"
    return "未说明"


def extract_date(text: str) -> str:
    m = DATE_PATTERN.search(text)
    return m.group(1).strip() if m else ""


def extract_round(text: str) -> str:
    m = ROUND_PATTERN.search(text)
    return m.group(1).strip() if m else "未披露"


def infer_round(text: str, disclosed_round: str) -> Tuple[str, str]:
    if disclosed_round != "未披露":
        return "", ""

    if "上市前" in text or "IPO前" in text or "申报前" in text:
        return "IPO前融资", "原文出现“上市前/IPO前/申报前”等表述，但未明确披露融资轮次"

    if "战略投资者" in text or "战略投资" in text:
        return "战略投资", "原文出现“战略投资者/战略投资”等表述，但未明确披露融资轮次"

    return "", ""


def extract_share_price(text: str) -> Optional[float]:
    m = SHARE_PRICE_PATTERN.search(text)
    return float(m.group(1)) if m else None


def extract_valuations(text: str) -> Tuple[Optional[float], Optional[float], str]:
    pre = None
    post = None
    basis = ""

    for m in VALUATION_PATTERN.finditer(text):
        label = m.group(1)
        num = m.group(3)
        unit = m.group(4)
        value = normalize_money(num, unit)

        if "投前" in label:
            pre = value
            basis = m.group(0)
        elif "投后" in label:
            post = value
            basis = m.group(0)
        elif basis == "":
            basis = m.group(0)

    return pre, post, basis


def extract_total_amount(text: str) -> Optional[float]:
    amount_candidates = []

    for m in AMOUNT_PATTERN.finditer(text):
        full = m.group(0)
        unit = m.group(3)

        if unit in ["万股", "股"]:
            continue

        nearby_start = max(0, m.start() - 20)
        nearby_end = min(len(text), m.end() + 20)
        nearby = text[nearby_start:nearby_end]

        if any(k in nearby for k in ["增资", "投资", "出资", "认购", "转让价款", "融资", "支付"]):
            amount_candidates.append(normalize_money(m.group(2), unit))

    return amount_candidates[0] if amount_candidates else None


def split_investor_names(raw: str) -> List[str]:
    raw = re.sub(r"[，。；;、和及与]", "|", raw)
    raw = re.sub(r"\s+", "", raw)
    names = [x.strip() for x in raw.split("|") if len(x.strip()) >= 2]
    return names[:20]


def extract_investors(text: str) -> List[Dict[str, Any]]:
    investors = []

    patterns = [
        r"(?:投资方|投资人|认购方|受让方|增资方|外部投资者|新增股东)[为包括系：:\s]*([^。\n；;]{2,120})",
        r"由([^。\n；;]{2,120}?)(?:投资|出资|认购|受让|增资)",
        r"向([^。\n；;]{2,120}?)(?:转让|出售)"
    ]

    names = []
    for p in patterns:
        for m in re.finditer(p, text):
            names.extend(split_investor_names(m.group(1)))

    cleaned = []
    for n in names:
        n = re.sub(r"(等|合计|共计|分别|以下简称.*)$", "", n)
        if n and n not in cleaned:
            cleaned.append(n)

    for name in cleaned:
        investor_type, is_pevc = classify_investor(name)
        investors.append({
            "investor_original_name": name,
            "investor_short_name": "",
            "investor_type": investor_type,
            "is_pevc": is_pevc,
            "investment_amount": None,
            "shares_acquired": extract_shares(text),
            "shareholding_ratio_after_event": extract_ratio(text),
            "exit_status_before_ipo": detect_exit_status(text)
        })

    if not investors:
        investors.append({
            "investor_original_name": "",
            "investor_short_name": "",
            "investor_type": "无法判断",
            "is_pevc": "uncertain",
            "investment_amount": None,
            "shares_acquired": extract_shares(text),
            "shareholding_ratio_after_event": extract_ratio(text),
            "exit_status_before_ipo": detect_exit_status(text)
        })

    return investors


def classify_investor(name: str) -> Tuple[str, str]:
    pevc_words = ["创投", "创业投资", "投资基金", "股权投资", "私募", "基金", "资本", "合伙企业"]
    industry_words = ["产业", "集团", "控股", "有限责任公司", "股份有限公司"]
    gov_words = ["政府", "国资", "财政", "引导基金", "高新投"]

    if any(w in name for w in pevc_words):
        return "VC/PE", "yes"
    if any(w in name for w in gov_words):
        return "政府基金", "uncertain"
    if any(w in name for w in industry_words):
        return "产业资本", "uncertain"
    if re.fullmatch(r"[\u4e00-\u9fa5]{2,4}", name):
        return "自然人", "no"

    return "无法判断", "uncertain"


def extract_ratio(text: str) -> Optional[float]:
    m = RATIO_PATTERN.search(text)
    return float(m.group(1)) if m else None


def extract_shares(text: str) -> Optional[float]:
    m = SHARES_PATTERN.search(text)
    if not m:
        return None
    value = float(m.group(1).replace(",", ""))
    if m.group(2) == "万股":
        return value * 10000
    return value


def detect_exit_status(text: str) -> str:
    if "全部退出" in text:
        return "全部退出"
    if "部分退出" in text:
        return "部分退出"
    if "未退出" in text or "仍持有" in text:
        return "未退出"
    return "无法判断"


def has_financing_signal(text: str) -> bool:
    return any(k.lower() in text.lower() for k in KEYWORDS)


def parse_financing_events(markdown: str) -> List[Dict[str, Any]]:
    blocks = relevant_blocks(markdown)
    events = []

    seen = set()
    for block in blocks:
        text = block["text"].strip()
        if not has_financing_signal(text):
            continue

        fingerprint = re.sub(r"\s+", "", text[:300])
        if fingerprint in seen:
            continue
        seen.add(fingerprint)

        disclosed_round = extract_round(text)
        inferred_round, basis = infer_round(text, disclosed_round)
        pre, post, valuation_basis = extract_valuations(text)
        amount = extract_total_amount(text)

        if not any([amount, disclosed_round != "未披露", inferred_round, "增资" in text, "股权转让" in text, "投资" in text]):
            continue

        event = {
            "event_order": len(events) + 1,
            "event_date": extract_date(text),
            "date_type": detect_date_type(text),
            "event_type": detect_event_type(text),
            "disclosed_round": disclosed_round,
            "inferred_round": inferred_round,
            "round_inference_basis": basis,
            "total_investment_amount": amount,
            "currency": detect_currency(text),
            "share_price": extract_share_price(text),
            "pre_money_valuation": pre,
            "post_money_valuation": post,
            "valuation_basis": valuation_basis,
            "investors": extract_investors(text),
            "source_section": block.get("source_section", ""),
            "source_page": "",
            "evidence_text": text[:1200],
            "confidence": "medium"
        }

        events.append(event)

    return events


def append_log(row: Dict[str, Any]) -> None:
    exists = LOG_CSV.exists()
    with LOG_CSV.open("a", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "timestamp", "company_name", "md_file", "output_json",
                "status", "event_count", "encoding", "notes", "error"
            ]
        )
        if not exists:
            writer.writeheader()
        writer.writerow(row)


def process_one(company_row: Dict[str, str], name_col: str) -> None:
    company_name = company_row.get(name_col, "").strip()
    md_file = None
    out_json = ""
    status = "success"
    error = ""
    notes = ""
    encoding = ""
    event_count = 0

    try:
        md_file = find_md_file(company_name)
        if not md_file:
            raise FileNotFoundError(f"未找到 markdown 文件：{company_name}")

        markdown, encoding = read_text(md_file)
        events = parse_financing_events(markdown)
        event_count = len(events)

        data = deepcopy(EMPTY_SCHEMA)
        data["company"]["company_name"] = company_name
        data["financing_events"] = events

        if event_count == 0:
            data["processing"]["locate_status"] = "partial"
            data["processing"]["extract_status"] = "partial"
            notes = "未定位到明确 VC/PE 融资事件，建议人工复核"
        else:
            notes = f"提取到 {event_count} 条候选融资事件，需人工复核"

        data["processing"]["notes"] = notes

        out_path = JSON_OUT_DIR / f"{safe_filename(company_name)}.json"
        out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        out_json = str(out_path)

    except Exception as e:
        status = "fail"
        error = repr(e)

    finally:
        append_log({
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "company_name": company_name,
            "md_file": str(md_file) if md_file else "",
            "output_json": out_json,
            "status": status,
            "event_count": event_count,
            "encoding": encoding,
            "notes": notes,
            "error": error
        })


def main() -> None:
    if not COMPANY_CSV.exists():
        print(f"公司清单不存在：{COMPANY_CSV}")
        return

    if not MD_DIR.exists():
        print(f"markdown 文件夹不存在：{MD_DIR}")
        return

    df, csv_encoding = read_csv_all_encodings(COMPANY_CSV)
    name_col = find_company_name_col(df)

    print(f"公司清单编码：{csv_encoding}")
    print(f"公司名称列：{name_col}")

    for _, row in tqdm(df.iterrows(), total=len(df), desc="抽取 VC/PE 信息"):
        process_one(row.to_dict(), name_col)

    print(f"完成。JSON 输出目录：{JSON_OUT_DIR}")
    print(f"提取日志：{LOG_CSV}")


if __name__ == "__main__":
    main()