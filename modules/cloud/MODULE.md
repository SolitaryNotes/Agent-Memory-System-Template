# modules/cloud — 远程 GPU 实验流水线（本地 Agent ⇄ 云端 Agent 协同）

> 本模块是 `core/agent_memory/` 的**场景增量**，不替换核心。
> 核心回答「记忆放哪、什么时候更新」；本模块回答「**算力在别人的机器上、那台机器随时会消失时，
> 实验怎么打包出去、过程怎么让用户看得见、结果怎么带回来、带回来的东西怎么归档**」。

---

## 一、适用场景（先确认你属于这一类）

本模块针对的是一种**具体的、约束很强的**作业形态：

| 约束 | 含义 |
|---|---|
| **实例不持久** | 云端 GPU 实例（典型例子：**AutoDL**）按小时计费，关机即丢盘；不能假设云端有任何历史代码/数据/环境 |
| **无远程控制通道** | 本地 Agent 无法 SSH 进云端、无法推送命令；本地与云端之间**只靠压缩包传递** |
| **人工搬运** | 上传 zip、下载返回包都由**用户手工**完成（网页上传 / JupyterLab / scp） |
| **不可中断性要求高** | 一次实验常常 5–10 小时（过夜），SSH 断连、实例重启、显存溢出都会发生 |
| **用户要看得见** | 用户在云端面板前，必须能实时确认"还在跑、跑到哪了、有没有挂" |

只要你的任务是「**把一批实验丢到租来的 GPU 上跑完，再拿回结果**」，就该挂载本模块。

反之，如果有常驻集群 + Slurm + 共享存储 + 自动拉取，本模块的很多约束（尤其打包/回传）是多余的——
此时你需要的是一套作业调度规范，不是这个。

---

## 二、一条流水线，四个交接面

整条链路上**只有四个地方会出错丢东西**，本模块的每条规则都对应其中一个：

```
[本地]                                          [云端]                     [本地]
1. 打包（四份文档 + 代码 + 数据）  ──zip──→  2. 自启动 + 执行  ──return.zip──→  3. 接收 + 核验
   ↑ 交接面 A：包不完整 / 云端看不懂                ↑ 交接面 B：静默跑挂 / 用户看不到
                                                                  ↑ 交接面 C：返回包缺斤少两
```

| 交接面 | 典型失效 | 本模块的对策 |
|---|---|---|
| **A. 打包** | 云端 Agent 只拿到「做什么」，不知道「为什么做」，遇到意外无法自主纠偏 | 四份核心文档缺一不可（见 §三） |
| **B. 执行** | 命令丢进后台静默跑完，中途挂了没人知道；或用户只能干等 | 实时监督为**硬性要求**（实现形式自由） |
| **C. 返回** | 返回包只有结果、没有云端改过的脚本，本地无法复现/无法改进 | 返回包强制含 `cloud_scripts/`（见 §五） |
| **D. 归档** | 三天后没人知道哪个 zip 对应哪次实验、结论落到哪个文件 | 按日期归档 + 每个日期一份 README（规则见 `archive/README.md`） |

---

## 三、四份核心文档（打包时缺一不可）

上传包根目录必须有这四份。**它们的价值不在于"记录了什么"，而在于让一个远程 Agent 能自主决策**：

| 文档 | 回答的问题 | 为什么不能省 |
|---|---|---|
| `CLOUD_AGENTS.md` | **怎么做**（执行手册） | 启动协议、环境检查、失败处理、返回打包——★必须是云端 Agent 读的第一份 |
| `RESEARCH_BACKGROUND.md` | **为什么做**（动机、科学问题、术语、理论张力） | **这是唯一能让云端 Agent 在遇到没写过的情况时做出正确判断的东西。** 只给「what」的 Agent 遇到异常只会停下来等指令；给了「why」的 Agent 能自己决定「这个失败该重试还是该跳过」 |
| `EXPERIMENT_PROTOCOL.md` | **做哪个、做多少**（配置、矩阵、重复次数、时间预估） | 把参数固化成可核对的表；没写进协议的时间预估，会让云端 Agent 中途放弃或无限拖 |
| `RESULTS_SO_FAR.md` | **已经知道什么**（本地已有结果与数字） | 避免重复劳动，并让云端 Agent 知道**当前证据强度**——它才能判断"我这次跑出来算好还是算坏" |

