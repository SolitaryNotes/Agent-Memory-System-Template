#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_conventions.py — 校验记忆系统与目录约定

背景
----
本系统的约定（分层、镜像规则、编号、计划生命周期……）原本全靠人肉维护。
实测后果：某项目出现了重复的 `04` 编号、一个没有对应脚本的孤儿图目录、
以及一份早已失效却仍被标为「当前计划」的计划文件——而没有任何机制发现。

本脚本把这些约定变成**可执行的检查**。只依赖标准库，任何环境都能跑。

用法
----
    python tools/check_conventions.py                 # 检查（默认：警告不阻塞）
    python tools/check_conventions.py --strict        # 有 ⚠️ 也未通过（退出码 1）
    python tools/check_conventions.py --only mirror_rule   # 只跑某几项（可多次指定）
    python tools/check_conventions.py --list               # 先看看有哪些检查项
    python tools/check_conventions.py --root DIR

可按项目覆盖阈值 —— 在项目根放一个可选的 `.memory-system.json`：

    {
      "claude_md_max_lines": 90,
      "boot_md_max_lines": 240,
      "boot_stale_days": 30,
      "dead_link_ignore": ["results/experiments/"],   # 可选的断链豁免
      "uninstalled_module_prefixes": ["cloud", "hooks"],  # 未装的模块，其引用不算断链
      "checks": {"mirror_rule": true, "run_json": false}
    }

`uninstalled_module_prefixes` 由**落地脚本**按实际装了哪些模块自动写入
（那个脚本在模板仓库里，**不随项目落地**——所以这里不写它的路径，免得变成一条断链），
一般不需要手改。没有它，只装了 research 的项目一落地就会报 7 条指向 cloud/hooks 的
"断链"——而文档写得明明白白"未安装的模块路径不存在是正常的"。警报多了，
真正的那条断链就会被一起划过去。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

# Windows 控制台默认 GBK，中文与符号输出会直接抛 UnicodeEncodeError
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except Exception:
        pass

# 本脚本是**只读**校验器，不该在被检查的项目里留下任何痕迹。
# `check_agents_sync` 会 `from sync_agents_md import ...`，默认行为会在项目里生成
# `tools/__pycache__/sync_agents_md.cpython-3x.pyc`——实测冷启动验收把它误读成
# 「脚手架把编译产物发给了项目」，是一条**由工具副作用引起的假发现**。
sys.dont_write_bytecode = True

OK, WARN, FAIL = "ok", "warn", "fail"
ICON = {OK: "✅", WARN: "⚠️ ", FAIL: "❌"}

# slug 允许 snake_case 与 kebab-case 两种写法。
# 这条检查的目的是「日期前缀 + 可读 slug」，不是分隔符——把分隔符限死成一种，
# 只会让文档写着 snake_case、正则却只认 kebab 的裂缝存在（实测发生过）。
SESSION_LOG_RE = re.compile(r"^session_(\d{8})_([a-z0-9]+(?:[_-][a-z0-9]+)*)\.md$")
PLAN_FILE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-[a-z0-9-]+\.md$")
PLOT_NAME_RE = re.compile(r"^(\d{2})-([a-z0-9]+(?:-[a-z0-9]+)*)\.py$")
UPDATED_RE = re.compile(r"\*\*(?:Updated|最后更新)\*\*\s*[:：]\s*(\d{4}-\d{2}-\d{2})")
# 落地脚本写入状态文件时带的标注。有这个标记 = 脚手架态，日期不代表项目进度。
SCAFFOLD_MARK = "脚手架初始化"
# 未填的占位符。与 SCAFFOLD_MARK 不同，这个**改不掉**——只要内容还没填，它就在。
TODO_MARK_RE = re.compile(r"\[TODO[:：]")

DEFAULTS = {
    # 内核的实际目标是 ~70 行；这里给到 100 是「上限」而非「目标」——
    # 提醒阈值取 0.85，即涨到 85 行就该考虑往 BOOT.md 下沉了。
    # （源项目曾写着"保持 ~40 行"而实际长到 128 行——不现实的预算等于没有预算。）
    "claude_md_max_lines": 100,
    "boot_md_max_lines": 240,
    "boot_stale_days": 30,
    "dead_link_ignore": [],
    # 未安装的可选模块的顶层目录名。这些模块的文档行会留在内核/路由表里
    # （散文允许它们留着：「没装则这些路径不存在，删掉本行即可」），
    # 但校验器读不懂散文——于是默认落地必然报 7 条「应当忽略」的断链警告，
    # 把 Agent 训成忽略本检查。落地脚本按**实际装了哪些模块**写入本项，
    # 校验器据此跳过，并单独报一行「跳过了几条」——跳过不是静默。
    "uninstalled_module_prefixes": [],
    "checks": {},
}


