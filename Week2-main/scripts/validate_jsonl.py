import json
from pathlib import Path
import pandas as pd
import re

# 输入 JSONL 目录
jsonl_dir = Path("week2_jsonl")
# 输出日志目录
log_dir = Path("logs")
log_dir.mkdir(parents=True, exist_ok=True)

schema_log = []
cross_check_log = []

# t0 标识关键字
T0_KEYWORDS = ["t0", "报告期初", "设立时"]

# 遍历 JSONL 文件
for jsonl_file in jsonl_dir.glob("*_extracted_records.jsonl"):
    company_code = re.match(r"(\d+)_", jsonl_file.name).group(1)
    company_name = re.match(r"\d+_(.+?)_extracted", jsonl_file.name).group(1)
    
    with jsonl_file.open("r", encoding="utf-8") as f:
        records = [json.loads(line) for line in f if line.strip()]
    
    # 分两类记录
    subscription_records = [r for r in records if r["record_type"]=="subscription_flow"]
    equity_records = [r for r in records if r["record_type"]=="equity_snapshot"]
    
    # ====== 第1层校验：JSONL解析、record_type校验 ======
    for idx, r in enumerate(records, 1):
        row_no = idx
        # record_type合法性
        if r.get("record_type") not in ["subscription_flow", "equity_snapshot"]:
            schema_log.append({
                "company_code": company_code,
                "company_name": company_name,
                "jsonl_file": jsonl_file.name,
                "line_no": row_no,
                "record_type": r.get("record_type"),
                "check_item": "record_type合法性",
                "status": "fail",
                "message": "record_type必须是 subscription_flow 或 equity_snapshot"
            })
        else:
            schema_log.append({
                "company_code": company_code,
                "company_name": company_name,
                "jsonl_file": jsonl_file.name,
                "line_no": row_no,
                "record_type": r.get("record_type"),
                "check_item": "record_type合法性",
                "status": "pass",
                "message": ""
            })
    
    # ====== 第2层校验：字段、类型、必填项 ======
    for rec_type, rec_list, required_fields, numeric_fields, text_required in [
        ("subscription_flow", subscription_records,
         ["pdf_page","increase_date","subscriber","evidence_text","review_status"],
         ["subscribed_shares_10k","subscribed_amount_10k_rmb","subscription_price_rmb_per_share"],
         ["pdf_page","subscriber","evidence_text"]),
        ("equity_snapshot", equity_records,
         ["pdf_page","snapshot_time","shareholder_name","evidence_text","review_status"],
         ["total_shares_10k","total_registered_capital_10k_rmb","shares_10k","capital_contribution_10k_rmb","shareholding_ratio"],
         ["pdf_page","shareholder_name","evidence_text"])
    ]:
        for idx, r in enumerate(rec_list, 1):
            row_no = idx
            for f in required_fields:
                if f not in r:
                    schema_log.append({
                        "company_code": company_code,
                        "company_name": company_name,
                        "jsonl_file": jsonl_file.name,
                        "line_no": row_no,
                        "record_type": rec_type,
                        "check_item": f"字段存在性:{f}",
                        "status": "fail",
                        "message": f"{f}缺失"
                    })
            for f in numeric_fields:
                val = r.get(f)
                if val is not None:
                    try:
                        float(val)
                        schema_log.append({
                            "company_code": company_code,
                            "company_name": company_name,
                            "jsonl_file": jsonl_file.name,
                            "line_no": row_no,
                            "record_type": rec_type,
                            "check_item": f"数字解析:{f}",
                            "status": "pass",
                            "message": ""
                        })
                    except:
                        schema_log.append({
                            "company_code": company_code,
                            "company_name": company_name,
                            "jsonl_file": jsonl_file.name,
                            "line_no": row_no,
                            "record_type": rec_type,
                            "check_item": f"数字解析:{f}",
                            "status": "fail",
                            "message": f"{f}无法解析为数字"
                        })
            for f in text_required:
                if not r.get(f):
                    schema_log.append({
                        "company_code": company_code,
                        "company_name": company_name,
                        "jsonl_file": jsonl_file.name,
                        "line_no": row_no,
                        "record_type": rec_type,
                        "check_item": f"必填字段:{f}",
                        "status": "fail",
                        "message": f"{f}为空"
                    })
    
    # ====== 第4层校验：t0存在性 ======
    t0_snapshot = [r for r in equity_records if r.get("snapshot_time") and any(k in r["snapshot_time"] for k in T0_KEYWORDS)]
    if not t0_snapshot:
        cross_check_log.append({
            "company_code": company_code,
            "company_name": company_name,
            "check_type": "t0存在性",
            "status": "fail",
            "message": "未发现 t0 股权结构"
        })
    else:
        cross_check_log.append({
            "company_code": company_code,
            "company_name": company_name,
            "check_type": "t0存在性",
            "status": "pass",
            "message": ""
        })
    
    # ====== 第5层：同一时点股东合计 vs 总股本/总出资额 ======
    # 按 snapshot_time 分组
    from collections import defaultdict
    snapshots = defaultdict(list)
    for r in equity_records:
        snapshots[r.get("snapshot_time")].append(r)
    for snap_time, recs in snapshots.items():
        total_shares = sum([float(r["shares_10k"]) for r in recs if r.get("shares_10k")])
        total_registered = sum([float(r["capital_contribution_10k_rmb"]) for r in recs if r.get("capital_contribution_10k_rmb")])
        # 对应总股本/总注册资本
        for r in recs:
            ts = r.get("total_shares_10k")
            tr = r.get("total_registered_capital_10k_rmb")
            diff_share = total_shares - float(ts) if ts else None
            diff_capital = total_registered - float(tr) if tr else None
            cross_check_log.append({
                "company_code": company_code,
                "company_name": company_name,
                "check_type": "股东合计校验",
                "snapshot_time_before": snap_time,
                "snapshot_time_after": snap_time,
                "shareholder_name": r.get("shareholder_name"),
                "上一时点股本/持股数(万股)": None,
                "上一时点出资额(万元注册资本)": None,
                "本次认缴/变化(万股)": None,
                "预期变更后股本/持股数(万股)": total_shares,
                "PDF披露变更后股本/持股数(万股)": ts,
                "差额(万股)": diff_share,
                "status": "fail" if diff_share and abs(diff_share)>1e-3 else "pass",
                "message": "股东合计不等于总股本" if diff_share and abs(diff_share)>1e-3 else ""
            })
    
    # ====== 第6层：增资流量与股本变化校验 ======
    # 简单匹配 snapshot_time 顺序
    equity_sorted = sorted(equity_records, key=lambda x: x.get("snapshot_time",""))
    for sub in subscription_records:
        inc_date = sub.get("increase_date")
        if not inc_date:
            continue
        # 找增资前后的 snapshot_time
        before = next((r for r in equity_sorted if r.get("snapshot_time")<=inc_date), None)
        after = next((r for r in equity_sorted if r.get("snapshot_time")>=inc_date), None)
        if before and after and sub.get("subscribed_shares_10k") and after.get("total_shares_10k"):
            expected_total = (float(before.get("total_shares_10k") or 0)+float(sub.get("subscribed_shares_10k")))
            diff = float(after.get("total_shares_10k")) - expected_total
            cross_check_log.append({
                "company_code": company_code,
                "company_name": company_name,
                "check_type": "增资流量与股本变化",
                "snapshot_time_before": before.get("snapshot_time"),
                "snapshot_time_after": after.get("snapshot_time"),
                "shareholder_name": sub.get("subscriber"),
                "上一时点股本/持股数(万股)": before.get("total_shares_10k"),
                "上一时点出资额(万元注册资本)": before.get("total_registered_capital_10k_rmb"),
                "本次认缴/变化(万股)": sub.get("subscribed_shares_10k"),
                "预期变更后股本/持股数(万股)": expected_total,
                "PDF披露变更后股本/持股数(万股)": after.get("total_shares_10k"),
                "差额(万股)": diff,
                "status": "fail" if abs(diff)>1e-3 else "pass",
                "message": "增资流量不对应股本变化" if abs(diff)>1e-3 else ""
            })

# ====== 输出日志 ======
pd.DataFrame(schema_log).to_csv(log_dir/"schema_validation_log.csv", index=False, encoding="utf-8-sig")
pd.DataFrame(cross_check_log).to_csv(log_dir/"cross_check_summary.csv", index=False, encoding="utf-8-sig")

print("校验完成，日志已生成：")
print(log_dir/"schema_validation_log.csv")
print(log_dir/"cross_check_summary.csv")