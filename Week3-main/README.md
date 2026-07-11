# Week3

## 📌 项目简介

本项目用于从IPO招股说明书（PDF）中自动抽取结构化信息，并与人工标注数据进行对比分析。

主要抽取三类数据：

- 认购/增资/出资信息
- 股权转让信息
- 股权结构存量信息

---

## 🏗️ 系统流程

DF解析 → 章节定位 → 候选抽取 → 规则/LLM抽取 → schema校验 → cross-check → 结果评估

---

## 📁 项目结构

data/
├── pdf_manifest.csv # PDF清单
├── manual_gold/ # 人工标注标准答案
│ ├── subscription_flow_gold.jsonl
│ ├── share_transfer_flow_gold.jsonl
│ ├── equity_snapshot_gold.jsonl
│ ├── cross_check_gold.jsonl
├── evaluation/
│ ├── error_analysis.md # 误差分析报告

outputs/
├── auto_jsonl/ # 自动抽取结果
├── auto_excel/ # Excel输出
├── logs/ # 运行日志

pipeline/
├── parse_pdf.py # PDF解析
├── locate_sections.py # 章节定位
├── extract_candidates.py # 候选事件生成
├── extract_with_rules.py # 规则抽取
├── extract_with_llm.py # LLM抽取
├── validate_schema.py # schema校验
├── run_cross_check.py # 一致性校验
├── compare_to_gold.py # gold评估
├── pipeline_total.py # 主流程入口

prompts/
├── system_prompt.md
├── prompt_variants.md
├── prompt_sensitivity.md
├── rule_coverage.md


---

## ⚙️ 核心功能

### 1️⃣ 信息抽取
- 规则方法 + LLM补充抽取
- 提取认购、转让、股权结构信息

### 2️⃣ Schema统一
- 统一字段格式（company、数量、金额等）
- 自动过滤非法数据

### 3️⃣ Cross-check校验
- 检查股本是否守恒
- 检查转让是否影响总股本

### 4️⃣ Gold对比
- 与人工标注数据对比
- 计算漏抽和误抽情况

---

## 🚀 运行方式

```bash
# 运行完整流程
python pipeline/pipeline_total.py

# 运行校验
python pipeline/run_cross_check.py

# 评估结果
python pipeline/compare_to_gold.py
