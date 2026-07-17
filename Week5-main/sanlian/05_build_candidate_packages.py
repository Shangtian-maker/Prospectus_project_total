import argparse
import json
import re
import shutil
from pathlib import Path
from typing import Any


# =========================================================
# 事件关键词
# 用于检查候选包内实际包含哪些事件信息，
# 同时发现可能被LLM事件索引遗漏的页面
# =========================================================

EVENT_KEYWORDS = {
    "公司设立": [
        "设立",
        "成立",
        "发起设立",
        "初始出资",
    ],
    "增资": [
        "增资",
        "增加注册资本",
        "新增注册资本",
        "认缴新增出资",
        "认购新增股份",
        "资本公积转增",
    ],
    "减资": [
        "减资",
        "减少注册资本",
        "回购注销",
    ],
    "股权转让": [
        "股权转让",
        "股份转让",
        "转让股权",
        "转让股份",
        "受让",
        "转让价款",
    ],
    "整体变更": [
        "整体变更",
        "整体改制",
        "变更为股份有限公司",
        "折股",
        "净资产折股",
    ],
    "股权代持": [
        "股权代持",
        "股份代持",
        "委托持股",
        "解除代持",
        "还原代持",
    ],
}


def normalize_text(value: Any) -> str:
    """
    合并多余空格、换行和全角空格。
    """
    if value is None:
        return ""

    text = str(value).replace("\u3000", " ")

    return re.sub(
        r"\s+",
        " ",
        text,
    ).strip()


def collect_strings(value: Any) -> list[str]:
    """
    递归提取list、dict中的字符串。
    """
    output = []

    if isinstance(value, str):
        value = normalize_text(value)

        if value:
            output.append(value)

    elif isinstance(value, list):
        for item in value:
            output.extend(
                collect_strings(item)
            )

    elif isinstance(value, dict):
        for item in value.values():
            output.extend(
                collect_strings(item)
            )

    return output


def get_block_text(block: dict) -> str:
    """
    从MinerU内容块中提取正文、表格和图片说明。
    """
    keys = [
        "text",
        "content",
        "table_caption",
        "table_body",
        "table_footnote",
        "image_caption",
        "image_footnote",
        "list_items",
    ]

    parts = []

    for key in keys:
        if key in block:
            parts.extend(
                collect_strings(block[key])
            )

    unique_parts = []
    seen = set()

    for part in parts:
        part = normalize_text(part)

        if part and part not in seen:
            seen.add(part)
            unique_parts.append(part)

    return "\n".join(unique_parts)


def get_image_paths(block: dict) -> list[str]:
    """
    提取MinerU内容块中的图片路径。
    """
    paths = []

    for key in [
        "img_path",
        "image_path",
    ]:
        value = block.get(key)

        if isinstance(value, str):
            value = value.strip()

            if value:
                paths.append(value)

        elif isinstance(value, list):
            for item in value:
                if isinstance(item, str):
                    item = item.strip()

                    if item:
                        paths.append(item)

    return list(dict.fromkeys(paths))


def find_content_list(
    mineru_root: Path,
    keyword: str,
) -> Path:
    """
    查找MinerU生成的*_content_list.json。
    """
    files = list(
        mineru_root.rglob(
            "*_content_list.json"
        )
    )

    if keyword:
        keyword_lower = keyword.lower()

        matched = [
            path
            for path in files
            if keyword_lower
            in path.name.lower()
            or keyword_lower
            in str(path.parent).lower()
        ]

        if matched:
            files = matched

    if not files:
        raise FileNotFoundError(
            f"在以下目录中未找到"
            f"*_content_list.json：\n"
            f"{mineru_root}"
        )

    # 多个文件时使用最近修改的一个
    return max(
        files,
        key=lambda path: path.stat().st_mtime,
    )