class Ctx:
    """一次检查运行的上下文。"""

    def __init__(self, root: Path, cfg: dict):
        self.root = root
        self.cfg = cfg
        self.mem = root / "agent_memory"
        self.results: list[tuple[str, str, str]] = []  # (severity, check, message)

    def add(self, severity: str, check: str, message: str) -> None:
        self.results.append((severity, check, message))

    def enabled(self, name: str) -> bool:
        return self.cfg.get("checks", {}).get(name, True)


# ---------------------------------------------------------------- checks


def check_line_budget(c: Ctx) -> None:
    """tier-0/tier-1 是每次会话都要读的，必须保持简短。"""
    if (c.root / "modules").is_dir():
        # 模板仓库自身没有落地后的内核与状态快照（它们在 core/ 下、还是 .tmpl），
        # 报「CLAUDE.md 不存在」是语境错配。与本文件另两项检查保持同一口径。
        c.add(OK, "line_budget", "当前是模板仓库（存在 modules/），本项检查不适用")
        return
    for path, key, label in (
        (c.root / "CLAUDE.md", "claude_md_max_lines", "CLAUDE.md（内核）"),
        (c.mem / "BOOT.md", "boot_md_max_lines", "BOOT.md（状态快照）"),
    ):
        if not path.exists():
            c.add(WARN, "line_budget", f"{label} 不存在（期望在 {path}）")
            continue
        n = len(path.read_text(encoding="utf-8").splitlines())
        budget = c.cfg[key]
        if n > budget:
            c.add(FAIL, "line_budget", f"{label} 有 {n} 行，超出预算 {budget} 行——该下沉到下一层了")
        elif n > budget * 0.85:
            c.add(WARN, "line_budget", f"{label} 有 {n} 行，接近预算上限 {budget} 行")
        else:
            c.add(OK, "line_budget", f"{label} {n}/{budget} 行")


def check_agents_sync(c: Ctx) -> None:
    """AGENTS.md 必须是 CLAUDE.md 的生成物，否则必然漂移。"""
    claude, agents = c.root / "CLAUDE.md", c.root / "AGENTS.md"
    if not claude.exists() or not agents.exists():
        return  # 没用 AGENTS.md 的项目跳过
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from sync_agents_md import render_agents_md  # type: ignore
    except Exception:
        return
    if agents.read_text(encoding="utf-8") != render_agents_md(claude.read_text(encoding="utf-8")):
        c.add(FAIL, "agents_sync", "AGENTS.md 与 CLAUDE.md 不同步 → 运行 tools/sync_agents_md.py")
    else:
        c.add(OK, "agents_sync", "AGENTS.md 与 CLAUDE.md 同步")


def check_staleness(c: Ctx) -> None:
    """状态文件必须带陈旧度信号，且不能太久没更新。"""
    for name in ("BOOT.md", "current_state.md"):
        path = c.mem / name
        if not path.exists():
            continue
        body = path.read_text(encoding="utf-8")[:2000]
        m = UPDATED_RE.search(body)
        if not m:
            c.add(WARN, "staleness", f"{name} 顶部缺少 `**Updated**: YYYY-MM-DD` 陈旧度信号")
            continue
        # 脚手架态：日期是初始化脚本盖的章，不是维护记录。
        # 报「更新于 0 天前」虽为真却毫无意义——它会把一份从未维护过的文件伪装成新鲜状态。
        #
        # 判据锚定在**陈旧度信号所在的那一行**，而不是整个 body：文档里别处（比如解释这条
        # 规则本身的段落）提到这几个字，不该被当成"还处于脚手架态"。上一版用的是全 body
        # 子串匹配，于是任何一处提及都会让本文件永远退不出脚手架态。
        scaffold = any(
            UPDATED_RE.search(line) and SCAFFOLD_MARK in line for line in body.splitlines()
        )
        if scaffold:
            c.add(OK, "staleness", f"{name} 仍是脚手架状态（尚无真实会话）——日期不代表项目进度")
            continue
        try:
            days = (date.today() - datetime.strptime(m.group(1), "%Y-%m-%d").date()).days
        except ValueError:
            c.add(WARN, "staleness", f"{name} 的日期无法解析：{m.group(1)}")
            continue
        # 仍带 `[TODO]` = 这份状态文件还没被真正填过。
        # 光删掉「脚手架初始化」标注就能让本检查报「更新于 0 天前」——**一条文档指令
        # 把防编造守卫变成了假绿灯**（冷启动验收实测复现）。标注是文档层的自愿信号，
        # 挡不住一个照着指令办事的 Agent，所以这里补一道工具层的判据。
        n_todo = len(TODO_MARK_RE.findall(body))
        tail = f"（但仍有 {n_todo} 处 `[TODO]` 未填——这份状态还不能当作已维护过）" if n_todo else ""
        if name == "BOOT.md" and days > c.cfg["boot_stale_days"]:
            c.add(WARN, "staleness", f"BOOT.md 已 {days} 天未更新——状态快照可能已经失真{tail}")
        else:
            c.add(OK, "staleness", f"{name} 更新于 {days} 天前{tail}")