> **反模式**：只发一份 `README.md` 交代任务。远程 Agent 会把所有没写明的选择都当成"随便"，
> 而实验里"随便"的默认值通常不是你要的那个。

---

## 四、本模块产出的项目目录

挂载后项目里会多出：

```
cloud/
├── archive/                      ← 归档区（**按日期**，见 archive/README.md）
│   ├── README.md                 ← 归档规则（本模块提供）
│   └── {YYYY-MM-DD}/
│       ├── README.md             ← 该次实验说明（内容 / 本文件夹内容 / 关键结论 / 结果去向）
│       └── {kebab-实验名}/        ← 上传 zip + 返回 zip + 返回解压目录
├── docs/                         ← 流程文档（常驻，不归档）
│   └── cloud_coordination.md     ← 协同流程手册（规范性文档）
├── package/                      ← 打包暂存区（**按功能**，常驻，不归档）
│   ├── CLOUD_AGENTS.md           ← 复制进 zip；云端 Agent 第一个读
│   ├── README_FIRST.md           ← 给**人**看的上传步骤
│   ├── RESEARCH_BACKGROUND.md    ← 打包时从项目背景文档复制
│   ├── EXPERIMENT_PROTOCOL.md
│   ├── RESULTS_SO_FAR.md
│   └── [TODO: 实验代码/数据/矩阵 CSV，每次打包前从项目里复制进来]
├── workflow/                     ← 工作流工具（常驻，不归档）
│   ├── CLOUD_START_PROMPTS.md    ← 启动 Prompt 集（**只追加，不修改历史**）
│   └── dashboard_template/       ← 实时仪表盘参考实现（参考，非规范）
└── verify_integrity.py           ← 返回包完整性核查（stdlib-only）
```

**核心组织原则**：**按时间归档实验，按功能区分工具。**

- `archive/{日期}/` 里的东西是**历史**，只会被读，不会被改。
- `package/` 和 `workflow/` 里的东西是**工具**，会被反复覆盖重建；一旦按日期归档，工具就会退化成几十个互相同步的副本。

> 完整协同手册（本模块的规范性文档，落地到项目的 `cloud/docs/cloud_coordination.md`）
> → 模块内源文件：`modules/cloud/docs/cloud_coordination.md.tmpl`

---

## 五、八条硬性规则（速查）

详细理由与操作见 `cloud/docs/cloud_coordination.md`；这里是挂载后必须记住的清单。

| # | 规则 | 一句话理由 |
|---|---|---|
| 1 | **zip 顶层目录固定为 `cloud_package/`** | 云端解压后的命令必须是常数：`unzip X.zip && cd cloud_package`，不能每次都查「这次叫什么」 |
| 2 | **只复制，不移动不删除本地源文件** | zip 是唯一上传物；本地源被 `mv` 走后，第二天本地实验就断了 |
| 3 | **重复 N=3 是硬性默认** | 随机性（seed / 随机掩码 / 采样）本身是实验变量时，单次结果**无法区分"策略好"和"这次运气好"**；只有 per-rep 原始值 + mean±std 才能 |
| 4 | **严禁编造数字**，且靠**结构性机制**保证 | 展示的所有数字都由 `results.csv` / `dashboard_state.json` **在读取时现算**，Agent 从不"手打"数字——这样"编造"在流程上就不可能发生 |
| 5 | **实时监督是硬性要求，实现形式自由** | 云端跑一夜、用户只能靠猜，是这个流程最大的痛点。但**展示长什么样由云端 Agent 定**——`dashboard_template/` 是**参考，不是规范** |
| 6 | **单机一致性（条件性）** | 若矩阵内格子要**互相比大小**，它们必须在同一实例、同一会话内跑完。同类项目实测：同一个格子跨两个实例可差 **0.0034**（经验值，**非本项目数据**），足以翻转"哪个最优"的结论 |
| 7 | **续跑按矩阵状态，不按 checkpoint** | 中断后是"把已完成的格子标 done、重跑其余"，不是"从某个 ckpt 恢复"。`nohup`/`screen` 是第一道防线 |
| 8 | **返回包必须包含云端实际运行的脚本**（`cloud_scripts/`） | 云端 Agent 一定会打补丁修 bug；这些补丁是**最有价值的长期产物**，要回流到本地暂存区 |

