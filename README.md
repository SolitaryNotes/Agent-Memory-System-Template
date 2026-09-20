# Agent Memory System — 可复用的 Agent 记忆系统模板

> 让任何一个新项目里的 Agent，**不需要你重新交代一遍上下文**，就能知道：
> 这是什么项目、现在在哪一步、该改哪个文件、上次做到哪了。

这是一套**模板仓库 + 初始化脚本**。它把一套在真实科研项目中长期使用、并经过一次全机审计的记忆系统
剥离出通用内核，补齐了原系统缺失的执行机制，做成可以一键落到任何新项目的形式。

---

## 快速开始

```bash
# 交互式落地（会逐项问清楚）
python tools/init.py --target D:/path/to/new-project

# 非交互，指定模块
python tools/init.py --target DIR --yes --modules research,cloud

# 只看看会做什么
python tools/init.py --target DIR --dry-run
```

落地后：

```bash
cd DIR
python tools/check_conventions.py --root .   # 校验约定（含死链检查）
```

`init.py` 会把能自动填的填好，**填不了的一律留成显式 `[TODO: ...]` 标记**并列出清单——
然后你新开一个 Agent 会话，让它读 `CLAUDE.md` 后按路由表逐项补齐即可。

**最后一步别省：冷启动验收。** 开一个**全新、零上下文**的 Agent 会话，只丢一句
「读 `CLAUDE.md`，按它的 Boot Sequence 走，然后告诉我这个项目是什么、什么状态、
哪一步断了或需要猜」，并要求它**必须给批评性意见**（否则它只会报喜）。
它说得清 = 系统可用。详见 [`docs/mechanism.md`](docs/mechanism.md) §12——
本模板就是靠这个办法连做 13 轮验收，每轮都抓出了真问题
（**并且每轮的结论都复核过**——验收报告本身也会错，见 §12 第 5 条教训）。

---

## 它解决什么问题

这套设计的每一条都对应一个**实测过的失效**，不是凭空的最佳实践：

| 失效 | 本系统的对策 |
|---|---|
| 同一份内容写在 4 个文件里，逐渐互相矛盾（实测某项目的两份入口文件在「当前阶段」「最近会话」「快速开始」三处不一致） | **单一事实源**：`AGENTS.md` 由 `CLAUDE.md` 生成，`tools/sync_agents_md.py` |
| 计划文件没有生命周期，早已失效却仍被标为「当前计划」 | `plans/` 强制 frontmatter `status: active\|done\|superseded`，`check_conventions.py` 校验至多一份 active |
| 「绘图脚本 ↔ 图片目录」的镜像规则靠人肉维护，出现**重复编号**和**孤儿目录** | 镜像规则与编号唯一性纳入 `check_conventions.py` |
| 实验结果目录靠语义命名，变体只靠手工 `--tag` 区分，30 epoch 与 10 epoch 除文件夹名外无从分辨 | **`run.json` 溯源**：run_id + 配置快照 + git commit + seed |
| 启动序列只是写在文档里的约定，没有东西保证它被执行 | 可选 `SessionStart` hook（**默认关闭**，附开销核算） |
| 上下文预算无人把关，tier-0 文件越写越长 | `check_conventions.py` 校验行数预算 |
| 文档指向不存在的文件（实测：路由表引用了一个不存在的 `configs/` 目录；模板仓库的内部路径泄漏进项目） | `check_conventions.py` 的**死链检查**——作者知道自己的意思，读者却会走进死胡同，这类断链必须机器查 |
| 空的模板文件被启动序列当成真实产物（实测：计划模板的 `status: active` 让 Agent 读到了一份"冒充真实计划的空文件"） | 模板与真实产物**命名分离**，且模板的 frontmatter 不写有效状态值 |
| 规则要求填某个字段，但该字段在当前环境下无值可取 → Agent 只能编造（实测：`run.json` 强制要求 `git_commit`，而项目尚未 `git init`） | 该字段允许 `null`，并在说明里**明确写出"不要为了填满而编造"** |

---

## 目录结构