def check_session_logs(c: Ctx) -> None:
    """日志命名规范 + 每份日志都必须在 current_state.md 索引里出现。"""
    logs_dir = c.mem / "session_logs"
    if not logs_dir.is_dir():
        return
    logs = sorted(p.name for p in logs_dir.glob("*.md") if not p.name.startswith("_"))
    for name in logs:
        if not SESSION_LOG_RE.match(name):
            c.add(WARN, "session_logs", f"命名不合规：{name}（应为 session_YYYYMMDD_<slug>.md）")

    state = c.mem / "current_state.md"
    if not state.exists():
        return
    body = state.read_text(encoding="utf-8")
    missing = [n for n in logs if n not in body]
    if missing:
        shown = "、".join(missing[:3]) + ("…" if len(missing) > 3 else "")
        c.add(
            FAIL,
            "session_logs",
            f"{len(missing)} 份日志未登记到 current_state.md 索引：{shown}"
            "（索引是历史目录唯一的检索入口）",
        )
    else:
        c.add(OK, "session_logs", f"{len(logs)} 份日志均已登记，命名合规")


def check_plans(c: Ctx) -> None:
    """计划必须有生命周期：至多一个 active，被取代的必须写明取代者。"""
    plans_dir = c.mem / "plans"
    if not plans_dir.is_dir():
        return
    plans = [p for p in plans_dir.glob("*.md") if not p.name.startswith("_")]
    if not plans:
        return

    actives, problems = [], []
    for p in plans:
        text = p.read_text(encoding="utf-8")
        m = re.match(r"^---\s*\n(.*?)\n---", text, re.S)
        if not m:
            problems.append(f"{p.name} 缺少 frontmatter")
            continue
        fm = m.group(1)
        status = (re.search(r"^status:\s*(\S+)", fm, re.M) or [None, ""])[1]
        if status not in ("active", "done", "superseded"):
            problems.append(f"{p.name} 的 status 非法或缺失（当前：{status!r}）")
            continue
        if status == "active":
            actives.append(p.name)
        if status == "superseded" and not re.search(r"^superseded_by:\s*\S+", fm, re.M):
            problems.append(f"{p.name} 标为 superseded 但未填 superseded_by")
        if not PLAN_FILE_RE.match(p.name):
            problems.append(f"{p.name} 命名不合规（应为 YYYY-MM-DD-<kebab>.md）")

    if len(actives) > 1:
        c.add(FAIL, "plans", f"有 {len(actives)} 份 active 计划（至多一份）：{'、'.join(actives)}")
    for msg in problems:
        c.add(WARN, "plans", msg)
    if not problems and len(actives) <= 1:
        c.add(OK, "plans", f"{len(plans)} 份计划，active={len(actives)}")


def check_mirror_rule(c: Ctx) -> None:
    """绘图脚本与图片目录必须 1:1 对应（镜像规则）。"""
    plot_root, fig_root = c.root / "experiments" / "plot", c.root / "figures"
    if not plot_root.is_dir() or not fig_root.is_dir():
        return
    for tier in ("exploratory", "curated"):
        scripts = {p.stem for p in (plot_root / tier).glob("*.py") if not p.name.startswith("_")}
        folders = {p.name for p in (fig_root / tier).iterdir() if p.is_dir()} if (fig_root / tier).is_dir() else set()
        if not scripts and not folders:
            continue
        for orphan in sorted(folders - scripts):
            c.add(WARN, "mirror_rule", f"{tier}/ 有图目录 `{orphan}` 但没有对应脚本（孤儿产物）")
        for missing in sorted(scripts - folders):
            c.add(WARN, "mirror_rule", f"{tier}/ 有脚本 `{missing}.py` 但没有对应图目录")
        if scripts == folders and scripts:
            c.add(OK, "mirror_rule", f"{tier}/ 镜像规则完整（{len(scripts)} 对）")


