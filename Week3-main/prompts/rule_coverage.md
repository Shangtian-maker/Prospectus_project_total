# Rule Coverage Report（规则覆盖说明）

## 一、目标说明

本规则系统用于从IPO招股说明书PDF中自动抽取三类核心股权结构数据：

- subscription_flow（增资 / 设立出资 / 定向发行）
- share_transfer_flow（股权转让）
- equity_snapshot（股权结构存量）

并用于后续 cross-check_gold.jsonl 的一致性验证。

---

# 二、规则覆盖章节范围（PDF结构层）

本规则主要覆盖以下三类章节：

## 1️⃣ 股本形成与历史沿革章节（核心）

### 覆盖关键词：

- 设立
- 注册资本
- 出资
- 股本形成
- 有限公司设立

### 覆盖内容：

- t0设立时股权结构
- 初始出资比例
- 注册资本来源

✔ 用于：
- equity_snapshot（t0）
- subscription_flow（设立出资）

---

## 2️⃣ 历次增资 / 定向发行章节

### 覆盖关键词：

- 增资
- 认购
- 定向发行
- 发行股份
- 新增注册资本

### 覆盖内容：

- 增资金额
- 认购人
- 认购价格
- 变化后总股本

✔ 用于：
- subscription_flow

---

## 3️⃣ 股权转让章节

### 覆盖关键词：

- 股权转让
- 转让
- 受让
- 出让
- 协议转让

### 覆盖内容：

- 转让方
- 受让方
- 转让数量
- 转让价格

✔ 用于：
- share_transfer_flow

---

## 4️⃣ 股权结构存量表章节

### 覆盖关键词：

- 股权结构
- 持股比例
- 股东结构
- 报告期末
- 本次变动后

### 覆盖内容：

- t0 / t1 / t2 / tn 股东结构
- 每一轮融资后的持股比例
- 总股本

✔ 用于：
- equity_snapshot

---

# 三、规则抽取策略（Rule Design）

## 1️⃣ 关键词触发 + 段落切块

```text
IF paragraph contains keyword → mark as candidate section