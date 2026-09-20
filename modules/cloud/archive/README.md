# cloud/ — 云实验归档与组织规则

> 本目录收纳全部云端实验资产。设计逻辑：**按时间归档实验，按功能区分工具**
> ——让每次云端实验「看得见、找得到、可追溯」。
>
> 协同流程完整手册见 `cloud/docs/cloud_coordination.md`；启动 Prompt 集见 `cloud/workflow/CLOUD_START_PROMPTS.md`。

---

## 目录结构

```
cloud/
├── archive/                    ← 归档区（**按日期**，只增不改）
│   ├── README.md               ← 本文件（归档规则）
│   └── {YYYY-MM-DD}/           ← 日期文件夹（纯日期；同一天多次 → _2、_3…）
│       ├── README.md           ← 该次实验说明（见 §3 的四个小节）
│       └── {kebab-实验名}/      ← 该次实验的全部资产
│           ├── {上传包}.zip
│           ├── return_package_<ts>.zip
│           └── return_package_<ts>/     ← 返回包解压目录（受 gitignore 约束）
├── docs/                       ← 流程文档（常驻，不归档）
│   └── cloud_coordination.md   ← 协同流程手册（规范性文档）
├── package/                    ← 打包暂存区（常驻工具；构建下一次上传 zip 用）
│   ├── CLOUD_AGENTS.md         ← 四份核心文档之一：云端自启动协议
│   ├── RESEARCH_BACKGROUND.md  ← 【打包时从项目背景文档复制】让云端理解「为什么做」
│   ├── README_FIRST.md         ← 给人看的上传说明
│   ├── EXPERIMENT_PROTOCOL.md
│   ├── RESULTS_SO_FAR.md
│   └── [实验代码/数据/矩阵 CSV]  ← 每次打包前从项目里**复制**进来
├── workflow/                   ← 工作流工具（常驻，不归档）
│   ├── CLOUD_START_PROMPTS.md  ← 启动 Prompt 集（**只追加，不修改历史**）
│   └── dashboard_template/     ← 实时仪表盘参考实现（参考，非规范）
└── verify_integrity.py         ← 返回包完整性核查（stdlib-only，常驻工具）
```

**两类目录，两套规则**：

| 类型 | 目录 | 规则 |
|---|---|---|
| **历史** | `archive/` | 按日期归档；**只增不改**；每个日期一份 README |
| **工具** | `docs/`、`package/`、`workflow/`、`verify_integrity.py` | **常驻，永不按日期归档**；内容会被反复覆盖重建 |

> 反面做法：把 `package/` 也按日期复制一份。结果是几十个互相同步的副本，
> 下一轮打包时没人知道该从哪个副本出发。

---

## 归档规则（后续 Agent 请自动遵守）

### 1. 日期文件夹

- 路径：`cloud/archive/{YYYY-MM-DD}/`，**只用日期**（ISO 格式，如 `2026-08-21`）。
- **同一天多次实验 → 追加序号**：`_2`、`_3`…（如 `2026-08-21_2/`）。
- 日期取**实验执行日**（不是打包日、不是分析日）。

### 2. 实验子文件夹

- 路径：`cloud/archive/{日期}/{kebab-实验名}/`，例如 `ratio-sweep-2026q1`。
- **一个实验的全部资产放同一个文件夹**，至少包含：
  - 上传包 zip
  - 返回包 zip
  - 返回包解压目录（若目录受 gitignore 约束，保持忽略状态即可）
- **不要**在日期文件夹里散放文件；所有资产都要在实验子文件夹内。

### 3. 日期 README（每个日期文件夹一个）

必须包含以下四个小节（缺一不可）：

```markdown
# 云实验 {YYYY-MM-DD} — {实验名}

## 实验内容
<!-- 跑的是什么、矩阵规模、重复次数、关键配置、实际耗时。
     写清楚到"没参加这次实验的人也能读懂在干什么"。 -->

## 本文件夹内容
实验资产收于 `{kebab-实验名}/` 子文件夹：

| 文件 | 说明 |
|---|---|
| `{实验名}/{上传包}.zip` | 上传云端的实验包（代码 + 数据 + 协议） |
| `{实验名}/return_package_<ts>.zip` | 云端返回包（N runs 数据 + 日志 + checkpoint） |
| `{实验名}/return_package_<ts>/` | 返回包解压目录（含 CLOUD_AGENT_NOTE.md） |

## 关键结论
<!-- 数值结论 + 判据是否成立 + 与上次实验的异同。
     数字必须从 results.csv / summary.csv 读，禁止凭记忆或估计。 -->

## 结果去向
<!-- 结果落到了哪：results/ 路径、session log 文件名、是否需要更新 RESEARCH_BACKGROUND。
     这一节是"下次怎么找回这些结果"的唯一线索。 -->
```

### 4. 新实验的归档流程

| 时点 | 动作 |
|---|---|
| **打包时** | 在 `cloud/package/` 暂存区准备；zip 顶层目录固定为 `cloud_package/`；`cp` 到 `cloud/archive/{执行日}/{实验名}/` |
| **执行后** | 返回包带回本地 → 核对完整性（`cloud/docs/cloud_coordination.md` §12）→ 解压到同目录 |
| **核验通过** | 补全日期 README，答复用户「可以关机」 |
| **分析后** | 更新日期 README 的「关键结论」「结果去向」，并把结论回流到 `cloud/package/RESULTS_SO_FAR.md` |
| **改进回流** | 把返回包里的 `cloud_scripts/`（云端修改过的脚本）**合并回 `cloud/package/` 暂存区** |

### 5. 打包纪律

- **只复制，不移动，不删除本地源文件。** zip 是唯一上传物。
- 归档用 `cp`，**不要用 `mv`**——源文件留在项目原处，归档是副本。

---

## 什么该入库、什么不该

| 内容 | 是否入库 | 理由 |
|---|---|---|
| 日期文件夹与实验文件夹下的 `README.md` | ✅ | 唯一能让三个月后的你读懂这次实验的东西 |
| 上传包 / 返回包 zip | ✅（默认） | 实验的原始凭据；体积敏感时可忽略（见 `.gitignore`） |
| 返回包解压目录 | ❌（保留 `manifest.json` / `CLOUD_AGENT_NOTE.md`） | 含大体积 checkpoint，且可由 zip 完整复现。核查脚本**不在**解压目录里——它是常驻工具 `cloud/verify_integrity.py`（返回包里也不会带它） |
| `package/` 里的代码副本 | ❌ | 每次打包前重建，随时被覆盖 |
| `package/` 里的四份文档与矩阵 CSV | ✅ | 它们是**手写的**，不是复制来的 |
| `cloud_scripts/`（返回包内） | ✅ | 云端打磨过的 harness，是最有价值的长期产物 |

---

## 参考

- 协同流程完整手册 → `cloud/docs/cloud_coordination.md`
- 启动 Prompt 集 → `cloud/workflow/CLOUD_START_PROMPTS.md`
- 仪表盘参考实现 → `cloud/workflow/dashboard_template/README.md`
- 返回包核验 → `python cloud/verify_integrity.py --help`