def check_plot_numbering(c: Ctx) -> None:
    """{NN} 必须是唯一键——一旦撞号，任何基于编号的自动映射都会失效。"""
    plot_root = c.root / "experiments" / "plot"
    if not plot_root.is_dir():
        return
    for tier in ("exploratory", "curated"):
        tier_dir = plot_root / tier
        if not tier_dir.is_dir():
            continue
        seen: dict[str, list[str]] = {}
        for p in tier_dir.glob("*.py"):
            m = PLOT_NAME_RE.match(p.name)
            if not m:
                c.add(WARN, "plot_numbering", f"{tier}/{p.name} 不符合 {{NN}}-{{kebab-name}} 命名")
                continue
            seen.setdefault(m.group(1), []).append(p.name)
        for nn, names in sorted(seen.items()):
            if len(names) > 1:
                c.add(FAIL, "plot_numbering", f"{tier}/ 编号 {nn} 撞号：{'、'.join(names)}")
        if seen:
            nums = sorted(int(k) for k in seen)
            gaps = [n for n in range(1, max(nums) + 1) if n not in nums]
            if gaps:
                c.add(WARN, "plot_numbering", f"{tier}/ 编号不连续，缺：{gaps}")
            elif not any(len(v) > 1 for v in seen.values()):
                c.add(OK, "plot_numbering", f"{tier}/ 编号唯一且连续（01–{max(nums):02d}）")


def check_run_json(c: Ctx) -> None:
    """每个实验结果目录都应有 run.json 溯源记录（两种布局都认）。

    除了扁平的 `results/<实验名>/run.json`，也认协议里的分层布局
    `results/<实验名>/<格>/<run_id>/run.json`（见 `docs/experiment_protocol.md`）。
    不做这层兜底，照协议落地的项目会被整片报成"没有 run.json"——
    一个**设计时已知**的落差会以"项目出错"的面目出现，而那时没人记得它其实是已知的。
    """
    results = c.root / "results"
    if not results.is_dir():
        return
    exp_dirs = [d for d in results.iterdir() if d.is_dir()]
    if not exp_dirs:
        return
    # 与 run.schema.json 的 required 保持一致（6 项）。
    # 只查 4 项会让「schema 说必填、检查器不查」的两个字段长期无人过问。
    required = ("run_id", "started_at", "config", "git_commit", "seed", "note")
    missing_dirs, bad, deep_layout = [], [], []
    for d in exp_dirs:
        flat = d / "run.json"
        if flat.exists():
            found = [flat]
        else:
            found = sorted(d.glob("*/run.json")) + sorted(d.glob("*/*/run.json"))
        if not found:
            missing_dirs.append(d.name)
            continue
        if flat not in found:
            deep_layout.append((d.name, len(found)))
        for rj in found:
            label = rj.relative_to(c.root).as_posix()
            try:
                data = json.loads(rj.read_text(encoding="utf-8"))
            except json.JSONDecodeError as e:
                bad.append(f"{label} 不是合法 JSON（{e.msg}）")
                continue
            lack = [k for k in required if k not in data]
            if lack:
                bad.append(f"{label} 缺字段：{'、'.join(lack)}")
    for msg in bad:
        c.add(WARN, "run_json", msg)
    if missing_dirs:
        shown = "、".join(missing_dirs[:4]) + ("…" if len(missing_dirs) > 4 else "")
        c.add(
            WARN,
            "run_json",
            f"{len(missing_dirs)} 个结果目录没有 run.json：{shown}"
            "（没有它，这个数字是哪次跑的就无从查证）",
        )
    if deep_layout:
        detail = "、".join(f"{n}({k})" for n, k in deep_layout)
        c.add(
            OK,
            "run_json",
            f"{len(deep_layout)} 个实验目录采用分层布局并按此复核：{detail}",
        )
    if not bad and not missing_dirs:
        c.add(OK, "run_json", f"{len(exp_dirs)} 个结果目录均有合规 run.json")