def load_json(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(
            f"文件不存在：{path}"
        )

    with path.open(
        "r",
        encoding="utf-8",
    ) as file:
        return json.load(file)


def save_json(
    path: Path,
    data: Any,
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with path.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            data,
            file,
            ensure_ascii=False,
            indent=2,
        )


def load_content_list(path: Path) -> list[dict]:
    """
    兼容不同content_list.json顶层结构。
    """
    data = load_json(path)

    if isinstance(data, list):
        return data

    if isinstance(data, dict):
        for key in [
            "content_list",
            "data",
            "items",
            "result",
        ]:
            value = data.get(key)

            if isinstance(value, list):
                return value

    raise ValueError(
        "无法识别content_list.json结构。"
    )


def load_event_index(path: Path) -> list[dict]:
    """
    读取05_llm_event_index.json。

    兼容：
    1. 顶层直接为数组；
    2. {"events": [...]}；
    3. {"event_index": [...]}。
    """
    data = load_json(path)

    if isinstance(data, list):
        events = data

    elif isinstance(data, dict):
        events = (
            data.get("events")
            or data.get("event_index")
            or data.get("items")
            or []
        )

    else:
        events = []

    if not events:
        raise ValueError(
            "05_llm_event_index.json中"
            "没有读取到事件。"
        )

    return events


def load_section_range(
    path: Path,
    section_group: str,
) -> dict:
    data = load_json(path)

    if isinstance(data, list):
        sections = data
    else:
        sections = data.get(
            "sections",
            [],
        )

    for section in sections:
        if (
            section.get("section_group")
            == section_group
        ):
            return section

    raise ValueError(
        f"未找到章节：{section_group}"
    )


def load_page_mapping(
    path: Path | None,
) -> dict[int, int]:
    """
    读取：
    目标PDF页码 → 原始PDF页码
    """
    if path is None:
        return {}

    if not path.exists():
        return {}

    data = load_json(path)

    mapping = {}

    for item in data.get(
        "page_mapping",
        [],
    ):
        target_page = item.get(
            "target_pdf_page"
        )

        original_page = item.get(
            "original_pdf_page"
        )

        if (
            target_page is not None
            and original_page is not None
        ):
            mapping[int(target_page)] = int(
                original_page
            )

    return mapping


def parse_pages(value: Any) -> list[int]:
    """
    兼容多种页码格式：

    [30, 31]
    30
    "30-31"
    "30,31"
    "第30至31页"
    """
    pages = []

    if value is None:
        return pages

    if isinstance(value, int):
        return [value]

    if isinstance(value, float):
        return [int(value)]

    if isinstance(value, list):
        for item in value:
            pages.extend(
                parse_pages(item)
            )

        return sorted(set(pages))

    text = str(value)

    # 先识别范围，例如30-32、30至32
    range_matches = re.findall(
        r"(\d+)\s*[-—~至到]\s*(\d+)",
        text,
    )

    for start, end in range_matches:
        start_int = int(start)
        end_int = int(end)

        if end_int >= start_int:
            pages.extend(
                range(
                    start_int,
                    end_int + 1,
                )
            )

    # 再识别单独数字
    numbers = re.findall(
        r"\d+",
        text,
    )

    pages.extend(
        int(number)
        for number in numbers
    )

    return sorted(set(pages))


def build_records(
    content_items: list[dict],
) -> list[dict]:
    """
    将MinerU内容块转换为统一结构。
    """
    records = []

    for order, item in enumerate(
        content_items
    ):
        if not isinstance(item, dict):
            continue

        try:
            page_idx = int(
                item.get("page_idx")
            )
        except (TypeError, ValueError):
            continue

        records.append(
            {
                "order": order,
                "page_idx": page_idx,
                "pdf_page": page_idx + 1,
                "type": str(
                    item.get(
                        "type",
                        "unknown",
                    )
                ),
                "text_level": item.get(
                    "text_level"
                ),
                "text": get_block_text(item),
                "image_paths": get_image_paths(
                    item
                ),
                "raw_block": item,
            }
        )

    if not records:
        raise ValueError(
            "content_list中没有读取到"
            "带page_idx的内容块。"
        )

    return records


def locate_pages_by_evidence(
    evidence: str,
    records: list[dict],
) -> list[int]:
    """
    当事件索引没有填写页码时，
    尝试使用evidence_start定位页面。
    """
    evidence = normalize_text(evidence)

    if len(evidence) < 6:
        return []

    search_text = re.sub(
        r"\s+",
        "",
        evidence,
    )

    # evidence较长时，只取前30个字符
    search_text = search_text[:30]

    pages = []

    for record in records:
        block_text = re.sub(
            r"\s+",
            "",
            record["text"],
        )

        if search_text in block_text:
            pages.append(
                record["pdf_page"]
            )

    return sorted(set(pages))


def resolve_original_pages(
    event: dict,
    page_mapping: dict[int, int],
    records: list[dict],
) -> list[int]:
    """
    确定事件在原始PDF中的页码。

    优先级：
    1. original_pdf_pages；
    2. source_pdf_pages；
    3. target_pdf_pages映射；
    4. evidence_start文本定位。
    """
    pages = parse_pages(
        event.get("original_pdf_pages")
    )

    if not pages:
        pages = parse_pages(
            event.get("source_pdf_pages")
        )

    if not pages:
        target_pages = parse_pages(
            event.get("target_pdf_pages")
        )

        pages = [
            page_mapping[page]
            for page in target_pages
            if page in page_mapping
        ]

    if not pages:
        pages = locate_pages_by_evidence(
            event.get(
                "evidence_start",
                "",
            ),
            records,
        )

    return sorted(set(pages))


def expand_pages(
    core_pages: list[int],
    context_pages: int,
    section_start: int,
    section_end: int,
) -> list[int]:
    """
    在事件核心页前后增加上下文页，
    并限制在目标章节范围内。
    """
    expanded = set()

    for page in core_pages:
        for candidate in range(
            page - context_pages,
            page + context_pages + 1,
        ):
            if (
                section_start
                <= candidate
                <= section_end
            ):
                expanded.add(candidate)

    return sorted(expanded)


def detect_keyword_hits(
    text: str,
) -> dict[str, list[str]]:
    """
    返回候选包中命中的事件关键词。
    """
    result = {}

    for category, keywords in (
        EVENT_KEYWORDS.items()
    ):
        hits = [
            keyword
            for keyword in keywords
            if keyword in text
        ]

        if hits:
            result[category] = hits

    return result


def resolve_image_path(
    image_path: str,
    content_list_path: Path,
    mineru_root: Path,
) -> Path | None:
    """
    尝试把MinerU记录的相对图片路径
    转换为真实本地路径。
    """
    path = Path(image_path)

    if path.is_absolute() and path.exists():
        return path

    candidates = [
        content_list_path.parent / path,
        mineru_root / path,
        content_list_path.parent
        / "images"
        / path.name,
    ]

    for candidate in candidates:
        if candidate.exists():
            return candidate

    # 最后按文件名搜索
    matches = list(
        mineru_root.rglob(path.name)
    )

    if matches:
        return matches[0]

    return None


def safe_name(text: str) -> str:
    text = normalize_text(text)

    text = re.sub(
        r'[\\/:*?"<>|]',
        "_",
        text,
    )

    text = re.sub(
        r"\s+",
        "_",
        text,
    )

    return text[:50] or "event"


def write_markdown_preview(
    package: dict,
    path: Path,
) -> None:
    """
    生成人工可读的候选事件包预览。
    """
    lines = [
        f'# {package["candidate_id"]} '
        f'{package["event_title"]}',
        "",
        f'- event_id：{package["event_id"]}',
        f'- 事件类型提示：{package["event_type_hint"]}',
        f'- 日期提示：{package["event_date_hint"]}',
        (
            f'- 核心原始PDF页：'
            f'{package["core_original_pdf_pages"]}'
        ),
        (
            f'- 上下文原始PDF页：'
            f'{package["context_original_pdf_pages"]}'
        ),
        (
            f'- 小标题：'
            f'{package["subsection_title"]}'
        ),
        "",
        "## 关键词命中",
        "",
        "```json",
        json.dumps(
            package["keyword_hits"],
            ensure_ascii=False,
            indent=2,
        ),
        "```",
        "",
        "## 候选事件正文",
        "",
        package["text"],
        "",
        "## 表格内容",
        "",
    ]

    if package["tables"]:
        for table in package["tables"]:
            lines.extend(
                [
                    (
                        f'### 原始PDF第'
                        f'{table["pdf_page"]}页'
                    ),
                    "",
                    table["text"],
                    "",
                ]
            )
    else:
        lines.append("未提取到独立表格块。")

    lines.extend(
        [
            "",
            "## 关联图片",
            "",
        ]
    )

    if package["image_paths"]:
        for image_path in package[
            "image_paths"
        ]:
            lines.append(
                f"- {image_path}"
            )
    else:
        lines.append("未提取到关联图片路径。")

    path.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )


