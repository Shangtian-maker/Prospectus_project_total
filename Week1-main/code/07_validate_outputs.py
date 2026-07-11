# -*- coding: utf-8 -*-
"""
校验 VC/PE 提取结果 JSON

输入：
  outputs/week1_sample_json/

输出：
  logs/validation_log.csv
  logs/error_cases.md

依赖：
  无需额外安装，使用 Python 标准库
"""

import csv
import json
import time
from pathlib import Path
from typing import Any, Dict, List


BASE_DIR = Path(r"C:\Users\lenovo\Desktop\project")

JSON_DIR = BASE_DIR / "outputs" / "week1_sample_json"
LOG_DIR = BASE_DIR / "logs"

VALIDATION_LOG = LOG_DIR / "validation_log.csv"
ERROR_CASES_MD = LOG_DIR / "error_cases.md"

LOG_DIR.mkdir(parents=True, exist_ok=True)


REQUIRED_TOP_FIELDS = ["company", "financing_events", "processing"]

REQUIRED_COMPANY_FIELDS = [
    "company_name",
    "stock_code",
    "exchange",
    "board",
    "listing_date",
    "prospectus_title",
    "prospectus_url",
    "prospectus_version",
    "prospectus_date",
]

REQUIRED_EVENT_FIELDS = [
    "event_order",
    "event_date",
    "date_type",
    "event_type",
    "disclosed_round",
    "inferred_round",
    "round_inference_basis",
    "total_investment_amount",
    "currency",
    "share_price",
    "pre_money_valuation",
    "post_money_valuation",
    "valuation_basis",
    "investors",
    "source_section",
    "source_page",
    "evidence_text",
    "confidence",
]

REQUIRED_INVESTOR_FIELDS = [
    "investor_original_name",
    "investor_short_name",
    "investor_type",
    "is_pevc",
    "investment_amount",
    "shares_acquired",
    "shareholding_ratio_after_event",
    "exit_status_before_ipo",
]


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def is_empty(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}


def validate_json_file(path: Path) -> Dict[str, Any]:
    errors: List[str] = []
    warnings: List[str] = []

    company_name = ""
    event_count = 0

    try:
        data = load_json(path)
    except Exception as e:
        return {
            "file": str(path),
            "company_name": "",
            "event_count": 0,
            "status": "fail",
            "errors": f"JSON无法解析：{repr(e)}",
            "warnings": "",
        }

    for field in REQUIRED_TOP_FIELDS:
        if field not in data:
            errors.append(f"缺少顶层字段：{field}")

    company = data.get("company", {})
    if not isinstance(company, dict):
        errors.append("company 不是对象")
        company = {}

    company_name = company.get("company_name", "")

    for field in REQUIRED_COMPANY_FIELDS:
        if field not in company:
            warnings.append(f"company 缺少字段：{field}")

    events = data.get("financing_events", [])
    if not isinstance(events, list):
        errors.append("financing_events 不是列表")
        events = []

    event_count = len(events)

    if event_count == 0:
        warnings.append("未提取到融资事件，需人工确认是否确实未披露")

    for i, event in enumerate(events, start=1):
        if not isinstance(event, dict):
            errors.append(f"事件{i}不是对象")
            continue

        for field in REQUIRED_EVENT_FIELDS:
            if field not in event:
                errors.append(f"事件{i}缺少字段：{field}")

        if is_empty(event.get("evidence_text")):
            errors.append(f"事件{i}缺少 evidence_text")

        if is_empty(event.get("source_section")) and is_empty(event.get("source_page")):
            warnings.append(f"事件{i}缺少 source_section/source_page")

        if is_empty(event.get("disclosed_round")):
            errors.append(f"事件{i} disclosed_round 为空，应填“未披露”或原文披露轮次")

        if event.get("disclosed_round") not in [None, "", "未披露"]:
            pass
        else:
            if event.get("disclosed_round") != "未披露":
                errors.append(f"事件{i} 未披露轮次时 disclosed_round 应为“未披露”")

        if not is_empty(event.get("inferred_round")) and is_empty(event.get("round_inference_basis")):
            errors.append(f"事件{i}有 inferred_round 但缺少 round_inference_basis")

        amount_fields = [
            "total_investment_amount",
            "share_price",
            "pre_money_valuation",
            "post_money_valuation",
        ]

        for field in amount_fields:
            value = event.get(field)
            if value is not None and not isinstance(value, (int, float)):
                warnings.append(f"事件{i}字段 {field} 不是数字或 null：{value}")

        investors = event.get("investors", [])
        if not isinstance(investors, list):
            errors.append(f"事件{i} investors 不是列表")
            investors = []

        if len(investors) == 0:
            warnings.append(f"事件{i} investors 为空")

        for j, investor in enumerate(investors, start=1):
            if not isinstance(investor, dict):
                errors.append(f"事件{i}投资方{j}不是对象")
                continue

            for field in REQUIRED_INVESTOR_FIELDS:
                if field not in investor:
                    errors.append(f"事件{i}投资方{j}缺少字段：{field}")

            if is_empty(investor.get("investor_original_name")):
                warnings.append(f"事件{i}投资方{j}缺少 investor_original_name")

            if investor.get("is_pevc") not in ["yes", "no", "uncertain", None, ""]:
                warnings.append(f"事件{i}投资方{j} is_pevc 值异常：{investor.get('is_pevc')}")

    processing = data.get("processing", {})
    if not isinstance(processing, dict):
        errors.append("processing 不是对象")

    if errors:
        status = "fail"
    elif warnings:
        status = "revise"
    else:
        status = "pass"

    return {
        "file": str(path),
        "company_name": company_name,
        "event_count": event_count,
        "status": status,
        "errors": "；".join(errors),
        "warnings": "；".join(warnings),
    }