# 只校验**含 `/` 的路径 token**。裸文件名（如 `BOOT.md`）在文档里既可能是真实引用，
# 也可能是举例（"例如 `gpu_setup.md`"），无法可靠区分——收紧到含路径分隔符的写法，
# 既能抓到真正有害的断链，又不产生噪音。
# 字符类**必须允许占位符**（`configs/<name>.yaml`），否则整条 token 匹配不上、
# 被静默跳过，恰好漏掉最常见的那类断链。
#
# 结尾的 `+` 曾改成 `*`，想覆盖 `` `meetings/` `` 这类**裸目录引用**（它确实是个悬空引用，
# 而旧写法看不见）。**改完又改回来了，因为数过代价**：默认落地立刻多 3 条误报
# （`common.py` 里"（如 `models/`、`data/`）"的举例、以及相对 `experiments/` 说的 `plot/`），
# 装全模块时多 7 条（`cloud/archive/README.md` 里的目录树、相对 `cloud/` 说的 `package/`、
# 以及**只存在于 zip 内部**的 `cloud_package/`、`cloud_scripts/`）。
# 结论：这个生态里的裸目录 token **绝大多数出现在举例与相对叙述里**，
# 按字面校验它们，换来的噪音远大于收益。
# 真正要治的那条改用**语义判据**——见 uninstalled_module_prefixes。
# 教训：**放宽一条正则之前，先数一遍它会新增多少条误报**；想清楚再改，改完再数。
PATH_TOKEN_RE = re.compile(r"`([A-Za-z0-9_][A-Za-z0-9_./<>{},*-]*/[A-Za-z0-9_./<>{},*-]+)`")
# 不校验的 token：含省略号或变量的，以及平台路径
PATH_SKIP_CHARS = set("…$")
PATH_SKIP_PREFIX = ("http", "~", "E:", "C:", "D:", "/")
PLACEHOLDER_CHARS = set("<>{}*")


def static_prefix(tok: str) -> str | None:
    """取路径中第一个含占位符的段**之前**的部分。

    `configs/<name>.yaml` → `configs`：占位符挡住的那一段不知道，但它前面的目录必须真实存在。
    这正是冷启动验收抓到 `configs/` 缺失的路径——如果因为含 `<>` 就整条跳过，这个缺陷会漏掉。
    返回 None 表示整条都是占位符，无从校验。
    """
    parts = tok.split("/")
    static: list[str] = []
    for p in parts:
        if any(ch in p for ch in PLACEHOLDER_CHARS):
            break
        static.append(p)
    return "/".join(static) or None


def template_repo_dirs(root: Path, max_depth: int = 3) -> set[Path]:
    """找出「看起来是模板仓库」的目录：同时含 `core/` 与 `modules/`。

    模板仓库是可以被**内嵌**的——例如某个项目把整套模板放进 `template/`，
    再在根目录建立它自己的记忆系统（本项目正是这个形态）。
    这些目录里的文档是按**落地后**的结构写的（`cloud/…`、`experiments/…`），
    用「落地项目」的规则去查它们只会产生成片的假警报。

    命中即止：某目录一旦判定为模板仓库，就不再往它内部找——里面的东西全属于模板。
    """
    found: set[Path] = set()
    stack: list[tuple[Path, int]] = [(root, 0)]
    while stack:
        d, depth = stack.pop()
        if (d / "core").is_dir() and (d / "modules").is_dir():
            found.add(d)
            continue
        if depth >= max_depth:
            continue
        try:
            stack.extend(
                (p, depth + 1) for p in d.iterdir() if p.is_dir() and not p.name.startswith(".")
            )
        except OSError:
            continue
    return found


def under_any_template(p: Path, dirs: set[Path]) -> bool:
    """`p` 是否位于某个模板仓库目录之内（含自身）。"""
    return any(d == p or d in p.parents for d in dirs)


# 记忆目录下这些子目录里是**历史与实例文档**，其中的路径可能是举例、
# 也可能指向后来被删的东西——校验它们只会产生噪音。
DEAD_LINK_EXCLUDE_DIRS = {"session_logs", "plans", "prompts"}
# 这些路径下的文档里的"路径"多是叙述/举例，校验它们只会产生噪音
DEAD_LINK_EXCLUDE_PREFIXES = {"docs", "package", ".git", "node_modules", "__pycache__", ".venv", "venv"}


def dead_link_targets(c: Ctx) -> list[Path]:
    """需要校验路径引用的文档。

    **覆盖范围（有意收窄，不要想当然）**：只覆盖「Agent 靠它导航」的文件——
    根目录的 `CLAUDE.md`/`AGENTS.md`/`README.md`、`agent_memory/` 下的常驻文档、
    以及各模块落地后的顶层 `*/README.md`。

    **不覆盖**：背景文档（`docs/`）、组会与论文笔记（`meetings/`）、历史日志与计划、
    以及包的内部说明文档——那里的路径多为举例或产物清单，校验它们没有收益。
    """
    docs = [c.root / "CLAUDE.md", c.root / "AGENTS.md", c.root / "README.md"]
    if c.mem.is_dir():
        docs += [
            p
            for p in c.mem.rglob("*.md")
            if not p.name.startswith("_")
            and not DEAD_LINK_EXCLUDE_DIRS & set(p.relative_to(c.mem).parts)
        ]
    # 任意深度的 README，但排除两类：
    #   - `docs/`：背景文档里的路径多是叙述与举例
    #   - `cloud/package/`：包内说明文档会画"包解压后长什么样"的树，路径在项目里本就不存在
    docs += [
        p
        for p in c.root.rglob("README.md")
        if p.is_file() and not DEAD_LINK_EXCLUDE_PREFIXES & set(p.relative_to(c.root).parts)
    ]
    # Python 文件也算：反引号在 Python 里**不是合法语法**，所以 `` `路径` `` 只会出现在
    # docstring 与注释里——也就是说，凡是被反引号包起来的路径 token 都是散文引用，
    # 不是代码。这让同一条检查能无痛覆盖 .py，补上「脚本 docstring 指向不存在的文档」这个盲区。
    docs += [
        p
        for p in c.root.rglob("*.py")
        if p.is_file()
        and p.name != "check_conventions.py"  # 本文件的注释里就在举例「坏路径」，不能自检
        and not DEAD_LINK_EXCLUDE_PREFIXES & set(p.relative_to(c.root).parts)
    ]
    # 内嵌的模板仓库整体让路：它的文档按落地后的结构书写，本就不该按本项目的规则校验
    tdirs = template_repo_dirs(c.root)
    return sorted({p for p in docs if p.exists() and not under_any_template(p, tdirs)})


