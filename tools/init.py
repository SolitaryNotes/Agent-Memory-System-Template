#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""init.py — 把一个项目的 Agent 记忆系统脚手架落地到目标目录

用法
----
    # 交互式（推荐：会逐项问清楚，其余留成 TODO 标记）
    python tools/init.py --target D:/path/to/new-project

    # 非交互（全部用默认值，适合脚本化）
    python tools/init.py --target DIR --yes \
        --name "My Project" --desc "一句话说明" --modules research,cloud

    # 只看会做什么，不写任何文件
    python tools/init.py --target DIR --dry-run

设计要点
--------
1. **只写目标目录，绝不触碰任何其它路径。** 目标目录已存在同名文件时，默认跳过并报告，
   不加 --force 绝不覆盖。
2. **能自动填的自动填，填不了的留成显式 `[TODO: ...]` 标记**，而不是留下刺眼的 `{{占位符}}`。
   结束后会把所有 TODO 列出来，交给 Agent 在会话中补齐。
3. **模块可勾选**：core 必装；research / reproduction / cloud / meetings 按需。
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

# Windows 控制台默认 GBK，中文输出会直接抛 UnicodeEncodeError
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except Exception:
        pass

TEMPLATE_ROOT = Path(__file__).resolve().parent.parent

# 结构化占位符 → TODO 提示语。落地时自动替换成 `[TODO: 提示]`。
TODO_HINTS = {
    "TASK_TYPE": "任务类型", "FILES": "涉及文件", "INVARIANT": "关键不变量",
    "ISSUE": "问题", "IMPACT": "影响", "STATUS": "状态", "MODULE": "模块名",
    "FILE": "文件路径", "DESC": "说明", "VAR": "变量", "WHERE": "位置",
    "VALUES": "可选值", "PRINCIPLE": "设计原则标题", "PRINCIPLE_BODY": "原则的理由（必须写理由）",
    "Q": "子问题 / 子目标", "Q_STATUS": "该子问题的状态", "NOT_DOING": "明确不做的事",
    "CATEGORY": "分类", "TODO": "待办事项", "DETAIL": "细节", "LOG": "对应会话日志文件名",
    "PLANNED": "计划中的事项", "DONE": "已完成的事项", "FINDING": "核心发现",
    "RESULTS_TREE": "结果目录树", "DIR_TREE": "项目目录树", "DATE_RANGE": "日期范围",
    "LOG_FILE": "日志文件名", "SUMMARY": "一句话摘要", "TOPIC_DOC": "专题文档文件名",
    "TOPIC": "主题", "WHEN": "何时该读它", "UPDATE_REASON": "本次更新原因",
    "PRIORITY": "优先级", "CURRENT_TASK": "当前任务", "BLOCKER": "阻塞点；无则填「无」",
    "ACTIVE_PLAN": "活跃计划文件名；无则填「无」", "LAST_SESSION": "最近一次会话日志文件名",
    "DEBUG_CMDS": "常用调试命令",
}

PLACEHOLDER_RE = re.compile(r"\{\{([A-Z0-9_]+)\}\}")


def hint_for(name: str) -> str:
    # 去掉序号段：TASK_TYPE_1 → TASK_TYPE、Q1_STATUS → Q_STATUS、PRINCIPLE_1_BODY → PRINCIPLE_BODY
    base = re.sub(r"_+", "_", re.sub(r"\d+", "", name)).strip("_")
    if base in TODO_HINTS:
        return TODO_HINTS[base]
    # 前缀兜底：长的先匹配，避免 PRINCIPLE 把 PRINCIPLE_BODY 吃掉
    for key in sorted(TODO_HINTS, key=len, reverse=True):
        if base.startswith(key):
            return TODO_HINTS[key]
    return name