def write_validation_log(rows: List[Dict[str, Any]]) -> None:
    with VALIDATION_LOG.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "timestamp",
                "file",
                "company_name",
                "event_count",
                "status",
                "errors",
                "warnings",
            ],
        )
        writer.writeheader()

        for row in rows:
            writer.writerow({
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                **row,
            })


def write_error_cases(rows: List[Dict[str, Any]]) -> None:
    lines = []
    lines.append("# 校验错误案例汇总\n")

    bad_rows = [r for r in rows if r["status"] in ["fail", "revise"]]

    if not bad_rows:
        lines.append("未发现需要修订的案例。\n")
    else:
        for r in bad_rows:
            lines.append(f"## {r.get('company_name') or '未知公司'}\n")
            lines.append(f"- 文件：`{r['file']}`\n")
            lines.append(f"- 状态：{r['status']}\n")
            lines.append(f"- 融资事件数：{r['event_count']}\n")
            if r["errors"]:
                lines.append(f"- 错误：{r['errors']}\n")
            if r["warnings"]:
                lines.append(f"- 警告：{r['warnings']}\n")
            lines.append("\n")

    ERROR_CASES_MD.write_text("".join(lines), encoding="utf-8")


def main() -> None:
    if not JSON_DIR.exists():
        print(f"JSON 输出目录不存在：{JSON_DIR}")
        return

    json_files = sorted(JSON_DIR.glob("*.json"))

    if not json_files:
        print(f"未找到 JSON 文件：{JSON_DIR}")
        return

    rows = []

    for path in json_files:
        result = validate_json_file(path)
        rows.append(result)

    write_validation_log(rows)
    write_error_cases(rows)

    total = len(rows)
    passed = sum(1 for r in rows if r["status"] == "pass")
    revised = sum(1 for r in rows if r["status"] == "revise")
    failed = sum(1 for r in rows if r["status"] == "fail")

    print("校验完成")
    print(f"总文件数：{total}")
    print(f"通过：{passed}")
    print(f"需修订：{revised}")
    print(f"失败：{failed}")
    print(f"校验日志：{VALIDATION_LOG}")
    print(f"错误案例：{ERROR_CASES_MD}")


if __name__ == "__main__":
    main()