def check_dead_links(c: Ctx) -> None:
    """导航性文档里引用的路径必须真实存在。

    冷启动验收连续两轮抓到的都是同一类问题：文档指向不存在的文件
    （`configs/` 目录缺失、模板仓库内部路径被原样带进项目）。这类断链人眼极难发现——
    作者知道自己的意思，读者却会走进死胡同。
    """
    if c.root in template_repo_dirs(c.root):
        # 模板仓库自身的文档按**落地后**的结构书写（`cloud/…`、`experiments/…`），
        # 那些路径在模板仓库里当然不存在。本检查只对落地项目有意义。
        c.add(OK, "dead_links", "当前是模板仓库（同时存在 core/ 与 modules/），本项检查不适用")
        return

    targets = dead_link_targets(c)
    missing: set[tuple[str, str]] = set()
    # 按配置跳过的：指向**未安装模块**的引用。它们不是断链——模块没装，
    # 这些路径本就不该存在，而内核与路由表都已在散文里写明"可删掉该行"。
    uninstalled = tuple(c.cfg.get("uninstalled_module_prefixes", ()))
    # 与项目原有目录**混在一起**的模块路径（research 的 experiments/、results/…
    # 没有独占顶层目录，没法用"前缀在不在"判断），由模块自己声明后写进配置。
    uninstalled_paths = tuple(c.cfg.get("uninstalled_module_paths", ()))
    skipped_modules: dict[str, int] = {}
    for f in targets:
        for m in PATH_TOKEN_RE.finditer(f.read_text(encoding="utf-8")):
            tok = m.group(1)
            if any(ch in tok for ch in PATH_SKIP_CHARS) or "..." in tok:
                continue
            if tok.startswith(PATH_SKIP_PREFIX):
                continue
            if tok in c.cfg.get("dead_link_ignore", ()):
                continue
            top = tok.split("/", 1)[0]
            if top in uninstalled:
                skipped_modules[top] = skipped_modules.get(top, 0) + 1
                continue
            declared = next((p for p in uninstalled_paths if tok.startswith(p)), None)
            if declared:
                skipped_modules[declared] = skipped_modules.get(declared, 0) + 1
                continue
            probe = static_prefix(tok)
            if probe is None:
                continue
            probe = probe.rstrip("/")
            # 相对路径有两种合理写法：相对项目根，或相对本文件所在目录。
            # 两者取其一能解析即算通过——否则会把 `cloud/README.md` 里
            # 正确写作 `archive/README.md` 的引用误报成断链。
            if (c.root / probe).exists() or (f.parent / probe).exists():
                continue
            detail = f"`{tok}`" if probe == tok else f"`{tok}`（前置目录 `{probe}/` 不存在）"
            missing.add((f.name, detail))

    for name, detail in sorted(missing):
        c.add(WARN, "dead_links", f"{name} 引用了不存在的路径：{detail}")
    if skipped_modules:
        # 跳过要**报出来**，不能静默——静默跳过正是本检查器一再犯的那个错。
        detail = "、".join(f"{k}({v})" for k, v in sorted(skipped_modules.items()))
        c.add(
            OK,
            "dead_links",
            f"已按配置跳过 {sum(skipped_modules.values())} 条指向未安装模块的引用：{detail}",
        )
    if not missing:
        # 说清**覆盖了哪些文件**。上一版只说"N 份记忆文件"，读起来像全项目结论，
        # 而 `docs/`、`meetings/`、历史日志其实都被有意排除在外（见 dead_link_targets）。
        c.add(
            OK,
            "dead_links",
            f"{len(targets)} 份**导航性**文件（内核/状态文档/各 README/全部 .py）中的路径引用均可解析"
            "——背景文档与历史目录不在覆盖范围内",
        )