---

## 六、本模块文件清单

| 文件 | 落地到项目的路径 | 说明 |
|---|---|---|
| `README.md` | —（不落地） | 本文件：模块说明 |
| `gitignore.fragment` | —（追加进 `.gitignore`） | 忽略暂存区、解压目录、权重、运行时状态 |
| `docs/cloud_coordination.md.tmpl` | `cloud/docs/cloud_coordination.md` | **协同流程手册**（本模块的规范性文档） |
| `workflow/CLOUD_START_PROMPTS.md.tmpl` | `cloud/workflow/CLOUD_START_PROMPTS.md` | 启动 Prompt 集（只追加） |
| `package/CLOUD_AGENTS.md.tmpl` | `cloud/package/CLOUD_AGENTS.md` | 云端 Agent 自启动协议 |
| `package/README_FIRST.md.tmpl` | `cloud/package/README_FIRST.md` | 给**人**看的操作说明 |
| `package/EXPERIMENT_PROTOCOL.md.tmpl` | `cloud/package/EXPERIMENT_PROTOCOL.md` | 实验协议 |
| `package/RESULTS_SO_FAR.md.tmpl` | `cloud/package/RESULTS_SO_FAR.md` | 已有结果（供云端 Agent 参考） |
| `archive/README.md` | `cloud/archive/README.md` | **归档规则**（按日期） |
| `verify_integrity.py` | `cloud/verify_integrity.py` | 返回包完整性核查（stdlib-only） |
| `workflow/dashboard_template/` | `cloud/workflow/dashboard_template/` | 实时仪表盘参考实现（4 个文件，原样复制） |

> **未提供**：`RESEARCH_BACKGROUND.md` 的模板。这份文档的内容高度依赖具体科研项目，
> 打包时由本地 Agent 从项目的背景文档复制并裁剪（见 `cloud/docs/cloud_coordination.md` §3.1）。

---

## 七、占位符

由 `tools/init.py` 替换；未被替换的会变成显式的 `[TODO: ...]` 标记。

| 占位符 | 含义 | 用在哪 |
|---|---|---|
| `{{PROJECT_NAME}}` | 项目名 | 文档标题、启动 Prompt |
| `{{PROJECT_SLUG}}` | 项目 slug（kebab-case） | 包名、归档目录名 |
| `{{DOMAIN}}` | 领域 | 研究背景的定位句 |
| `{{GOAL}}` | 最终目标 | 研究背景的目标句 |
| `{{DATE}}` | 建立日期 | Prompt 集、归档 README 模板 |
| `{{ENTRY_CMD}}` | 实验入口命令 | `EXPERIMENT_PROTOCOL.md` §2、启动 Prompt |
| `{{BOOT_CMD}}` | 环境自检命令 | `CLOUD_AGENTS.md` §环境检查 |
| `{{GIT_REMOTE}}` | 远端仓库 | 备份/回流说明（本模块当前未引用，供项目自己的文档使用） |

**每次实验特有、init 时无法得知的值**（实验名、矩阵规模、GPU 型号、重复次数、预估时长），
一律写成 `[TODO: ...]`，由本地 Agent 在**打包那一次**填好——不要新增 `{{...}}` 名字。

---

## 八、挂载检查表

第一次做云实验前逐项过：

- [ ] `cloud/docs/cloud_coordination.md` 已读，且 §3.1 的四份文档职责已明确
- [ ] `cloud/package/` 里四份文档已按本项目填写（不是留模板原文）
- [ ] 已确定**本次的重复次数 N**（默认 3）与**是否需要单机一致性**
- [ ] 实验脚本已接入进度上报（写 `dashboard_state.json`）+ `tee` 日志
- [ ] 实验脚本已支持**按矩阵状态续跑**（`status=todo/done`）
- [ ] 启动 Prompt 已写进 `cloud/workflow/CLOUD_START_PROMPTS.md`（**追加**）
- [ ] 用户已知晓：`README_FIRST.md` 是给他看的，上传命令是 `unzip X.zip && cd cloud_package`
- [ ] 返回包回来后跑过 `python cloud/verify_integrity.py`
