import json
from pathlib import Path
import pandas as pd

# 输入目录：所有公司 JSONL 文件所在路径
jsonl_dir = Path("week2_jsonl")
# 输出目录：生成 Excel 文件
excel_dir = Path("week2_excel")
excel_dir.mkdir(parents=True, exist_ok=True)

# 循环处理目录下所有 JSONL 文件
for jsonl_file in jsonl_dir.glob("*_extracted_records.jsonl"):
    records = []
    with jsonl_file.open("r", encoding="utf-8") as f:
        for line in f:
            records.append(json.loads(line.strip()))

    if not records:
        continue

    # 分两类
    subscription_records = [r for r in records if r["record_type"] == "subscription_flow"]
    equity_records = [r for r in records if r["record_type"] == "equity_snapshot"]

    # 转 DataFrame
    df_sub = pd.DataFrame(subscription_records)
    df_eq = pd.DataFrame(equity_records)

    # 输出 Excel
    excel_file = excel_dir / f"{jsonl_file.stem}.xlsx"
    with pd.ExcelWriter(excel_file, engine="openpyxl") as writer:
        df_sub.to_excel(writer, sheet_name="subscription_flow", index=False)
        df_eq.to_excel(writer, sheet_name="equity_snapshot", index=False)

    print(f"已生成 Excel 文件: {excel_file}")