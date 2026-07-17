# 8家公司招股书股权演变批处理工程

本工程将单家公司处理扩展为8家公司批处理，覆盖：

1. PDF接入与页级文本抽取
2. OCR兜底
3. 股本演变、历史沿革、股东章节定位
4. 分块抽取
5. 认购增资、股权转让、股权快照三类Schema输出
6. 时间、数值、比例、公司别名归一化
7. JSON Schema校验与业务规则校验
8. Gold工作簿Cross-check
9. JSON、Excel、问题清单和批量汇总输出
10. 输入哈希与断点跳过

## 一、准备数据

将8份PDF放入：

```text
input/pdfs/
```

将可选的人工Gold工作簿放入：

```text
input/gold/
```

编辑 `config/companies.yaml`，填写真实公司名称、别名、PDF路径和Gold路径。

## 二、安装

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
```

## 三、运行

处理全部公司：

```bash
python run_batch.py
```

只处理指定公司：

```bash
python run_batch.py --only company_01 company_03
```

## 四、LLM抽取配置

默认 `llm.enabled: false`，此时只运行规则候选抽取，适合先验证流程和目录。

接入支持Chat Completions风格的结构化抽取服务时，在 `config/companies.yaml` 中设置：

```yaml
llm:
  enabled: true
  endpoint: "你的服务地址"
  api_key_env: LLM_API_KEY
  model: "你的模型名"
```

再设置环境变量：

```bash
# Windows PowerShell
$env:LLM_API_KEY="..."
# macOS/Linux
export LLM_API_KEY="..."
```

## 五、输出

每家公司：

```text
output/company_01/
├── extracted.json
├── validation_issues.json
├── crosscheck.json              # 有Gold时生成
└── company_01_prospectus_result.xlsx
```

总汇总：

```text
output/batch_summary.xlsx
```

中间过程：

```text
data/intermediate/company_01/
├── pages.json
├── segments.json
└── manifest.json
```

## 六、验收建议

- Schema错误数为0
- source_page缺失数为0
- Gold核心字段PASS率达到项目设定阈值
- 抽取记录都有source_text
- 同一股权快照持股比例合计接近100%
- 8家公司均有独立输出与批量汇总
