import argparse
import json
import re
from pathlib import Path
from typing import Any


PAGE_BLOCK_PATTERN = re.compile(
    r"\[原始PDF第(\d+)页\]"
    r"\[[^\]]+\]\n"
    r"(.*?)"
    r"(?=\n\n\[原始PDF第\d+页\]|\Z)",
    re.DOTALL,
)


def load_json(path: Path) -> Any:
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


def normalize_text(text: Any) -> str:
    if text is None:
        return ""

    return re.sub(
        r"[ \t]+",
        " ",
        str(text),
    ).strip()


def find_candidate_files(
    candidate_dir: Path,
) -> list[Path]:
    """
    查找各候选事件目录中的Cxxx.json，
    排除总索引和覆盖率报告。
    """
    files = []

    for path in candidate_dir.rglob(
        "C*.json"
    ):
        if path.name.startswith(
            "C"
        ):
            files.append(path)

    return sorted(files)


def split_text_by_page(
    text: str,
) -> dict[int, list[str]]:
    """
    从候选包text字段中恢复：
    原始PDF页码 → 内容块列表。
    """
    page_blocks = {}

    for match in PAGE_BLOCK_PATTERN.finditer(
        text
    ):
        page = int(
            match.group(1)
        )

        content = normalize_text(
            match.group(2)
        )

        if not content:
            continue

        page_blocks.setdefault(
            page,
            [],
        )

        if content not in page_blocks[page]:
            page_blocks[page].append(
                content
            )

    return page_blocks


def add_unique(
    target: list,
    values: list,
) -> None:
    for value in values:
        if value not in target:
            target.append(value)


def estimate_event_size(
    event: dict,
    page_pool_map: dict,
) -> int:
    """
    估算单个事件需要读取的文本字符数。
    """
    total = 0

    for page in event.get(
        "context_original_pdf_pages",
        [],
    ):
        page_data = page_pool_map.get(
            int(page),
            {},
        )

        total += sum(
            len(block)
            for block in page_data.get(
                "text_blocks",
                [],
            )
        )

        total += sum(
            len(
                table.get(
                    "text",
                    "",
                )
            )
            for table in page_data.get(
                "tables",
                [],
            )
        )

    return total


def build_batches(
    candidate_events: list[dict],
    page_pool_map: dict,
    max_events: int,
    max_chars: int,
) -> list[list[dict]]:
    """
    按事件数和估算字符数自动分批。

    如果全部内容不大，只会生成一个批次。
    """
    batches = []
    current_batch = []
    current_chars = 0

    for event in candidate_events:
        event_chars = estimate_event_size(
            event,
            page_pool_map,
        )

        exceeds_event_limit = (
            len(current_batch) >= max_events
        )

        exceeds_char_limit = (
            current_batch
            and current_chars + event_chars
            > max_chars
        )

        if (
            exceeds_event_limit
            or exceeds_char_limit
        ):
            batches.append(
                current_batch
            )

            current_batch = []
            current_chars = 0

        current_batch.append(
            event
        )

        current_chars += event_chars

    if current_batch:
        batches.append(
            current_batch
        )

    return batches


