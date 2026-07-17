#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
将LLM输出的JSON文件转换为三张CSV表：

1. subscription_flow.csv
2. share_transfer_flow.csv
3. equity_snapshot.csv

特点：
- 只使用Python标准库；
- 不需要artifact_tool；
- 不需要openpyxl；
- 不需要pandas；
- CSV可直接使用Excel打开；
- JSON中的null转换为空单元格；
- 数字0正常保留；
- 自动规范日期和页码；
- 自动按照时间排序；
- equity_snapshot按照Pre-t0、t0、t1、t2……排序；
- 同一时点支持一行一股东；
- 支持LLM输出位于顶层数组、tables对象或events数组中的情况。

适用Python版本：Python 3.8及以上
"""

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ============================================================
# 1. 三张表的固定表头
# ============================================================

TABLE_HEADERS = {
    "subscription_flow": [
        "公司",
        "事件类型",
        "时间",
        "认购人",
        "数量（万股）",
        "金额（万元）",
        "变化后总股本（万元）",
        "页码",
        "原文证据",
    ],
    "share_transfer_flow": [
        "公司",
        "事件类型",
        "时间",
        "转让方",
        "受让方",
        "数量（万元）",
        "价格",
        "页码",
        "原文证据",
    ],
    "equity_snapshot": [
        "公司",
        "时点",
        "总股本（万股）",
        "总出资额（万元）",
        "股东名称",
        "持股数（万股）",
        "出资额（万元）",
        "持股比例（%）",
        "页码",
        "原文证据",
    ],
}


# ============================================================
# 2. 常见字段名兼容
# ============================================================

FIELD_ALIASES = {
    "subscription_flow": {
        "company": "公司",
        "company_name": "公司",
        "event_type": "事件类型",
        "event_date": "时间",
        "date": "时间",
        "subscriber": "认购人",
        "investor": "认购人",
        "认购主体": "认购人",
        "认购数量": "数量（万股）",
        "认购数量（万股）": "数量（万股）",
        "新增股份数（万股）": "数量（万股）",
        "subscription_shares": "数量（万股）",
        "投资金额（万元）": "金额（万元）",
        "认购金额（万元）": "金额（万元）",
        "subscription_amount": "金额（万元）",
        "变更后总股本（万元）": "变化后总股本（万元）",
        "增资后注册资本（万元）": "变化后总股本（万元）",
        "变化后注册资本（万元）": "变化后总股本（万元）",
        "registered_capital_after": "变化后总股本（万元）",
        "source_pdf_pages": "页码",
        "source_pages": "页码",
        "evidence": "原文证据",
    },

    "share_transfer_flow": {
        "company": "公司",
        "company_name": "公司",
        "event_type": "事件类型",
        "event_date": "时间",
        "date": "时间",
        "transferor": "转让方",
        "seller": "转让方",
        "transferee": "受让方",
        "buyer": "受让方",
        "转让数量": "数量（万元）",
        "转让出资额（万元）": "数量（万元）",
        "transfer_amount": "数量（万元）",
        "transfer_quantity": "数量（万元）",
        "交易价格": "价格",
        "转让价款": "价格",
        "transfer_price": "价格",
        "source_pdf_pages": "页码",
        "source_pages": "页码",
        "evidence": "原文证据",
    },

    "equity_snapshot": {
        "company": "公司",
        "company_name": "公司",
        "timepoint": "时点",
        "snapshot_time": "时点",
        "总股本": "总股本（万股）",
        "total_shares": "总股本（万股）",
        "注册资本（万元）": "总出资额（万元）",
        "总注册资本（万元）": "总出资额（万元）",
        "total_contribution": "总出资额（万元）",
        "shareholder": "股东名称",
        "shareholder_name": "股东名称",
        "股东": "股东名称",
        "持股数": "持股数（万股）",
        "holding_shares": "持股数（万股）",
        "出资额": "出资额（万元）",
        "contribution_amount": "出资额（万元）",
        "持股比例": "持股比例（%）",
        "holding_ratio": "持股比例（%）",
        "source_pdf_pages": "页码",
        "source_pages": "页码",
        "evidence": "原文证据",
    },
}


# ============================================================
# 3. 清理和解析JSON
# ============================================================

def clean_json_text(text: str) -> str:
    """
    清理LLM输出中的：
    - UTF-8 BOM；
    - ```json代码框；
    - JSON前后的少量说明文字。
    """
    text = text.lstrip("\ufeff").strip()

    fenced = re.fullmatch(
        r"```(?:json)?\s*(.*?)\s*```",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )

    if fenced:
        text = fenced.group(1).strip()

    start = text.find("{")
    end = text.rfind("}")

    if start >= 0 and end > start:
        text = text[start:end + 1]

    return text


def parse_json_text(text: str, source: str) -> Dict[str, Any]:
    """解析JSON并显示准确的错误位置。"""
    cleaned = clean_json_text(text)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as error:
        start = max(0, error.pos - 100)
        end = min(len(cleaned), error.pos + 100)
        nearby = cleaned[start:end]

        raise ValueError(
            "JSON解析失败：{}\n"
            "错误位置：第{}行，第{}列\n"
            "错误原因：{}\n"
            "错误附近内容：{}".format(
                source,
                error.lineno,
                error.colno,
                error.msg,
                repr(nearby),
            )
        ) from error

    if not isinstance(data, dict):
        raise ValueError("JSON最外层必须是对象，不能是数组或字符串。")

    return data


def load_json_file(path: Path) -> Dict[str, Any]:
    """读取JSON文件。"""
    if not path.exists():
        raise FileNotFoundError("找不到JSON文件：{}".format(path))

    text = path.read_text(encoding="utf-8-sig")
    return parse_json_text(text, str(path))


# ============================================================
# 4. 兼容API包装格式
# ============================================================

def unwrap_llm_result(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    某些LLM API可能将真正的JSON放在以下字段中：
    content、output_text、response、result、text。
    """
    table_names = set(TABLE_HEADERS.keys())

    if table_names.intersection(data.keys()):
        return data

    tables_object = data.get("tables")

    if isinstance(tables_object, dict):
        if table_names.intersection(tables_object.keys()):
            merged = dict(data)
            merged.update(tables_object)
            return merged

    for key in [
        "content",
        "output_text",
        "response",
        "result",
        "text",
    ]:
        wrapped = data.get(key)

        if isinstance(wrapped, str) and "{" in wrapped:
            nested = parse_json_text(
                wrapped,
                "JSON字段：{}".format(key),
            )
            return unwrap_llm_result(nested)

        if isinstance(wrapped, dict):
            try:
                return unwrap_llm_result(wrapped)
            except ValueError:
                pass

    return data


# ============================================================
# 5. 通用值处理
# ============================================================

def normalize_key(value: Any) -> str:
    """规范字段名，便于匹配中文括号和空格差异。"""
    text = str(value or "").strip()

    text = (
        text.replace("(", "（")
        .replace(")", "）")
        .replace("％", "%")
        .replace("﹪", "%")
    )

    text = re.sub(r"\s+", "", text)

    return text.lower()


def build_alias_lookup(table_name: str) -> Dict[str, str]:
    """创建标准字段和别名字段映射。"""
    lookup = {}

    for header in TABLE_HEADERS[table_name]:
        lookup[normalize_key(header)] = header

    for alias, standard in FIELD_ALIASES.get(table_name, {}).items():
        lookup[normalize_key(alias)] = standard

    return lookup


def normalize_text(value: Any) -> str:
    """删除换行和多余空格。"""
    if value is None:
        return ""

    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)

    text = str(value)
    text = text.replace("\r", " ")
    text = text.replace("\n", " ")
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def normalize_number(value: Any) -> Any:
    """
    数值处理：
    - null转换为空字符串；
    - 数值0正常保留；
    - 纯数字字符串转换为数字；
    - 带文字的值保持原样。
    """
    if value is None:
        return ""

    if isinstance(value, bool):
        return int(value)

    if isinstance(value, (int, float)):
        return value

    text = str(value).strip()

    if text.lower() in {
        "",
        "null",
        "none",
        "n/a",
        "na",
        "未披露",
        "不适用",
        "无法确定",
    }:
        return ""

    numeric_text = (
        text.replace(",", "")
        .replace("，", "")
        .strip()
    )

    if re.fullmatch(r"[-+]?\d+", numeric_text):
        try:
            return int(numeric_text)
        except ValueError:
            return text

    if re.fullmatch(r"[-+]?(?:\d+\.\d*|\d*\.\d+)", numeric_text):
        try:
            return float(numeric_text)
        except ValueError:
            return text

    return text


def normalize_date(value: Any) -> str:
    """
    日期转换：

    2004-06
    -> 2004年6月

    2020-06-15
    -> 2020年6月15日
    """
    if value is None:
        return ""

    text = normalize_text(value)

    iso_match = re.fullmatch(
        r"(\d{4})[-/.](\d{1,2})(?:[-/.](\d{1,2}))?",
        text,
    )

    if iso_match:
        year = int(iso_match.group(1))
        month = int(iso_match.group(2))
        day = iso_match.group(3)

        if day:
            return "{}年{}月{}日".format(
                year,
                month,
                int(day),
            )

        return "{}年{}月".format(year, month)

    chinese_match = re.fullmatch(
        r"(\d{4})年0?(\d{1,2})月(?:0?(\d{1,2})日)?",
        text,
    )

    if chinese_match:
        year = int(chinese_match.group(1))
        month = int(chinese_match.group(2))
        day = chinese_match.group(3)

        if day:
            return "{}年{}月{}日".format(
                year,
                month,
                int(day),
            )

        return "{}年{}月".format(year, month)

    return text


def normalize_page(value: Any) -> str:
    """
    页码转换：

    原始PDF第34页
    -> 34

    原始PDF第30-31页
    -> 30-31

    原始PDF第34页、第35页
    -> 34、35
    """
    if value is None:
        return ""

    if isinstance(value, list):
        parts = [
            normalize_page(item)
            for item in value
            if item is not None
        ]
        return "、".join(
            item for item in parts if item
        )

    text = normalize_text(value)

    text = re.sub(
        r"原始\s*PDF\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )

    text = text.replace("物理页码", "")
    text = text.replace("物理页", "")
    text = text.replace("页码", "")
    text = text.replace("第", "")
    text = text.replace("页", "")
    text = text.replace("，", "、")
    text = text.replace(",", "、")
    text = text.replace("；", "、")
    text = text.replace(";", "、")
    text = text.replace("至", "-")
    text = text.replace("—", "-")
    text = text.replace("–", "-")
    text = re.sub(r"\s+", "", text)

    return text.strip("、")


def normalize_evidence(value: Any) -> str:
    """将证据列表或对象转换为单行文字。"""
    if value is None:
        return ""

    if isinstance(value, list):
        parts = []

        for item in value:
            if isinstance(item, dict):
                page = (
                    item.get("页码")
                    or item.get("page")
                    or item.get("pdf_page")
                    or item.get("source_pdf_page")
                )

                text = (
                    item.get("原文证据")
                    or item.get("text")
                    or item.get("quote")
                    or item.get("evidence")
                )

                if page and text:
                    parts.append(
                        "{}：{}".format(
                            normalize_page(page),
                            normalize_text(text),
                        )
                    )
                elif text:
                    parts.append(normalize_text(text))
                else:
                    parts.append(
                        json.dumps(item, ensure_ascii=False)
                    )
            else:
                parts.append(normalize_text(item))

        return "；".join(
            part for part in parts if part
        )

    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)

    return normalize_text(value)


# ============================================================
# 6. 数字字段
# ============================================================

NUMERIC_FIELDS = {
    "数量（万股）",
    "金额（万元）",
    "变化后总股本（万元）",
    "数量（万元）",
    "总股本（万股）",
    "总出资额（万元）",
    "持股数（万股）",
    "出资额（万元）",
    "持股比例（%）",
}


# ============================================================
# 7. 从events结构中展开三张表
# ============================================================

def value_to_page(value: Any) -> str:
    """将source_pdf_pages等字段转换为页码字符串。"""
    return normalize_page(value)


def event_default_evidence(event: Dict[str, Any]) -> str:
    """提取事件层面的证据。"""
    evidence = (
        event.get("原文证据")
        or event.get("evidence")
        or event.get("evidences")
    )

    return normalize_evidence(evidence)


def append_event_rows(
    event: Dict[str, Any],
    root_company: str,
    output: Dict[str, List[Dict[str, Any]]],
) -> None:
    """将单个事件中的三个数组展开。"""
    company = (
        event.get("公司")
        or event.get("company")
        or event.get("company_name")
        or root_company
    )

    event_type = (
        event.get("事件类型")
        or event.get("event_type")
        or event.get("event_type_hint")
        or ""
    )

    event_date = (
        event.get("时间")
        or event.get("event_date")
        or event.get("date")
        or ""
    )

    event_pages = (
        event.get("页码")
        or event.get("source_pdf_pages")
        or event.get("source_pages")
        or ""
    )

    evidence = event_default_evidence(event)

    table_candidates = {
        "subscription_flow": [
            "subscription_flow",
            "subscription_rows",
            "subscriptions",
        ],
        "share_transfer_flow": [
            "share_transfer_flow",
            "share_transfer_rows",
            "transfer_rows",
            "transfers",
        ],
        "equity_snapshot": [
            "equity_snapshot",
            "equity_snapshot_rows",
            "snapshot_rows",
            "snapshots",
        ],
    }

    for table_name, candidate_keys in table_candidates.items():
        rows = None

        for key in candidate_keys:
            candidate = event.get(key)

            if isinstance(candidate, list):
                rows = candidate
                break

        if rows is None:
            continue

        for raw_row in rows:
            if not isinstance(raw_row, dict):
                continue

            row = dict(raw_row)

            if company:
                row.setdefault("公司", company)

            if table_name != "equity_snapshot":
                if event_type:
                    row.setdefault("事件类型", event_type)

                if event_date:
                    row.setdefault("时间", event_date)

            if event_pages:
                row.setdefault("页码", event_pages)

            if evidence:
                row.setdefault("原文证据", evidence)

            output[table_name].append(row)


def extract_raw_tables(data: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    """
    支持三种JSON结构：

    结构1：
    {
      "subscription_flow": [],
      "share_transfer_flow": [],
      "equity_snapshot": []
    }

    结构2：
    {
      "tables": {
        "subscription_flow": [],
        ...
      }
    }

    结构3：
    {
      "events": [
        {
          "subscription_rows": [],
          "share_transfer_rows": [],
          "equity_snapshot_rows": []
        }
      ]
    }
    """
    data = unwrap_llm_result(data)

    output = {
        "subscription_flow": [],
        "share_transfer_flow": [],
        "equity_snapshot": [],
    }

    top_company = normalize_text(
        data.get("公司")
        or data.get("company")
        or data.get("document_id")
        or ""
    )

    tables_object = data.get("tables")

    if isinstance(tables_object, dict):
        source = tables_object
    else:
        source = data

    found_direct_table = False

    for table_name in TABLE_HEADERS:
        rows = source.get(table_name)

        if isinstance(rows, list):
            found_direct_table = True

            for row in rows:
                if isinstance(row, dict):
                    copied = dict(row)

                    if top_company:
                        copied.setdefault("公司", top_company)

                    output[table_name].append(copied)

    events = data.get("events")

    if isinstance(events, list):
        for event in events:
            if isinstance(event, dict):
                append_event_rows(
                    event,
                    top_company,
                    output,
                )

    if not found_direct_table and not isinstance(events, list):
        raise ValueError(
            "JSON中没有找到三张表数据。\n"
            "应至少包含以下一种结构：\n"
            "1. subscription_flow、share_transfer_flow、equity_snapshot；\n"
            "2. tables对象；\n"
            "3. events数组。"
        )

    return output


# ============================================================
# 8. 单行标准化
# ============================================================

def normalize_row(
    table_name: str,
    raw_row: Dict[str, Any],
) -> Dict[str, Any]:
    """将一条记录转换为固定字段。"""
    headers = TABLE_HEADERS[table_name]
    alias_lookup = build_alias_lookup(table_name)

    mapped = {}

    for raw_key, value in raw_row.items():
        standard_key = alias_lookup.get(
            normalize_key(raw_key)
        )

        if standard_key:
            if (
                standard_key not in mapped
                or mapped[standard_key] in [None, ""]
            ):
                mapped[standard_key] = value

    result = {}

    for field in headers:
        value = mapped.get(field)

        if field in NUMERIC_FIELDS:
            result[field] = normalize_number(value)

        elif field == "时间":
            result[field] = normalize_date(value)

        elif field == "页码":
            result[field] = normalize_page(value)

        elif field == "原文证据":
            result[field] = normalize_evidence(value)

        elif field == "时点":
            result[field] = normalize_text(value).replace("｜", "|")

        else:
            result[field] = normalize_text(value)

    return result


def normalize_table_rows(
    table_name: str,
    raw_rows: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """规范化整张表。"""
    rows = []

    for index, raw_row in enumerate(raw_rows, start=1):
        if not isinstance(raw_row, dict):
            print(
                "警告：{}第{}条记录不是JSON对象，已跳过。".format(
                    table_name,
                    index,
                )
            )
            continue

        rows.append(
            normalize_row(table_name, raw_row)
        )

    return rows


# ============================================================
# 9. 排序
# ============================================================

def date_sort_key(value: Any) -> Tuple[int, int, int, int]:
    """时间排序键。"""
    if value is None:
        return 9999, 12, 31, 1

    text = normalize_text(value)

    match = re.search(
        r"(\d{4})"
        r"(?:年|[-/.])?"
        r"(\d{1,2})?"
        r"(?:月|[-/.])?"
        r"(\d{1,2})?",
        text,
    )

    if not match:
        return 9999, 12, 31, 1

    year = int(match.group(1))
    month = int(match.group(2) or 1)
    day = int(match.group(3) or 1)

    return year, month, day, 0


def equity_sort_key(value: Any, original_index: int) -> Tuple[Any, ...]:
    """
    equity_snapshot排序：

    1. Pre-t0|设立时；
    2. 其他Pre-t0历史事件；
    3. t0；
    4. t1、t2、t3……；
    5. 无法识别的时点。
    """
    text = normalize_text(value)

    if re.match(r"(?i)^pre[-_ ]?t0", text):
        if "设立" in text:
            return 0, 0, 0, 0, original_index

        year, month, day, _ = date_sort_key(text)

        return 0, 1, year, month, day, original_index

    t_match = re.match(r"(?i)^t(\d+)", text)

    if t_match:
        return 1, int(t_match.group(1)), 0, 0, 0, original_index

    year, month, day, _ = date_sort_key(text)

    return 2, 999999, year, month, day, original_index


def sort_table_rows(
    table_name: str,
    rows: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """按照时间或时点排序。"""
    indexed = list(enumerate(rows))

    if table_name in {
        "subscription_flow",
        "share_transfer_flow",
    }:
        indexed.sort(
            key=lambda item: (
                date_sort_key(item[1].get("时间")),
                item[0],
            )
        )

    elif table_name == "equity_snapshot":
        indexed.sort(
            key=lambda item: equity_sort_key(
                item[1].get("时点"),
                item[0],
            )
        )

    return [row for _, row in indexed]


# ============================================================
# 10. 输出CSV
# ============================================================

def write_csv(
    output_path: Path,
    table_name: str,
    rows: List[Dict[str, Any]],
) -> None:
    """
    输出UTF-8 BOM格式CSV。

    使用Excel打开时，中文不会乱码。
    """
    headers = TABLE_HEADERS[table_name]

    with output_path.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=headers,
            extrasaction="ignore",
        )

        writer.writeheader()

        for row in rows:
            writer.writerow(
                {
                    field: (
                        ""
                        if row.get(field) is None
                        else row.get(field)
                    )
                    for field in headers
                }
            )


# ============================================================
# 11. 输出简单校验报告
# ============================================================

def build_summary(
    input_path: Path,
    output_dir: Path,
    tables: Dict[str, List[Dict[str, Any]]],
) -> Dict[str, Any]:
    """生成转换摘要。"""
    empty_counts = {}

    for table_name, rows in tables.items():
        headers = TABLE_HEADERS[table_name]

        empty_counts[table_name] = {
            field: sum(
                1
                for row in rows
                if row.get(field) in [None, ""]
            )
            for field in headers
        }

    return {
        "输入文件": str(input_path.resolve()),
        "输出目录": str(output_dir.resolve()),
        "输出表格行数": {
            table_name: len(rows)
            for table_name, rows in tables.items()
        },
        "各字段空值数量": empty_counts,
        "说明": (
            "本脚本只使用Python标准库，"
            "不包含artifact_tool、openpyxl或pandas。"
        ),
    }


# ============================================================
# 12. 主程序
# ============================================================

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "将LLM输出JSON转换为"
            "subscription_flow、share_transfer_flow和"
            "equity_snapshot三张CSV表。"
        )
    )

    parser.add_argument(
        "--input",
        required=True,
        help="LLM输出JSON文件路径",
    )

    parser.add_argument(
        "--output-dir",
        required=True,
        help="三张CSV表输出目录",
    )

    args = parser.parse_args()

    input_path = Path(args.input)
    output_dir = Path(args.output_dir)

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    # 打印实际运行的脚本，便于确认没有运行旧脚本。
    print("当前运行脚本：{}".format(Path(__file__).resolve()))
    print("Python解释器：{}".format(sys.executable))
    print("-" * 70)

    data = load_json_file(input_path)
    raw_tables = extract_raw_tables(data)

    final_tables = {}

    for table_name in TABLE_HEADERS:
        rows = normalize_table_rows(
            table_name,
            raw_tables.get(table_name, []),
        )

        rows = sort_table_rows(
            table_name,
            rows,
        )

        final_tables[table_name] = rows

        output_path = output_dir / "{}.csv".format(table_name)

        write_csv(
            output_path,
            table_name,
            rows,
        )

        print(
            "{}：{}行".format(
                table_name,
                len(rows),
            )
        )
        print("输出文件：{}".format(output_path.resolve()))
        print("-" * 70)

    summary = build_summary(
        input_path,
        output_dir,
        final_tables,
    )

    summary_path = output_dir / "09_conversion_summary.json"

    summary_path.write_text(
        json.dumps(
            summary,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("三张CSV表生成完成。")
    print("转换摘要：{}".format(summary_path.resolve()))
    print("CSV文件可直接使用Excel打开。")


if __name__ == "__main__":
    try:
        main()

    except Exception as error:
        print("\n程序执行失败：", file=sys.stderr)
        print(str(error), file=sys.stderr)
        sys.exit(1)