def create_event_pdf(
    source_pdf_path: Path,
    selected_pages: list[int],
    output_path: Path,
) -> None:
    """
    从原始PDF中提取候选事件对应页面。

    selected_pages使用PDF物理页码，从1开始。
    """
    try:
        import pymupdf
    except ImportError:
        try:
            import fitz as pymupdf
        except ImportError as error:
            raise RuntimeError(
                "需要安装PyMuPDF："
                "pip install pymupdf"
            ) from error

    source_doc = pymupdf.open(
        str(source_pdf_path)
    )

    target_doc = pymupdf.open()

    total_pages = source_doc.page_count

    for page in sorted(
        set(selected_pages)
    ):
        if 1 <= page <= total_pages:
            target_doc.insert_pdf(
                source_doc,
                from_page=page - 1,
                to_page=page - 1,
            )

    if target_doc.page_count > 0:
        target_doc.save(
            str(output_path)
        )

    target_doc.close()
    source_doc.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "根据05_llm_event_index.json和"
            "MinerU content_list.json"
            "生成候选事件包。"
        )
    )

    parser.add_argument(
        "--mineru-output",
        required=True,
        help="MinerU输出根目录",
    )

    parser.add_argument(
        "--event-index",
        required=True,
        help="05_llm_event_index.json路径",
    )

    parser.add_argument(
        "--section-ranges",
        required=True,
        help="03_section_ranges.json路径",
    )

    parser.add_argument(
        "--page-mapping",
        default=None,
        help="目标PDF页码映射JSON，可选",
    )

    parser.add_argument(
        "--source-pdf",
        default=None,
        help="完整原始PDF路径，可选",
    )

    parser.add_argument(
        "--result-dir",
        required=True,
        help="候选事件包输出目录",
    )

    parser.add_argument(
        "--keyword",
        default="三联锻造",
        help="查找content_list文件的关键词",
    )

    parser.add_argument(
        "--section-group",
        default="股本演变主章节",
        help="目标章节分组名称",
    )

    parser.add_argument(
        "--context-pages",
        type=int,
        default=1,
        help="事件核心页前后扩展页数",
    )

    parser.add_argument(
        "--copy-assets",
        action="store_true",
        help="复制候选事件关联图片",
    )

    args = parser.parse_args()

    mineru_root = Path(
        args.mineru_output
    )

    event_index_path = Path(
        args.event_index
    )

    section_ranges_path = Path(
        args.section_ranges
    )

    result_dir = Path(
        args.result_dir
    )

    result_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    page_mapping_path = (
        Path(args.page_mapping)
        if args.page_mapping
        else None
    )

    source_pdf_path = (
        Path(args.source_pdf)
        if args.source_pdf
        else None
    )

    content_list_path = find_content_list(
        mineru_root,
        args.keyword,
    )

    content_items = load_content_list(
        content_list_path
    )

    records = build_records(
        content_items
    )

    events = load_event_index(
        event_index_path
    )

    section = load_section_range(
        section_ranges_path,
        args.section_group,
    )

    page_mapping = load_page_mapping(
        page_mapping_path
    )

    section_start = int(
        section["pdf_page_start"]
    )

    section_end = int(
        section["pdf_page_end"]
    )

    print("=" * 70)
    print(
        f"content_list：{content_list_path}"
    )
    print(
        f"事件数量：{len(events)}"
    )
    print(
        f"目标章节范围："
        f"{section_start}-{section_end}"
    )

    package_index = []
    all_core_pages = set()
    skipped_events = []

    for index, event in enumerate(
        events,
        start=1,
    ):
        event_id = normalize_text(
            event.get("event_id")
        ) or f"E{index:03d}"

        candidate_id = f"C{index:03d}"

        event_title = normalize_text(
            event.get("event_title")
        ) or event_id

        event_type = normalize_text(
            event.get("event_type")
        ) or "待判断"

        core_pages = resolve_original_pages(
            event,
            page_mapping,
            records,
        )

        # 仅保留目标章节内的页码
        core_pages = [
            page
            for page in core_pages
            if section_start
            <= page
            <= section_end
        ]

        if not core_pages:
            skipped_events.append(
                {
                    "event_id": event_id,
                    "event_title": event_title,
                    "reason": (
                        "无法确定目标章节内的"
                        "原始PDF页码"
                    ),
                }
            )

            print(
                f"跳过 {event_id}："
                "无法确定页码"
            )

            continue

        all_core_pages.update(
            core_pages
        )

        context_pages = expand_pages(
            core_pages,
            args.context_pages,
            section_start,
            section_end,
        )

        selected_records = [
            record
            for record in records
            if record["pdf_page"]
            in context_pages
        ]

        text_parts = []
        table_items = []
        original_image_paths = []

        for record in selected_records:
            if record["text"]:
                text_parts.append(
                    (
                        f'[原始PDF第'
                        f'{record["pdf_page"]}页]'
                        f'[{record["type"]}]\n'
                        f'{record["text"]}'
                    )
                )

            if (
                record["type"].lower()
                == "table"
            ):
                table_items.append(
                    {
                        "pdf_page": (
                            record["pdf_page"]
                        ),
                        "text": record["text"],
                    }
                )

            original_image_paths.extend(
                record["image_paths"]
            )

        original_image_paths = list(
            dict.fromkeys(
                original_image_paths
            )
        )

        full_text = "\n\n".join(
            text_parts
        )

        keyword_hits = detect_keyword_hits(
            full_text
        )

        folder_name = (
            f"{candidate_id}_{event_id}_"
            f"{safe_name(event_title)}"
        )

        package_dir = (
            result_dir / folder_name
        )

        package_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        saved_image_paths = []
        missing_image_paths = []

        for image_path in (
            original_image_paths
        ):
            resolved = resolve_image_path(
                image_path,
                content_list_path,
                mineru_root,
            )

            if resolved is None:
                missing_image_paths.append(
                    image_path
                )
                continue

            if args.copy_assets:
                assets_dir = (
                    package_dir / "assets"
                )

                assets_dir.mkdir(
                    parents=True,
                    exist_ok=True,
                )

                destination = (
                    assets_dir / resolved.name
                )

                if not destination.exists():
                    shutil.copy2(
                        resolved,
                        destination,
                    )

                saved_image_paths.append(
                    str(destination)
                )
            else:
                saved_image_paths.append(
                    str(resolved)
                )

        package = {
            "candidate_id": candidate_id,
            "event_id": event_id,

            "event_type_hint": event_type,

            "event_title": event_title,

            "event_date_hint": event.get(
                "event_date"
            ),

            "section_group": (
                args.section_group
            ),

            "section_title": section.get(
                "matched_title"
            ),

            "subsection_title": event.get(
                "subsection_title"
            ),

            "core_original_pdf_pages": (
                core_pages
            ),

            "context_original_pdf_pages": (
                context_pages
            ),

            "target_pdf_pages_from_index": (
                parse_pages(
                    event.get(
                        "target_pdf_pages"
                    )
                )
            ),

            "participants_hint": event.get(
                "participants",
                [],
            ),

            "evidence_start_hint": (
                event.get(
                    "evidence_start"
                )
            ),

            "contains_table_hint": (
                event.get(
                    "contains_table"
                )
            ),

            "contains_image_hint": (
                event.get(
                    "contains_image"
                )
            ),

            "needs_further_review_hint": (
                event.get(
                    "needs_further_review"
                )
            ),

            "keyword_hits": keyword_hits,

            "text": full_text,

            "tables": table_items,

            "image_paths": saved_image_paths,

            "missing_image_paths": (
                missing_image_paths
            ),

            "content_block_count": len(
                selected_records
            ),

            "text_length": len(
                full_text
            ),

            "source_content_list": str(
                content_list_path
            ),

            "event_index_record": event,

            "next_task": (
                "将本候选事件包单独送入LLM，"
                "只抽取该事件的标准化字段，"
                "不要混入其他事件。"
            ),
        }

        json_path = (
            package_dir
            / f"{candidate_id}.json"
        )

        markdown_path = (
            package_dir
            / f"{candidate_id}.md"
        )

        save_json(
            json_path,
            package,
        )

        write_markdown_preview(
            package,
            markdown_path,
        )

        event_pdf_path = None

        if (
            source_pdf_path is not None
            and source_pdf_path.exists()
        ):
            event_pdf_path = (
                package_dir
                / f"{candidate_id}.pdf"
            )

            create_event_pdf(
                source_pdf_path,
                context_pages,
                event_pdf_path,
            )

        package_index.append(
            {
                "candidate_id": (
                    candidate_id
                ),
                "event_id": event_id,
                "event_type_hint": (
                    event_type
                ),
                "event_title": (
                    event_title
                ),
                "core_original_pdf_pages": (
                    core_pages
                ),
                "context_original_pdf_pages": (
                    context_pages
                ),
                "json_path": str(
                    json_path
                ),
                "markdown_path": str(
                    markdown_path
                ),
                "pdf_path": (
                    str(event_pdf_path)
                    if event_pdf_path
                    else None
                ),
                "image_count": len(
                    saved_image_paths
                ),
                "table_count": len(
                    table_items
                ),
                "text_length": len(
                    full_text
                ),
            }
        )

        print(
            f"生成 {candidate_id}："
            f"{event_title}，"
            f"核心页{core_pages}，"
            f"上下文页{context_pages}"
        )

    # =====================================================
    # 生成候选包总索引
    # =====================================================

    index_result = {
        "event_index_path": str(
            event_index_path
        ),

        "content_list_path": str(
            content_list_path
        ),

        "section_group": (
            args.section_group
        ),

        "section_original_pdf_range": {
            "start": section_start,
            "end": section_end,
        },

        "context_pages": (
            args.context_pages
        ),

        "input_event_count": len(
            events
        ),

        "generated_package_count": len(
            package_index
        ),

        "skipped_event_count": len(
            skipped_events
        ),

        "packages": package_index,

        "skipped_events": (
            skipped_events
        ),
    }

    save_json(
        result_dir
        / "06_candidate_packages_index.json",
        index_result,
    )

    # =====================================================
    # 生成覆盖率检查报告
    #
    # 找出目标章节中：
    # 含事件关键词，但没有被05事件索引覆盖的页面
    # =====================================================

    uncovered_pages = []

    section_records = [
        record
        for record in records
        if section_start
        <= record["pdf_page"]
        <= section_end
    ]

    page_texts = {}

    for record in section_records:
        page_texts.setdefault(
            record["pdf_page"],
            [],
        )

        if record["text"]:
            page_texts[
                record["pdf_page"]
            ].append(record["text"])

    for page, texts in sorted(
        page_texts.items()
    ):
        page_text = "\n".join(texts)

        hits = detect_keyword_hits(
            page_text
        )

        if (
            hits
            and page not in all_core_pages
        ):
            uncovered_pages.append(
                {
                    "pdf_page": page,
                    "keyword_hits": hits,
                    "text_excerpt": (
                        normalize_text(
                            page_text
                        )[:500]
                    ),
                    "review_reason": (
                        "该页含事件关键词，"
                        "但未被05事件索引列为"
                        "任何事件的核心页面。"
                    ),
                }
            )

    coverage_report = {
        "section_original_pdf_range": {
            "start": section_start,
            "end": section_end,
        },

        "core_pages_covered_by_event_index": (
            sorted(all_core_pages)
        ),

        "uncovered_keyword_page_count": (
            len(uncovered_pages)
        ),

        "uncovered_keyword_pages": (
            uncovered_pages
        ),

        "interpretation": (
            "如果未覆盖页面确实包含独立事件，"
            "说明05_llm_event_index.json可能漏掉事件；"
            "应补充事件索引后重新运行本脚本。"
        ),
    }

    save_json(
        result_dir
        / "06_candidate_coverage_report.json",
        coverage_report,
    )

    print("\n处理完成：")
    print(
        f"候选事件包数量："
        f"{len(package_index)}"
    )
    print(
        f"跳过事件数量："
        f"{len(skipped_events)}"
    )
    print(
        f"待核验未覆盖页面："
        f"{len(uncovered_pages)}"
    )
    print(
        f"输出目录："
        f"{result_dir.resolve()}"
    )
    print("=" * 70)


if __name__ == "__main__":
    main()