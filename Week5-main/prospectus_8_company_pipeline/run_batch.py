from __future__ import annotations
from pathlib import Path
import argparse
import yaml

from src.utils import read_json, setup_logger
from src.pipeline import ProspectusPipeline
from src.exporter import export_batch_summary

def main():
    parser = argparse.ArgumentParser(description="批量处理8家公司招股书")
    parser.add_argument("--config", default="config/companies.yaml")
    parser.add_argument("--only", nargs="*", default=None,
                        help="只处理指定company_id，例如 --only company_01 company_03")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent
    with (root / args.config).open("r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    schema = read_json(root / "config" / "schema.json")
    logger = setup_logger(root / "logs" / "pipeline.log")
    pipeline = ProspectusPipeline(root, config, schema, logger)

    companies = config.get("companies", [])
    if args.only:
        wanted = set(args.only)
        companies = [c for c in companies if c.get("company_id") in wanted]

    summaries = []
    for company in companies:
        summaries.append(pipeline.run_company(company))

    export_batch_summary(summaries, root / "output" / "batch_summary.xlsx")
    success = sum(1 for x in summaries if x["status"] in {"SUCCESS", "SKIPPED"})
    failed = sum(1 for x in summaries if x["status"] == "FAILED")
    print(f"完成：成功/跳过 {success} 家，失败 {failed} 家。")
    print(f"汇总文件：{root / 'output' / 'batch_summary.xlsx'}")

if __name__ == "__main__":
    main()