# 尾随斜杠**可选**：`modules/cloud` 与 `modules/cloud/` 都是残留，
# 上一版要求必须有 `/`，结果漏掉了 `.gitignore` 里的 `modules/cloud`。
TEMPLATE_PATH_RE = re.compile(r"modules/(?:research|reproduction|cloud|meetings|hooks)(?=[/\s,)]|$)")
TEMPLATE_LEAK_SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", ".idea"}
# 模板仓库的措辞。落地后的项目里没有「模块」这一层，出现即是没改干净。
TEMPLATE_PHRASE_RE = re.compile(r"本模块|该模块|模块的 README|模块 README")


def check_template_leaks(c: Ctx) -> None:
    """落地后的项目里不该出现「模板仓库内部路径」。

    模板文件在仓库里写作 `modules/cloud/docs/xxx.md`，但落地后该文件变成
    `<项目>/cloud/docs/xxx.md`——路径里的 `modules/<模块名>/` 前缀必须去掉。
    漏掉一处，读者就会走进一个**在项目里根本不存在**的路径。

    这条检查零假阳性：已落地的项目结构里没有 `modules/` 这一层，
    所以任何 `modules/<模块名>/` 的出现都是泄漏。
    """
    tdirs = template_repo_dirs(c.root)
    if c.root in tdirs:
        # 被检查的就是**模板仓库本身**——它当然有 `modules/`，文档里当然会提到它。
        # 这条检查的目标是「落地后的项目」，在模板仓库里跑没有意义，自动让路。
        c.add(OK, "template_leaks", "当前是模板仓库（同时存在 core/ 与 modules/），本项检查不适用")
        return

    leaks: list[tuple[str, int]] = []
    for p in c.root.rglob("*"):
        if not p.is_file() or TEMPLATE_LEAK_SKIP_DIRS & set(p.parts):
            continue
        if under_any_template(p, tdirs):
            continue  # 内嵌模板仓库的内容整体让路（见 template_repo_dirs 的说明）
        if p.suffix.lower() not in {".md", ".py", ".json", ".tmpl", ".txt", ".yaml", ".yml", ".sh"}:
            continue
        if p.name in {"MODULE.md", "module.json"}:
            continue  # 模块自身的文档，本来就该写模板仓库路径
        if p.name == "check_conventions.py":
            continue  # 本检查器的正则源码里就含这个模式，自引用不算泄漏
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        # 「本模块」在自然语言文档里是模板仓库措辞，但在 .py 里指的是 Python module，
        # 是正确用法——所以措辞检查只作用于文档，路径检查才作用于所有文件。
        # 注意：`.tmpl` 要**先剥掉再判断**——`common.py.tmpl` 落地后是 `common.py`，
        # 里面那个「本模块」是 Python module 语义，按 `.tmpl` 判成文档就会误报。
        landed = p.with_suffix("") if p.suffix.lower() == ".tmpl" else p
        is_prose = landed.suffix.lower() in {".md", ".txt", ""}
        # 措辞检查可被项目显式关掉：**模板仓库自己的家**里「模块」是原生词汇，
        # 讨论模块是正当的，不是未改干净的残留。**只关措辞，不关路径**——
        # 路径泄漏在任何语境下都是错的。
        if c.cfg.get("module_vocabulary_is_native"):
            is_prose = False
        for lineno, line in enumerate(text.splitlines(), 1):
            # URL 里的路径段（如 schema 的 $id）不是文件引用，先剥掉再判断
            scrubbed = re.sub(r"https?://\S+", "", line)
            hit_path = TEMPLATE_PATH_RE.search(scrubbed)
            hit_prose = is_prose and TEMPLATE_PHRASE_RE.search(scrubbed)
            if hit_path or hit_prose:
                leaks.append((str(p.relative_to(c.root)), lineno, "路径" if hit_path else "措辞"))

    for path, lineno, kind in leaks:
        detail = (
            "残留模板仓库路径 `modules/<模块名>/`——落地时应去掉此前缀"
            if kind == "路径"
            else "残留模板仓库措辞（如「本模块」）——落地后项目里没有「模块」这一层"
        )
        c.add(WARN, "template_leaks", f"{path}:{lineno} {detail}")
    if not leaks:
        c.add(OK, "template_leaks", "无模板仓库路径残留")