```
├── core/                  必备内核（任何项目都装）
│   ├── CLAUDE.md.tmpl     tier-0 内核：只写协议，不写知识
│   ├── gitignore.tmpl
│   └── agent_memory/
│       ├── README.md      ★ 记忆系统的规范定义（放什么、放哪、何时更新）
│       ├── BOOT.md.tmpl   tier-1 状态快照 + ★任务→文件路由表
│       ├── current_state.md.tmpl   tier-2 完整手册 + 索引
│       ├── session_logs/_TEMPLATE.md
│       ├── plans/_TEMPLATE.md
│       └── prompts/_TEMPLATE.md
│
├── modules/               按需勾选，每个模块自带 module.json 声明落点
│   ├── research/          科研目录规范（run/plot/results/figures/configs）
│   ├── reproduction/      论文复现专项（基线对齐、偏离清单、种子策略）
│   ├── cloud/             远程 GPU 实验流水线（打包/自启动/实时监督/返回归档）
│   ├── meetings/          组会记录与论文笔记模板
│   └── hooks/             可选会话自启动（默认不装）
│
├── tools/
│   ├── init.py            一键落地
│   ├── check_conventions.py   约定校验
│   └── sync_agents_md.py  由 CLAUDE.md 生成 AGENTS.md
│
└── docs/
    ├── design.md          设计原理与上下文开销核算
    └── mechanism.md       各机制详解（为什么这么设计）
```

---

## 校验器会在两种语境间自动切换

`tools/check_conventions.py` 是给**落地后的项目**用的。它的两条核心检查——
「模板路径残留」和「路径引用死链」——在**模板仓库自身**里必然误报：
本仓库的文档按落地后的结构书写（`cloud/…`、`experiments/…`），那些路径在模板仓库里当然不存在。

所以它按根目录是否存在 `modules/` 自动判断：存在 = 模板仓库 → 这两项让路并说明原因；
不存在 = 落地项目 → 严格检查。**你不需要手动配置。**

另一类假警报来自**没装的模块**：内核与路由表里留着 `cloud/`、`hooks/`、`meetings/` 的行
（散文写着"未安装的模块路径不存在是正常的，删掉该行即可"），校验器却读不懂散文。
所以 `init.py` 落地时会生成一份 `.memory-system.json`，写明**本项目没装哪些模块**，
校验器据此跳过指向它们的引用，**并把"跳过了几条"单独报出来**——跳过不等于静默。

其余检查（行数预算、AGENTS 同步、陈旧度、日志索引、计划生命周期…）在两种语境下都照常跑。
另外，**"没产出结果"不再等于"通过"**：哪些检查项因为前置目录还没出现而根本没跑，
汇总行会单独列出来，不会伪装成覆盖面。

---

## 模块约定

每个模块用一份 `module.json` **显式声明自己的落点**，而不是靠隐式约定：

```json
{
  "name": "cloud",
  "target_prefix": "cloud",     // 本模块的文件落到项目的 cloud/ 下；空字符串 = 项目根
  "description": "…",
  "requires": ["research"]      // 依赖提示（供人参考，init.py 不强制）
}
```

两条配套规则：

- **`MODULE.md`** = 模块**自身**的说明文档，**不会**落地到项目里。
  模块内任何位置名为 `README.md` 的文件则**会**按原样落地——所以
  `modules/cloud/README.md.tmpl` 会变成项目的 `cloud/README.md`。
  这样「模板仓库的文档」与「项目的文档」永远不会混淆。
- **`gitignore.fragment`** 不会被直接复制，而是追加到项目的 `.gitignore` 末尾。

### 新增一个模块

```
modules/<name>/
├── MODULE.md            模块说明（不落地）
├── module.json          落点声明
├── gitignore.fragment   可选
└── …                    其余文件按 target_prefix 落地
```

改完跑一次 `python tools/init.py --target DIR --modules <name> --dry-run` 确认落点。

---

## 核心思想（三句话）

1. **分层渐进披露。** 每次会话自动加载的只有一个很短的内核；知识按需下沉到
   `BOOT.md` → `current_state.md` → `session_logs/`。判断一条信息放哪层，问：
   「**每次会话都必须知道吗？**」
2. **单一事实源 + 可执行校验。** 同一个事实只写一次；能用脚本查的约定就不要靠人记。
3. **产物清单是找回东西的唯一线索。** 每份会话记录必须列出本次产生的全部路径——
   后续会话靠它检索，靠记忆检索是不可靠的。

---

## 平台兼容

以 **Claude Code** 为主入口（`CLAUDE.md` 自动加载），同时生成 `AGENTS.md`
供 Codex / Cursor 等 AGENTS.md 生态读取。两者**同源**：改 `CLAUDE.md`，
跑一次 `sync_agents_md.py`。平台专属内容用 `<!-- @agents:skip -->` 标记包裹，
不会进入 `AGENTS.md`。

---

## 文档

- **设计原理与开销核算** → [`docs/design.md`](docs/design.md)
- **各机制详解** → [`docs/mechanism.md`](docs/mechanism.md)
