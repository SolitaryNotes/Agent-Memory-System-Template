---
paper: "{{PAPER_TITLE}}"
venue: {{VENUE}}              # 会议/期刊名；预印本写 arXiv
year: {{YEAR}}
url: {{URL}}                  # arXiv / DOI / 会议页
code: {{CODE_REPO}}           # 无官方代码写 none；有第三方实现写链接
read_date: {{YYYY-MM-DD}}     # 本次通读日期，不是论文发表日
relevance: {{RELEVANCE}}      # 与本课题的关系：为什么读它（1-2 句）
---

# {{PAPER_TITLE}}

> **本文是论文的「结构性转写」（structural transcription），按论文自身章节编号组织，不是读后总结。**
> 转写部分只陈述**论文说了什么**；自己的判断一律放文末 `## 我的批注`。
> 二者分离的理由：**你必须能随时区分「论文的主张」与「你的理解」**——
> 论文笔记的正文是**结构转录**（忠实于原文），你的判断一律写在末尾的批注区。

**原文作者**: {{AUTHORS}}
**机构**: {{AFFILIATIONS}}

---

## Abstract

{{[TODO: 逐句转写摘要。保留原文的论断强度——"outperforms" 与 "is competitive with" 不是一回事，不要统一成"效果好"]}}

---

## 1 Introduction

### 1.1 问题背景

{{[TODO: 论文为什么做这件事；现有方法的问题是什么]}}

### 1.2 本文主张（contributions）

> 逐条转写论文自报的贡献，**不做评价**。评价放 §我的批注。

1. {{CONTRIBUTION_1}}
2. {{CONTRIBUTION_2}}
3. {{CONTRIBUTION_3}}

### 1.3 关键论断原句

| # | 论断 | 原文位置 |
|---|---|---|
| C1 | {{CLAIM}} | p.{{N}} / §{{X}} |
| C2 | | |

> ⚠️ 转写时**不要把 hedge 词抹掉**（"may"、"we hypothesize"、"suggests"）。这些词决定论断强度，抹掉后就变成了论文没说过的话。

---

## 2 Related Work

> 按论文自己的分组转写；每组写清「论文认为与它的区别在哪」。

### 2.1 {{GROUP_NAME}}

- {{METHODS}}
- **论文自述的区别**: {{DIFFERENCE}}

### 2.2 {{GROUP_NAME}}

- {{METHODS}}
- **论文自述的区别**: {{DIFFERENCE}}

### 2.3 本文在谱系中的位置

| 维度 | 前作 | 本文 |
|---|---|---|
| {{DIM}} | {{PRIOR}} | {{OURS}} |

---

## 3 Proposed Method

### 3.1 {{SECTION_TITLE}}

{{[TODO: 转写方法。公式用 LaTeX 原样保留；符号表单独列出，避免后文符号混乱]}}

**符号表**：

| 符号 | 含义 |
|---|---|
| {{SYMBOL}} | {{MEANING}} |

### 3.2 {{SECTION_TITLE}}

{{[TODO]}}

### 3.3 实现细节

| 项 | 值 | 出处 |
|---|---|---|
| {{PARAM}} | {{VALUE}} | §{{X}} / Table {{N}} |

> 本节是**复现时最有用的部分**——同步登记到 `docs/reproduction_protocol.md` 的参数对照表。

### 3.4 论文未说明的部分 ⚠️

| 项 | 论文是否说明 | 备注 |
|---|---|---|
| {{ITEM}} | [TODO: 核对后填 ❌——先确认论文正文与附录里确实都没有，再把它列进本表] | [TODO: 需自行决定] |

> 本表只收**核对过、论文确实没给**的项。没核对就填 ❌ 等于替论文下结论——
> 那是转写区最不能出的错（转写区的每一句都要能回溯到原文）。

---

## 4 Experiments

### 4.1 实验设置

| 项 | 内容 |
|---|---|
| 数据集 | {{DATASETS}} |
| Baseline 对手 | {{BASELINES}} |
| 评测指标 | {{METRICS}} |
| 硬件 | {{HARDWARE}} |

### 4.2 主结果（Table {{N}} / Figure {{N}}）

| {{COL_1}} | {{COL_2}} | {{COL_3}} | 论文出处 |
|---|---|---|---|
| {{ROW}} | {{NUM}} | {{NUM}} | Table {{N}} |

> **数字原样转写，不四舍五入、不改写单位。** 后续要拿它当对照基准，转写失真等于自毁证据链。

### 4.3 消融实验（Ablation）

| 变体 | {{METRIC}} | Δ vs full | 论文结论 |
|---|---|---|---|
| full | {{NUM}} | — | — |
| w/o {{COMPONENT}} | {{NUM}} | {{DELTA}} | {{CONCLUSION}} |

### 4.4 论文自报的结论

- {{FINDING_1}}
- {{FINDING_2}}

---

## 5 Conclusion

{{[TODO: 转写论文自己的总结，以及它自报的 limitation / future work]}}

**论文自报的局限**：
- {{LIMITATION}}

---

## References

> 只记**要跟进的**，不抄全表。

| # | 文献 | 为什么记 |
|---|---|---|
| [{{N}}] | {{CITATION}} | {{WHY}} |

---

## Appendix

{{[TODO: 附录里常藏关键信息——完整超参、额外消融、数据集细节。不要跳过]}}

| 内容 | 位置 | 关键信息 |
|---|---|---|
| {{CONTENT}} | App. {{X}} | {{KEY_INFO}} |

---

---

# 我的批注

> ⚠️ **以下内容全部是读者本人的判断，不是论文的主张。**
> 与上方转写严格分离；如需引用本文件，请指明引用的是哪一部分。

## 可信度评估

| 维度 | 评估 | 依据 |
|---|---|---|
| 实验是否支撑结论 | {{VERDICT}} | {{EVIDENCE}} |
| 是否与其他工作公平对比 | {{VERDICT}} | {{EVIDENCE}} |
| 缺失的关键实验 | {{WHAT}} | {{WHY_IT_MATTERS}} |
| 复现风险 | {{RISK}} | {{REASON}} |

## 与我课题的关系

- **可直接借用**: {{USABLE}}
- **需要改造**: {{NEEDS_ADAPTATION}}
- **不适合的原因**: {{UNSUITABLE}}

## 待确认的问题

1. [TODO: {{QUESTION_1}}]
2. [TODO: {{QUESTION_2}}]

## 衍生的实验想法

| 想法 | 依据（对应上方哪一句） | 优先级 |
|---|---|---|
| {{IDEA}} | §{{X}} / Table {{N}} | P0 / P1 |

---

> **写完后登记**：把本文件加入课题的文献索引，并在 `agent_memory/current_state.md` §10 专题文档索引中补一行（若属长期专题）。
