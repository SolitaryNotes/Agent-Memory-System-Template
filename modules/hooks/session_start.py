#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""session_start.py — SessionStart hook：把「启动序列」从文字约定变成机制

本脚本由 Claude Code 在会话开始时调用，stdout 的内容会作为上下文注入。

**它的输出必须极短。** 每次会话都要付这份上下文成本，所以只注入
「不看就会做错事」的那几条，其余交给 Agent 按 Boot Sequence 自己去读。
默认只输出 6 行以内；任何一层读不到就静默跳过，绝不报错、绝不阻塞会话。
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import date, datetime
from pathlib import Path

# Windows 控制台默认 GBK；hook 输出必须干净，不能因为编码问题变成乱码注入上下文
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except Exception:
        pass

MAX_LINES = 8

# 脚手架态的标记语：初始化脚本写入 BOOT.md / current_state.md 时带这一句。
# 此时「更新于 0 天前」虽然为真，却毫无意义——项目还没有过任何一次会话，
# 报成「新鲜」会把一个从未维护过的状态文件伪装成维护中的状态。
SCAFFOLD_MARK = "脚手架初始化"


def read(path: Path, limit: int = 4000) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:limit]
    except OSError:
        return ""


def main() -> int:
    root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path.cwd())
    mem = root / "agent_memory"
    out: list[str] = []

    boot = read(mem / "BOOT.md", 3000)
    if boot:
        m = re.search(r"\*\*Updated\*\*\s*[:：]\s*(\d{4}-\d{2}-\d{2})", boot)
        if m and SCAFFOLD_MARK in boot:
            # 脚手架态：报天数会误导（0 天前 = 看起来很新），所以明确报「还没开始」
            out.append(f"[记忆] BOOT.md 仍是脚手架状态（尚无真实会话），日期 {m.group(1)} 不代表项目进度")
        elif m:
            try:
                days = (date.today() - datetime.strptime(m.group(1), "%Y-%m-%d").date()).days
                flag = f"，已 {days} 天未更新 ⚠️" if days > 30 else ""
                out.append(f"[记忆] BOOT.md 更新于 {m.group(1)}{flag}")
            except ValueError:
                pass
        m = re.search(r"\*\*Stage\*\*\s*[:：]\s*([^|\n]+)", boot)
        if m:
            out.append(f"[记忆] 当前阶段：{m.group(1).strip()}")

    state = read(mem / "current_state.md", 20000)
    if state:
        # 只数真实待办。两条排除规则都必要：
        #   ① `[TODO: ...]` 是占位符，不是活儿；
        #   ② 必须锚定行首——文档里会**描述** `- [ ]` 这个语法本身，
        #      用 `in` 判断会把说明文字也数进去。
        active = sum(
            1
            for ln in state.splitlines()
            if re.match(r"\s*- \[ \]", ln) and "[TODO" not in ln
        )
        if active:
            out.append(f"[记忆] 待办树中有 {active} 项未完成 → current_state.md §7")

    plans = mem / "plans"
    if plans.is_dir():
        for p in sorted(plans.glob("*.md")):
            if p.name.startswith("_"):
                continue
            head = read(p, 600)
            if re.search(r"^status:\s*active", head, re.M):
                out.append(f"[记忆] 活跃计划：plans/{p.name}")
                break

    logs = mem / "session_logs"
    if logs.is_dir():
        found = sorted((p for p in logs.glob("session_*.md")), reverse=True)
        if found:
            out.append(f"[记忆] 最近会话：session_logs/{found[0].name}")

    if out:
        out.append("[记忆] 完整启动序列见 CLAUDE.md 的 Boot Sequence 一节")

    print("\n".join(out[:MAX_LINES]))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        # hook 绝不能因为自身出错而阻塞用户的会话
        sys.exit(0)
