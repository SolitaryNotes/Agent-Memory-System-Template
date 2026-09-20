#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sync_agents_md.py — 由 CLAUDE.md 生成 AGENTS.md（单一事实源）

背景
----
很多项目同时维护 CLAUDE.md 和 AGENTS.md（后者供 Codex / Cursor 等读取）。
两份文件手工双写，必然漂移——实测某项目的两份文件在「当前阶段」「最近会话」
「快速开始命令」三处互相矛盾，而没有任何机制会发现。

本脚本让 CLAUDE.md 成为**唯一事实源**：AGENTS.md 是生成物，不手工编辑。

用法
----
    python tools/sync_agents_md.py            # 生成 / 更新 AGENTS.md
    python tools/sync_agents_md.py --check     # 只检查是否同步（CI 用）；不同步则退出码 1
    python tools/sync_agents_md.py --root DIR  # 指定项目根（默认：脚本上一级）

平台专属内容如何排除
--------------------
在 CLAUDE.md 中用成对标记包住只对 Claude Code 有意义的段落：

    <!-- @agents:skip -->
    ## Claude Code 专属
    ...
    <!-- @agents:endskip -->

标记对之间的内容不会进入 AGENTS.md。标记本身也不输出。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Windows 控制台默认 GBK，中文输出会直接抛 UnicodeEncodeError
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except Exception:
        pass

SKIP_BEGIN = "<!-- @agents:skip -->"
SKIP_END = "<!-- @agents:endskip -->"
GENERATED_BANNER = (
    "<!-- 本文件由 tools/sync_agents_md.py 从 CLAUDE.md 自动生成，请勿手工编辑。 -->\n"
    "<!-- 修改请改 CLAUDE.md，然后运行：python tools/sync_agents_md.py -->\n"
)


def strip_platform_blocks(text: str) -> str:
    """删除 @agents:skip 与 @agents:endskip 之间的全部内容（含标记本身）。"""
    out, depth = [], 0
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == SKIP_BEGIN:
            depth += 1
            continue
        if stripped == SKIP_END:
            depth = max(0, depth - 1)
            continue
        if depth == 0:
            out.append(line)
    return "\n".join(out)


def collapse_blank_lines(text: str) -> str:
    """把 3 个以上连续空行压成 1 个，避免删块后留下大洞。"""
    return re.sub(r"\n{3,}", "\n\n", text)


def render_agents_md(claude_text: str) -> str:
    body = collapse_blank_lines(strip_platform_blocks(claude_text)).strip()
    return f"{GENERATED_BANNER}\n{body}\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="由 CLAUDE.md 生成 AGENTS.md")
    ap.add_argument("--root", default=None, help="项目根目录（默认：本脚本的上一级）")
    ap.add_argument("--check", action="store_true", help="只检查是否同步，不写文件")
    args = ap.parse_args()

    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parent.parent
    claude = root / "CLAUDE.md"
    agents = root / "AGENTS.md"

    if not claude.exists():
        print(f"❌ 找不到 {claude}", file=sys.stderr)
        return 2

    expected = render_agents_md(claude.read_text(encoding="utf-8"))

    if args.check:
        if not agents.exists():
            print("❌ AGENTS.md 不存在（应运行 sync_agents_md.py 生成）")
            return 1
        actual = agents.read_text(encoding="utf-8")
        if actual != expected:
            print("❌ AGENTS.md 与 CLAUDE.md 不同步。运行: python tools/sync_agents_md.py")
            return 1
        print("✅ AGENTS.md 与 CLAUDE.md 同步")
        return 0

    if agents.exists() and agents.read_text(encoding="utf-8") == expected:
        print("✅ AGENTS.md 已是最新，无需改动")
        return 0

    agents.write_text(expected, encoding="utf-8")
    print(f"✅ 已生成 {agents.relative_to(root)}  ({len(expected.splitlines())} 行)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