def collect_batch_pages(
    events: list[dict],
) -> list[int]:
    pages = set()

    for event in events:
        pages.update(
            int(page)
            for page in event.get(
                "context_original_pdf_pages",
                []
            )
        )

    return sorted(pages)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "合并多个候选事件包，生成"
            "总候选事件包和自动分批文件。"
        )
    )

    parser.add_argument(
        "--candidate-dir",
        required=True,
        help="06_candidate_packages目录",
    )

    parser.add_argument(
        "--output-dir",
        required=True,
        help="总包输出目录",
    )

    parser.add_argument(
        "--document-id",
        default="unknown_document",
        help="公司名称或文档编号",
    )

    parser.add_argument(
        "--max-events",
        type=int,
        default=10,
        help="每批最多包含的事件数",
    )

    parser.add_argument(
        "--max-chars",
        type=int,
        default=100000,
        help="每批估算最大文本字符数",
    )

    args = parser.parse_args()

    candidate_dir = Path(
        args.candidate_dir
    )

    output_dir = Path(
        args.output_dir
    )

    if not candidate_dir.exists():
        raise FileNotFoundError(
            f"候选事件包目录不存在："
            f"{candidate_dir}"
        )

    candidate_files = find_candidate_files(
        candidate_dir
    )

    if not candidate_files:
        raise FileNotFoundError(
            "没有找到Cxxx.json候选事件包。"
        )

    page_pool_map = {}
    candidate_events = []
    section_title = None
    section_group = None

    for candidate_file in candidate_files:
        package = load_json(
            candidate_file
        )

        if section_title is None:
            section_title = package.get(
                "section_title"
            )

        if section_group is None:
            section_group = package.get(
                "section_group"
            )

        event = {
            "candidate_id": package.get(
                "candidate_id"
            ),

            "event_id": package.get(
                "event_id"
            ),

            "event_type_hint": package.get(
                "event_type_hint"
            ),

            "event_title": package.get(
                "event_title"
            ),

            "event_date_hint": package.get(
                "event_date_hint"
            ),

            "subsection_title": package.get(
                "subsection_title"
            ),

            "core_original_pdf_pages": (
                package.get(
                    "core_original_pdf_pages",
                    [],
                )
            ),

            "context_original_pdf_pages": (
                package.get(
                    "context_original_pdf_pages",
                    [],
                )
            ),

            "participants_hint": package.get(
                "participants_hint",
                [],
            ),

            "evidence_start_hint": package.get(
                "evidence_start_hint"
            ),

            "keyword_hits": package.get(
                "keyword_hits",
                {},
            ),

            "contains_table_hint": (
                package.get(
                    "contains_table_hint"
                )
            ),

            "contains_image_hint": (
                package.get(
                    "contains_image_hint"
                )
            ),

            "needs_further_review_hint": (
                package.get(
                    "needs_further_review_hint"
                )
            ),
        }

        candidate_events.append(
            event
        )

        page_blocks = split_text_by_page(
            package.get(
                "text",
                "",
            )
        )

        for page, blocks in (
            page_blocks.items()
        ):
            page_pool_map.setdefault(
                page,
                {
                    "original_pdf_page": page,
                    "text_blocks": [],
                    "tables": [],
                    "image_paths": [],
                },
            )

            add_unique(
                page_pool_map[page][
                    "text_blocks"
                ],
                blocks,
            )

        for table in package.get(
            "tables",
            [],
        ):
            page = table.get(
                "pdf_page"
            )

            if page is None:
                continue

            page = int(page)

            page_pool_map.setdefault(
                page,
                {
                    "original_pdf_page": page,
                    "text_blocks": [],
                    "tables": [],
                    "image_paths": [],
                },
            )

            if (
                table
                not in page_pool_map[page][
                    "tables"
                ]
            ):
                page_pool_map[page][
                    "tables"
                ].append(table)

        # 旧候选包没有保存图片对应页码，
        # 因此先将图片挂在事件层面。
        event["image_paths"] = package.get(
            "image_paths",
            [],
        )

    page_pool = [
        page_pool_map[page]
        for page in sorted(
            page_pool_map
        )
    ]

    all_pages = sorted(
        page_pool_map
    )

    master_package = {
        "document_id": args.document_id,

        "section_group": section_group,

        "section_title": section_title,

        "original_pdf_range": {
            "start": (
                min(all_pages)
                if all_pages
                else None
            ),

            "end": (
                max(all_pages)
                if all_pages
                else None
            ),
        },

        "event_count": len(
            candidate_events
        ),

        "page_count": len(
            page_pool
        ),

        "instructions": {
            "event_isolation": (
                "每个event_id必须独立判断，"
                "不得合并不同event_id。"
            ),

            "page_usage": (
                "每个事件主要依据其"
                "core_original_pdf_pages和"
                "context_original_pdf_pages。"
            ),

            "missing_values": (
                "无法确认的字段填写null，"
                "不得推测。"
            ),
        },

        "candidate_events": (
            candidate_events
        ),

        "page_pool": page_pool,
    }

    master_path = (
        output_dir
        / "06_master_candidate_package.json"
    )

    save_json(
        master_path,
        master_package,
    )

    # 自动生成批次
    batches = build_batches(
        candidate_events,
        page_pool_map,
        args.max_events,
        args.max_chars,
    )

    batch_dir = (
        output_dir
        / "batches"
    )

    batch_index = []

    for batch_number, events in enumerate(
        batches,
        start=1,
    ):
        batch_pages = collect_batch_pages(
            events
        )

        batch_page_pool = [
            page_pool_map[page]
            for page in batch_pages
            if page in page_pool_map
        ]

        batch_id = (
            f"B{batch_number:03d}"
        )

        batch_data = {
            "document_id": args.document_id,
            "batch_id": batch_id,

            "event_count": len(
                events
            ),

            "events": events,

            "page_pool": batch_page_pool,

            "output_requirement": (
                "必须为本批次每个event_id"
                "输出一条独立的标准化事件记录。"
            ),
        }

        batch_path = (
            batch_dir
            / f"{batch_id}.json"
        )

        save_json(
            batch_path,
            batch_data,
        )

        batch_index.append(
            {
                "batch_id": batch_id,

                "event_ids": [
                    event.get("event_id")
                    for event in events
                ],

                "event_count": len(
                    events
                ),

                "page_count": len(
                    batch_pages
                ),

                "batch_path": str(
                    batch_path
                ),
            }
        )

    save_json(
        output_dir
        / "06_batch_index.json",

        {
            "document_id": (
                args.document_id
            ),

            "master_package": str(
                master_path
            ),

            "total_event_count": len(
                candidate_events
            ),

            "batch_count": len(
                batches
            ),

            "max_events_per_batch": (
                args.max_events
            ),

            "max_chars_per_batch": (
                args.max_chars
            ),

            "batches": batch_index,
        },
    )

    print("=" * 70)
    print(
        f"候选事件数量："
        f"{len(candidate_events)}"
    )
    print(
        f"去重后页面数量："
        f"{len(page_pool)}"
    )
    print(
        f"总候选事件包："
        f"{master_path}"
    )
    print(
        f"自动批次数量："
        f"{len(batches)}"
    )
    print(
        f"批次目录："
        f"{batch_dir}"
    )
    print("=" * 70)


if __name__ == "__main__":
    main()