CHECKS = [
    ("template_leaks", check_template_leaks, "模板仓库路径是否残留"),
    ("dead_links", check_dead_links, "记忆文件中的路径引用是否存在"),
    ("line_budget", check_line_budget, "tier-0/tier-1 行数预算"),
    ("agents_sync", check_agents_sync, "AGENTS.md 与 CLAUDE.md 同步"),
    ("staleness", check_staleness, "状态文件陈旧度"),
    ("session_logs", check_session_logs, "会话日志命名与索引"),
    ("plans", check_plans, "计划生命周期"),
    ("mirror_rule", check_mirror_rule, "绘图脚本↔图片目录镜像"),
    ("plot_numbering", check_plot_numbering, "图表编号唯一性"),
    ("run_json", check_run_json, "实验溯源 run.json"),
]


def main() -> int:
    ap = argparse.ArgumentParser(description="校验记忆系统与目录约定")
    ap.add_argument("--root", default=None, help="项目根目录（默认：本脚本的上一级）")
    ap.add_argument("--strict", action="store_true", help="有 ⚠️ 也算不通过")
    ap.add_argument("--only", action="append", default=None, metavar="NAME", help="只跑指定检查")
    ap.add_argument("--list", action="store_true", help="列出所有检查项后退出")
    args = ap.parse_args()

    if args.list:
        for name, _, desc in CHECKS:
            print(f"  {name:<16} {desc}")
        return 0

    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parent.parent
    cfg = dict(DEFAULTS)
    cfg_file = root / ".memory-system.json"
    if cfg_file.exists():
        try:
            cfg.update(json.loads(cfg_file.read_text(encoding="utf-8")))
        except json.JSONDecodeError as e:
            print(f"❌ .memory-system.json 解析失败：{e}", file=sys.stderr)
            return 2

    # `--only` 写错名字时**必须报错**：否则它会静默跑 0 项并退出 0，
    # 一次「通过」实际上什么都没检查——这比检查失败危险得多。
    known = [name for name, _, _ in CHECKS]
    if args.only:
        unknown = [n for n in args.only if n not in known]
        if unknown:
            print(f"❌ 未知检查项：{', '.join(unknown)}", file=sys.stderr)
            print(f"   可用：{', '.join(known)}", file=sys.stderr)
            print("   提示：用 --list 查看带说明的清单。", file=sys.stderr)
            return 2

    ctx = Ctx(root, cfg)
    selected = [c for c in CHECKS if not args.only or c[0] in args.only]
    disabled = [n for n, _, _ in selected if not ctx.enabled(n)]
    for name, fn, _ in selected:
        if ctx.enabled(name):
            fn(ctx)

    ran = {check for _, check, _ in ctx.results}
    silent = [n for n, _, _ in selected if ctx.enabled(n) and n not in ran]

    # 与「未知检查项」是同一类危险：退出码 0 会被读成「通过」，而实际上一项都没检查。
    # 上一版只拦未知名字（见上），已知但**不适用**的名字原样保留了同一个洞。
    if args.only and not ran:
        print(
            f"❌ 请求的检查项（{', '.join(args.only)}）未产出任何结果——\n"
            "   退出码 0 会被读成「通过」，但实际什么都没检查。\n"
            "   常见原因：该项的前置目录/文件还不存在（如 results/、plans/、figures/），\n"
            "   或该项已被 .memory-system.json 的 checks 关闭。",
            file=sys.stderr,
        )
        return 2

    print(f"\n约定校验 — {root}\n" + "─" * 60)
    for severity, check, message in ctx.results:
        print(f"{ICON[severity]} [{check}] {message}")

    # 「没产出结果」不等于「通过」。报出来，别让它伪装成覆盖面——
    # 否则「共 N 项检查」这句汇总行会把实际没跑的部分算成已检查。
    for n in disabled:
        print(f"➖ [{n}] 已在 .memory-system.json 中关闭，本次未运行")
    if silent:
        print(
            f"➖ 未产出结果的检查（{len(silent)} 项）：{', '.join(silent)}"
            "——通常是前置目录尚未出现，**不代表通过**"
        )

    n_fail = sum(1 for s, _, _ in ctx.results if s == FAIL)
    n_warn = sum(1 for s, _, _ in ctx.results if s == WARN)
    n_checks = len({check for _, check, _ in ctx.results})
    print("─" * 60)
    # 刻意区分「检查项」与「结果条数」：一个检查可能产出多条结果，
    # 把条数写成项数会让人以为跑了比实际更多的检查。
    # 零失败时不要打红叉——一个「❌ 0 项失败」会让人以为出了问题
    mark = "❌" if n_fail else "✅"
    print(
        f"{mark} {n_fail} 项失败 · ⚠️  {n_warn} 项警告 · "
        f"共 {n_checks} 项检查 / {len(ctx.results)} 条结果"
    )

    if n_fail or (args.strict and n_warn):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
