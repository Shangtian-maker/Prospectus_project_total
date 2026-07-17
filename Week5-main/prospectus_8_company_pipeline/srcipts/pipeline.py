from __future__ import annotations
from pathlib import Path
from typing import Dict, Any, List
import time
import traceback

from .utils import ensure_dir, sha256_file, sha256_json, read_json, write_json
from .pdf_parser import PDFParser
from .segmenter import locate_segments, split_segment
from .rule_extractor import extract_rule_candidates
from .llm_extractor import LLMExtractor
from .normalizer import normalize_record, deduplicate, aliases_to_map
from .validator import schema_validate, business_validate
from .crosscheck import load_gold, compare
from .exporter import export_workbook

class ProspectusPipeline:
    def __init__(self, project_root: Path, config: Dict[str, Any], schema: Dict[str, Any], logger):
        self.root = project_root
        self.config = config
        self.schema = schema
        self.logger = logger
        self.pipeline_cfg = config.get("pipeline", {})
        self.llm = LLMExtractor(self.pipeline_cfg.get("llm", {}), schema)

    def _manifest_hash(self, company: Dict[str, Any], pdf_path: Path) -> str:
        return sha256_json({
            "pdf_sha256": sha256_file(pdf_path),
            "company": company,
            "pipeline": self.pipeline_cfg,
            "schema": self.schema,
        })

    def run_company(self, company: Dict[str, Any]) -> Dict[str, Any]:
        started = time.time()
        cid = company["company_id"]
        pdf_path = (self.root / company["pdf_file"]).resolve()
        out_dir = ensure_dir(self.root / "output" / cid)
        tmp_dir = ensure_dir(self.root / "data" / "intermediate" / cid)
        manifest_path = tmp_dir / "manifest.json"
        result_json = out_dir / "extracted.json"

        if not pdf_path.exists():
            return self._summary(company, "FAILED", started, error=f"PDF不存在：{pdf_path}")

        current_hash = self._manifest_hash(company, pdf_path)
        if self.pipeline_cfg.get("skip_unchanged", True) and manifest_path.exists() and result_json.exists():
            old = read_json(manifest_path)
            if old.get("hash") == current_hash:
                self.logger.info("[%s] 输入未变化，跳过重新抽取", cid)
                data = read_json(result_json)
                issues = read_json(out_dir / "validation_issues.json")
                return self._summary(company, "SKIPPED", started, data=data, issues=issues)

        try:
            self.logger.info("[%s] 1/7 PDF解析", cid)
            parser = PDFParser(
                use_ocr=bool(self.pipeline_cfg.get("use_ocr", False)),
                min_page_text_chars=int(self.pipeline_cfg.get("min_page_text_chars", 80))
            )
            pages = parser.parse(pdf_path)
            write_json(tmp_dir / "pages.json", [p.to_dict() for p in pages])

            self.logger.info("[%s] 2/7 章节定位与切块", cid)
            segments = locate_segments(
                pages, padding_pages=int(self.pipeline_cfg.get("section_padding_pages", 2))
            )
            chunks = []
            for seg in segments:
                chunks.extend(split_segment(
                    seg,
                    chunk_chars=int(self.pipeline_cfg.get("chunk_chars", 12000)),
                    overlap_chars=int(self.pipeline_cfg.get("chunk_overlap_chars", 800))
                ))
            write_json(tmp_dir / "segments.json", [s.to_dict() for s in chunks])

            self.logger.info("[%s] 3/7 结构化抽取", cid)
            merged = {"capital_increase": [], "equity_transfer": [], "equity_snapshot": []}
            for chunk in chunks:
                if chunk.section not in {"equity_evolution", "shareholders"}:
                    continue
                if self.llm.enabled:
                    part = self.llm.extract(company, chunk.section, chunk.text)
                else:
                    part = extract_rule_candidates(chunk.text, cid)
                for table in merged:
                    merged[table].extend(part.get(table, []))

            self.logger.info("[%s] 4/7 归一化与去重", cid)
            alias_map = aliases_to_map(company)
            normalized = {
                "company": {
                    "company_id": cid,
                    "company_name": company["company_name"],
                    "aliases": company.get("aliases", []),
                    "source_pdf": str(pdf_path.name),
                },
                "capital_increase": [
                    normalize_record(r, "capital_increase", alias_map)
                    for r in merged["capital_increase"]
                ],
                "equity_transfer": [
                    normalize_record(r, "equity_transfer", alias_map)
                    for r in merged["equity_transfer"]
                ],
                "equity_snapshot": [
                    normalize_record(r, "equity_snapshot", alias_map)
                    for r in merged["equity_snapshot"]
                ],
                "metadata": {
                    "page_count": len(pages),
                    "ocr_page_count": sum(1 for p in pages if p.used_ocr),
                    "llm_enabled": self.llm.enabled
                }
            }
            normalized["capital_increase"] = deduplicate(
                normalized["capital_increase"], ("date", "subscriber", "source_page")
            )
            normalized["equity_transfer"] = deduplicate(
                normalized["equity_transfer"], ("date", "transferor", "transferee", "source_page")
            )
            normalized["equity_snapshot"] = deduplicate(
                normalized["equity_snapshot"], ("date", "shareholder_name", "source_page")
            )

            # 去重后重编ID，确保稳定、连续。
            for i, r in enumerate(normalized["capital_increase"], 1):
                r["event_id"] = f"{cid}_CI_{i:04d}"
            for i, r in enumerate(normalized["equity_transfer"], 1):
                r["event_id"] = f"{cid}_ET_{i:04d}"
            for i, r in enumerate(normalized["equity_snapshot"], 1):
                r["snapshot_id"] = f"{cid}_ES_{i:04d}"

            self.logger.info("[%s] 5/7 Schema与业务校验", cid)
            issues = schema_validate(normalized, self.schema) + business_validate(normalized)

            self.logger.info("[%s] 6/7 Gold Cross-check", cid)
            crosscheck_rows = None
            gold_file = company.get("gold_file")
            if gold_file:
                gold_path = (self.root / gold_file).resolve()
                if gold_path.exists():
                    crosscheck_rows = compare(normalized, load_gold(gold_path))
                else:
                    issues.append({
                        "level": "WARN", "rule": "GOLD_NOT_FOUND",
                        "message": f"Gold文件不存在：{gold_path}"
                    })

            self.logger.info("[%s] 7/7 导出JSON、Excel、校验结果", cid)
            write_json(result_json, normalized)
            write_json(out_dir / "validation_issues.json", issues)
            if crosscheck_rows is not None:
                write_json(out_dir / "crosscheck.json", crosscheck_rows)
            export_workbook(
                normalized, issues, out_dir / f"{cid}_prospectus_result.xlsx",
                crosscheck=crosscheck_rows
            )
            write_json(manifest_path, {"hash": current_hash})
            return self._summary(company, "SUCCESS", started, normalized, issues, crosscheck_rows)

        except Exception as exc:
            self.logger.error("[%s] 处理失败：%s\n%s", cid, exc, traceback.format_exc())
            return self._summary(company, "FAILED", started, error=str(exc))

    @staticmethod
    def _summary(company, status, started, data=None, issues=None, crosscheck=None, error=None):
        data = data or {}
        issues = issues or []
        crosscheck = crosscheck or []
        return {
            "company_id": company.get("company_id"),
            "company_name": company.get("company_name"),
            "status": status,
            "capital_increase_count": len(data.get("capital_increase", [])),
            "equity_transfer_count": len(data.get("equity_transfer", [])),
            "equity_snapshot_count": len(data.get("equity_snapshot", [])),
            "error_count": sum(1 for x in issues if x.get("level") == "ERROR"),
            "warning_count": sum(1 for x in issues if x.get("level") == "WARN"),
            "crosscheck_diff_count": sum(1 for x in crosscheck if x.get("result") in {
                "DIFF", "UNMATCHED_EXTRACTED", "MISSING_EXTRACTED"
            }),
            "elapsed_seconds": round(time.time() - started, 2),
            "error": error or ""
        }