def detect_git_branch(target: Path) -> tuple[bool, str]:
    """目标目录**自身**是不是 git 仓库；是的话顺便取当前分支名。

    只认目标目录**自身**的 `.git`，不认"被某个上层仓库罩着"——后者会让一个尚未 `git init`
    的项目凭空获得一个分支名，而那正是要避免的假断言。
    """
    if not (target / ".git").exists():
        return False, ""
    try:
        r = subprocess.run(
            ["git", "-C", str(target), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return True, ""
    return True, r.stdout.strip() if r.returncode == 0 else ""


def build_globals(a: argparse.Namespace, target: Path) -> dict[str, str]:
    today = date.today().isoformat()
    slug = a.slug or re.sub(r"[^a-z0-9]+", "-", a.name.lower()).strip("-")
    has_git, branch = detect_git_branch(target)
    branch = branch or a.git_branch
    return {
        "PROJECT_NAME": a.name,
        "PROJECT_SLUG": slug,
        "ONE_LINE_DESC": a.desc,
        "GOAL": a.goal,
        "CURRENT_STAGE": a.stage,
        "DOMAIN": a.domain,
        "DATE": today,
        "GIT_REMOTE": a.git_remote,
        "GIT_BRANCH": branch,
        # 没有 git 仓库时整项**不输出**。上一版写死 `Branch: main` 再加一句
        # "尚未 git init 时整项删掉"——把判断推给读者，而读者会先看到事实陈述。
        # 这里能当场判断，就不该让读者去判断。
        "BRANCH_ITEM": f" | **Branch**: {branch}" if has_git else "",
        "BOOT_CMD": a.boot_cmd,
        "ENTRY_CMD": a.entry_cmd,
        "QUICK_START_CMDS": f"{a.boot_cmd}\n{a.entry_cmd}",
        "CLAUDE_MAX_LINES": str(a.claude_max_lines),
        "NAMING_RULES": a.naming_rules,
        "STYLE_RULES": a.style_rules,
        # 状态类：一律留 TODO，交给会话里的 Agent 填
        "PRIORITY": "[TODO: 优先级]",
        "CURRENT_TASK": "[TODO: 当前任务]",
        "BLOCKER": "[TODO: 阻塞点；无则填「无」]",
        "ACTIVE_PLAN": "[TODO: 活跃计划文件名，无则填「无」]",
        "LAST_SESSION": "[TODO: 最近会话日志文件名]",
        "UPDATE_REASON": "[TODO: 本次更新原因]",
    }


def substitute(text: str, values: dict[str, str], unresolved: set[str]) -> str:
    """先替换已知值，再把剩余的 {{X}} 变成显式 TODO 标记。"""
    for key, val in values.items():
        text = text.replace("{{" + key + "}}", val)

    def repl(m: re.Match[str]) -> str:
        name = m.group(1)
        unresolved.add(name)
        return f"[TODO: {hint_for(name)}]"

    return PLACEHOLDER_RE.sub(repl, text)


def module_config(mod_root: Path) -> dict:
    cfg = mod_root / "module.json"
    if not cfg.exists():
        return {}
    try:
        return json.loads(cfg.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        print(f"⚠️  {cfg} 不是合法 JSON，按默认值处理", file=sys.stderr)
        return {}


def optional_module_prefixes() -> dict[str, str]:
    """{模块名: 顶层落点前缀}，只含前缀非空的模块。

    前缀为空的模块（research / reproduction）落在项目根，与项目自身目录混在一起，
    没法按前缀区分——只有 `cloud/`、`meetings/`、`hooks/` 这类独占顶层目录的模块
    才能靠"这个目录该不该存在"来判断引用是不是断链。
    """
    out: dict[str, str] = {}
    mods_dir = TEMPLATE_ROOT / "modules"
    if not mods_dir.is_dir():
        return out
    for d in sorted(mods_dir.iterdir()):
        if d.is_dir():
            prefix = str(module_config(d).get("target_prefix", "") or "").strip("/")
            if prefix:
                out[d.name] = prefix
    return out


def uninstalled_module_paths(installed: list[str]) -> list[str]:
    """未安装模块会贡献的顶层路径。

    有些模块（research / reproduction）落地后与项目原有目录**混在一起**，
    没有独占的顶层目录可供识别——它们引用的 `experiments/`、`results/`、`run.schema.json`
    一旦被校验器当成断链，就会产生成片假警报（本项目的首次落地实测到 7 条）。
    所以让模块自己在 `module.json` 里声明 `landed_paths`，由这里汇总未安装的那些。
    """
    out: list[str] = []
    mods_dir = TEMPLATE_ROOT / "modules"
    if not mods_dir.is_dir():
        return out
    for d in sorted(mods_dir.iterdir()):
        if d.is_dir() and d.name not in installed:
            out.extend(str(p) for p in (module_config(d).get("landed_paths") or []))
    return sorted(set(out))


def check_target_safety(target: Path) -> str | None:
    """落地目标的安全检查。通过则返回 None，否则返回拒绝理由。

    **为什么这道守卫要放在脚本里，而不是只写在 Prompt 的「暂停条件」里**：
    Prompt 是会被绕过的——直接敲 `init.py` 就看不到它。放进脚本本身，
    command / Prompt / 手敲命令三条路径才受同一道守卫。
    （与本项目一贯做法一致：能钉死在机制里的，不留给流程自觉。）

    刻意**不**拦的情况：目标目录不存在（那就新建）、目标是某个已有项目
    （文件已存在时默认跳过，不会覆盖）。
    """
    repo_root = TEMPLATE_ROOT.parent
    if target == repo_root:
        return f"目标是模板仓库自身（{repo_root}）——那会把模板与项目混在一起"
    if target == TEMPLATE_ROOT or TEMPLATE_ROOT in target.parents:
        return f"目标在 {TEMPLATE_ROOT.name}/ 内部——那是模板的源，不是落地位置"
    if target == target.parent:
        return f"目标是磁盘根目录（{target}）——不像是一个项目"
    try:
        if target == Path.home():
            return f"目标是用户主目录（{target}）——不像是一个项目"
    except RuntimeError:
        pass
    return None


def plan_files(modules: list[str]) -> tuple[list[tuple[Path, Path]], list[str]]:
    """返回 (源文件, 目标相对路径) 列表，以及未知模块名列表。"""
    plan: list[tuple[Path, Path]] = []
    unknown: list[str] = []

    for src in sorted((TEMPLATE_ROOT / "core").rglob("*")):
        if src.is_file():
            if _is_build_artifact(src):
                continue
            rel = src.relative_to(TEMPLATE_ROOT / "core")
            if rel.name == "gitignore.tmpl":
                continue  # .gitignore 由主流程合并各模块 fragment 后统一生成
            plan.append((src, _strip_tmpl(rel)))

    for mod in modules:
        mod_root = TEMPLATE_ROOT / "modules" / mod
        if not mod_root.is_dir():
            unknown.append(mod)
            continue
        # 落点前缀由模块自己声明，而不是靠「目录名写两遍」这种隐式约定
        prefix = Path(module_config(mod_root).get("target_prefix", "") or "")
        for src in sorted(mod_root.rglob("*")):
            if not src.is_file():
                continue
            if _is_build_artifact(src):
                continue
            rel = src.relative_to(mod_root)
            if rel == Path("MODULE.md") or rel.name == "module.json":
                continue  # 模板自身的说明文档，不落地到项目里
            if rel.name == "gitignore.fragment":
                continue
            plan.append((src, prefix / _strip_tmpl(rel)))

    return plan, unknown


# 构建产物：任何人在模板仓库里跑过一次 `python -m compileall` 就会产生，
# 若不滤掉就会被复制进每一个新落地项目（实测发生过）。
BUILD_ARTIFACT_DIRS = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
BUILD_ARTIFACT_SUFFIXES = {".pyc", ".pyo", ".pyd"}


def _is_build_artifact(p: Path) -> bool:
    return bool(BUILD_ARTIFACT_DIRS & set(p.parts)) or p.suffix.lower() in BUILD_ARTIFACT_SUFFIXES


# 这些文件在模板里**不带前导点**——带了的话，它们会在模板仓库内部就被 git 当作配置读取，
# 作用于 `template/` 子树。落地时才还原成点开头的正式名字。
DOTFILE_RENAME = {"gitignore": ".gitignore", "gitattributes": ".gitattributes"}


def _strip_tmpl(rel: Path) -> Path:
    if rel.suffix == ".tmpl":
        rel = rel.with_suffix("")
    if rel.name in DOTFILE_RENAME:
        rel = rel.with_name(DOTFILE_RENAME[rel.name])
    return rel


def main() -> int:
    ap = argparse.ArgumentParser(description="落地 Agent 记忆系统脚手架")
    ap.add_argument("--target", required=True, help="目标项目目录")
    ap.add_argument("--modules", default="research", help="逗号分隔：research,reproduction,cloud,meetings")
    ap.add_argument("--yes", action="store_true", help="非交互，全部用默认值")
    ap.add_argument("--force", action="store_true", help="覆盖已存在的文件")
    ap.add_argument("--dry-run", action="store_true", help="只打印计划，不写文件")
    ap.add_argument("--name", default=None)
    ap.add_argument("--slug", default=None)
    ap.add_argument("--desc", default="[TODO: 一句话说明本项目做什么]")
    ap.add_argument("--goal", default="[TODO: 项目的最终目标]")
    ap.add_argument("--stage", default="[TODO: 当前阶段]")
    ap.add_argument("--domain", default="[TODO: 领域]")
    ap.add_argument("--git-remote", default="[TODO: git remote]")
    ap.add_argument("--git-branch", default="main")
    ap.add_argument("--boot-cmd", default="[TODO: 环境自检命令]")
    ap.add_argument("--entry-cmd", default="[TODO: 主入口命令]")
    ap.add_argument("--claude-max-lines", type=int, default=100)
    ap.add_argument(
        "--naming-rules",
        default="### 命名约定\n- 新增文件遵循项目既有的同类命名；不确定时先查 `agent_memory/BOOT.md` 路由表。",
    )
    ap.add_argument(
        "--style-rules",
        default=(
            "## Style\n"
            "- 输出与注释语言：**中文**（技术术语保留英文）。\n"
            "- 提交信息：**英文**，Conventional Commits（`feat:` / `fix:` / `docs:`——"
            "type **必须小写**；写成 `Feat:` 不符合该规范，commitlint / semantic-release 解析不了）。"
        ),
        help="写入内核 CLAUDE.md 的风格约定（自带 `## Style` 标题；BOOT.md 不再重复这段）",
    )
    args = ap.parse_args()

    target = Path(args.target).resolve()

    # 守卫在**任何写入之前**跑，`--dry-run` 也照跑——让危险目标在预演阶段就暴露
    refusal = check_target_safety(target)
    if refusal:
        print(f"❌ 拒绝落地：{refusal}", file=sys.stderr)
        print("   这是安全守卫，不是权限问题；换一个目标目录即可。", file=sys.stderr)
        return 2

    modules = [m.strip() for m in args.modules.split(",") if m.strip()]

    if args.name is None:
        if args.yes:
            args.name = target.name
        else:
            print("\n=== 项目基本信息（回车用中括号里的默认值）===\n")
            args.name = input(f"项目名 [{target.name}]: ").strip() or target.name
            args.desc = input("一句话说明: ").strip() or args.desc
            args.goal = input("最终目标: ").strip() or args.goal
            args.stage = input("当前阶段: ").strip() or args.stage
            args.boot_cmd = input("环境自检命令: ").strip() or args.boot_cmd
            args.entry_cmd = input("主入口命令: ").strip() or args.entry_cmd

    values = build_globals(args, target)
    plan, unknown = plan_files(modules)

    if unknown:
        available = sorted(p.name for p in (TEMPLATE_ROOT / "modules").iterdir() if p.is_dir())
        print(f"❌ 未知模块：{', '.join(unknown)}", file=sys.stderr)
        print(f"   可用模块：{', '.join(available)}", file=sys.stderr)
        return 2

    print(f"\n目标目录 : {target}")
    print(f"模块     : core + {', '.join(modules) if modules else '(无)'}")
    print(
        f"将写入   : {len(plan)} 个文件"
        "（另有 .gitignore / AGENTS.md / .memory-system.json / tools/*.py 由脚本生成）\n"
    )

    if args.dry_run:
        for src, rel in plan:
            print(f"  {rel}")
        uninstalled = sorted(p for name, p in optional_module_prefixes().items() if name not in modules)
        print("  .gitignore")
        print("  AGENTS.md（由 CLAUDE.md 生成）")
        print(f"  .memory-system.json（记录未安装模块：{uninstalled or '无'}）")
        print("  tools/check_conventions.py, tools/sync_agents_md.py")
        return 0

    target.mkdir(parents=True, exist_ok=True)

    unresolved: set[str] = set()
    written, skipped = [], []
    for src, rel in plan:
        dst = target / rel
        if dst.exists() and not args.force:
            skipped.append(str(rel))
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.suffix == ".tmpl":
            dst.write_text(substitute(src.read_text(encoding="utf-8"), values, unresolved), encoding="utf-8")
        else:
            shutil.copy2(src, dst)
        written.append(str(rel))

    # 把校验工具装进项目：CLAUDE.md / AGENTS.md 都引用了 tools/ 下的脚本，
    # 不落地就是断链（冷启动验证实测到的问题）。
    for tool in ("check_conventions.py", "sync_agents_md.py"):
        src = TEMPLATE_ROOT / "tools" / tool
        dst = target / "tools" / tool
        if src.exists() and (not dst.exists() or args.force):
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            written.append(f"tools/{tool}")

    # .gitignore = core 模板 + 各模块 fragment
    # rstrip：模板文件自身结尾带空行，不剥掉就会与下面的分隔空行叠成三段
    ignores = [
        substitute(
            (TEMPLATE_ROOT / "core" / "gitignore.tmpl").read_text(encoding="utf-8"),
            values,
            unresolved,
        ).rstrip()
    ]
    for mod in modules:
        frag = TEMPLATE_ROOT / "modules" / mod / "gitignore.fragment"
        if frag.exists():
            # 不写模块名——落地后的项目里没有 `modules/` 这一层，
            # 在注释里提到它只会让读者去找一个不存在的目录
            # 拼成「空行 + 整块」而不是「空行 + 整块 + 空行」：后者会与下一段的空行叠成三个
            ignores.append(f"\n{frag.read_text(encoding='utf-8').strip()}")
    gi = target / ".gitignore"
    if gi.exists() and not args.force:
        skipped.append(".gitignore")
    else:
        gi.write_text("\n".join(ignores).rstrip() + "\n", encoding="utf-8")
        written.append(".gitignore")

    # 告诉校验器「本项目**没装**哪些模块」。不写这个文件，只装 research 的项目
    # 一落地就会报 7 条指向 cloud/hooks 的"断链"——而内核与路由表都写着
    # "未安装的模块路径不存在是正常的，删掉那行即可"。校验器读不懂那句散文，
    # 于是每次冷启动都以一堆"应当忽略"的警告开场，把 Agent 训成忽略这类检查；
    # 真正的那条断链会被一起划过去。
    uninstalled = sorted(p for name, p in optional_module_prefixes().items() if name not in modules)
    mem_cfg = {
        "_comment": (
            # 不要在这里写 `tools/init.py`：那是**模板仓库**里的落地脚本，不随项目落地，
            # 写出来就是一条指向不存在文件的引用（冷启动验收抓到过）。
            "由记忆系统脚手架的初始化脚本生成（该脚本在模板仓库里，**不随本项目落地**，"
            "所以本文件直接手改即可），tools/check_conventions.py 读取。"
            "uninstalled_module_prefixes = 本项目没装的模块的顶层目录名："
            "校验器会跳过指向它们的路径引用（那些路径本就不该存在），"
            "并在结果里单独报出跳过了几条。"
            "**后来手工装了某个模块，记得把它从本列表里删掉**，否则该模块内的断链不会被查。"
            "uninstalled_module_paths = 那些**与项目原有目录混在一起**、"
            "没有独占顶层目录的模块所贡献的路径（如 research 的 experiments/、results/）——"
            "它们同样按未安装处理，合并进同一条跳过统计。"
        ),
        "uninstalled_module_prefixes": uninstalled,
        "uninstalled_module_paths": uninstalled_module_paths(modules),
    }
    cfg_path = target / ".memory-system.json"
    if cfg_path.exists() and not args.force:
        skipped.append(".memory-system.json")
    else:
        cfg_path.write_text(
            json.dumps(mem_cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        written.append(".memory-system.json")

    # 由 CLAUDE.md 生成 AGENTS.md
    sync = TEMPLATE_ROOT / "tools" / "sync_agents_md.py"
    if sync.exists() and not (target / "AGENTS.md").exists():
        subprocess.run([sys.executable, str(sync), "--root", str(target)], check=False)

    print(f"✅ 写入 {len(written)} 个文件")
    if skipped:
        print(f"⏭️  跳过 {len(skipped)} 个已存在文件（加 --force 可覆盖）：{', '.join(skipped[:5])}")

    if unresolved:
        by_hint: dict[str, int] = {}
        for name in unresolved:
            by_hint[hint_for(name)] = by_hint.get(hint_for(name), 0) + 1
        print(f"\n📝 留待会话中补齐的 TODO：{len(unresolved)} 处，共 {len(by_hint)} 类")
        for hint, n in sorted(by_hint.items(), key=lambda kv: -kv[1]):
            print(f"   - {hint}{f'  ×{n}' if n > 1 else ''}")
        print("\n   建议：新开一个 Agent 会话，让它读 CLAUDE.md 后按 BOOT.md 路由表逐项补齐。")

    print(f"""
下一步
  1. cd {target}
  2. 用编辑器或 Agent 会话补齐上面列出的 TODO
  3. python tools/check_conventions.py --root .     # 校验约定
  4. 冷启动验收（★强烈建议）：
     开一个【全新、零上下文】的 Agent 会话，只丢一句——
       「读 CLAUDE.md，按它的 Boot Sequence 走，然后告诉我：这个项目是什么、
         现在什么状态、哪一步断了或需要猜。」
     它说得清 = 系统可用；说不清 = TODO 还没补全。
     要求它必须给批评性意见，否则它只会报喜。
""")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
