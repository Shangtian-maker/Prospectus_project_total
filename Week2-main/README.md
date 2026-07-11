# Week 2 招股说明书股本变化抽取项目

本仓库用于提交 Week 2 公共 8 家 IPO 招股说明书的结构化抽取结果。任务重点是从 PDF 原文中抽取上市前股本变化相关事实，并通过 schema 校验、数值 cross-check 和 PDF 证据回源保证结果可复核。

## 一、项目目标

本周处理统一指定的 8 家公共样本公司，围绕招股说明书中的上市前股本变化，抽取两类事实记录：

1. `subscription_flow`：认缴流量，记录谁在什么时候认购了多少、多少钱、什么价格。
2. `equity_snapshot`：股权结构存量，记录某一时点的股东结构、总股本、出资额、持股数和持股比例。

所有结果以 JSONL 作为主结果，Excel 仅作为人工查看版。

## 二、样本范围
本周仅处理以下 8 家公共样本：
| 股票代码   | 公司简称 | 公司全称                |
| ------ | ---- | ------------------- |
| 001282 | 三联锻造 | 芜湖三联锻造股份有限公司        |
| 603418 | 友升股份 | 上海友升铝业股份有限公司        |
| 301581 | 黄山谷捷 | 黄山谷捷股份有限公司          |
| 301563 | 云汉芯城 | 云汉芯城（上海）互联网科技股份有限公司 |
| 688758 | 赛分科技 | 苏州赛分科技股份有限公司        |
| 688775 | 影石创新 | 影石创新科技股份有限公司        |
| 920100 | 三协电机 | 常州三协电机股份有限公司        |
| 920116 | 星图测控 | 中科星图测控技术股份有限公司      |

## 三、目录结构

week2/
  README.md
  company_list/
    week2_public_8.csv

  outputs/
    week2_jsonl/
      001282_三联锻造_extracted_records.jsonl
      603418_友升股份_extracted_records.jsonl
     ...

    week2_excel/
      001282_三联锻造_extracted_records.xlsx
      603418_友升股份_extracted_records.xlsx
      ...

  annotations_pdf/
    001282_三联锻造_关键页批注.pdf
    603418_友升股份_关键页批注.pdf
    ...

  schemas/
    extraction_models.py

  scripts/
    validate_jsonl.py
    jsonl_to_excel.py
    generate_key_page_annotations_compressed.py

  logs/
    schema_validation_log.csv
    cross_check_summary.csv

  prompts/
    candidate_texts/
      001282_三联锻造_IPO招股说明书_候选文本.jsonl
      301563_云汉芯城_IPO招股说明书_候选文本.jsonl
      ...
    llm_prompt.md

  weekly_reports/
    week2.md


## 四、主要提交内容

### 1. JSONL 主结果

路径：
outputs/week2_jsonl/

每家公司一个 JSONL 文件。每行是一条结构化记录，`record_type` 只能为：
subscription_flow
equity_snapshot

### 2. Excel 查看版

路径：
outputs/week2_excel/

由 JSONL 自动转换生成，每家公司一个 Excel 文件，包含：

* `认缴流量`
* `股权结构存量`
* `schema_cross_check`

Excel 仅用于人工查看，正式结果以 JSONL 为准。

### 3. Pydantic Schema

路径：
schemas/extraction_models.py

用于定义两类记录的字段、类型、必填项和基础取值规则。

### 4. 校验脚本

路径：
scripts/validate_jsonl.py

用于检查：

* JSONL 是否可逐行解析；
* `record_type` 是否正确；
* 必填字段是否为空；
* 数字字段是否能解析；
* 每家公司是否存在 `t0` 股权结构；
* 认缴流量与股权结构变化是否能够进行 cross-check。

### 5. JSONL 转 Excel 脚本

路径：
scripts/jsonl_to_excel.py

用于将 JSONL 转换为 Excel 查看版。

### 6. 校验日志

路径：
logs/schema_validation_log.csv
logs/cross_check_summary.csv

其中：
* `schema_validation_log.csv` 记录 schema 检查结果；
* `cross_check_summary.csv` 记录总量核对和逐股东核对结果，并保留参与核对的关键数字。

### 7. 关键页批注 PDF

路径：
annotations_pdf/      

用于展示字段和数字来自 PDF 的哪些页面。批注 PDF 已进行压缩处理，便于上传 GitHub。

### 8. 周报

路径：
weekly_reports/week2.md

记录本周完成的工作、处理流程、遇到的问题和解决方案。

## 五、运行方式

### 1. 安装依赖

pip install pymupdf pandas openpyxl pydantic pillow

### 2. 校验 JSONL

python scripts/validate_jsonl.py

运行后生成：
logs/schema_validation_log.csv
logs/cross_check_summary.csv

### 3. 生成 Excel 查看版

python scripts/jsonl_to_excel.py

输出到：
outputs/week2_excel/

### 4. 生成关键页批注 PDF

python scripts/generate_key_page_annotations_compressed.py

输出到：
annotations_pdf/


## 六、说明

本项目强调可复核性。所有数字和字段原则上都应能回到 PDF 页码和原文证据。对于无法自动确认的记录，不强行补全，统一标记为待复核，并在校验日志中说明原因。
