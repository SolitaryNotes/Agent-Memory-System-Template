#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_integrity.py — 云端返回包完整性核查（stdlib-only，通用）

为什么需要它
------------
云端实例**关机即丢盘**。返回包一旦缺东西，就没有第二次机会。
而"缺东西"最常见的形态是**静默**的：

    - zip 传输损坏（CRC 失败），但 unzip 不报错或只报一行警告；
    - manifest 里列了某个文件，实际没打进去（打包脚本漏了一行）；
    - 某个条件少了一个 rep（跑到一半被 OOM 打断，脚本继续往下跑了）；
    - **云端改过的脚本没回来**（`cloud_scripts/` 缺失）——同类项目发生过一次（**非本项目数据**），
      导致本地无法复现这批数字是怎么跑出来的。

本脚本把这四项变成**一条命令**，退出码非 0 即"先别关云端实例"。

用法
----
    # 最基本：给解压目录
    python verify_integrity.py --root path/to/return_package_20260821_2238

    # 推荐：同时给 zip（额外做 CRC 校验）并指定重复次数
    python verify_integrity.py --root <解压目录> --zip <return_package>.zip --reps 3

    # 输出机器可读结果（供归档 README 引用）
    python verify_integrity.py --root <目录> --json verify_report.json

    # 显式给出阶段名（推荐：这样"某个阶段一路日志都没有"也会被报出来）
    python verify_integrity.py --root <目录> --zip <包>.zip --reps 3 --stages <阶段A>,<阶段B>

    # 看全部选项
    python verify_integrity.py --help

约定（可用参数覆盖）
--------------------
    - 日志文件名：``{stage}_{condition}_rep{N}.log``，例如 ``<阶段>_<条件>_rep2.log``
    - 阶段名：**本模板不预设**。不给 ``--stages`` 时从日志文件名现推；
      显式给出（如 ``--stages 阶段A,阶段B``）才能发现"某个阶段整个没有日志"这种损坏。
    - 返回包强制含：``manifest.json``、``CLOUD_AGENT_NOTE.md``、``cloud_scripts/``

退出码
------
    0 = 全部通过（或仅有警告）
    1 = 有失败项 —— **不要关闭云端实例**，先把缺的东西要回来
    2 = 用法/环境错误（找不到目录、manifest 不存在等）
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
import zipfile

FAIL, WARN, OK = "FAIL", "WARN", "OK"
ICON = {OK: "[ok]  ", WARN: "[warn]", FAIL: "[FAIL]"}


class Report:
    def __init__(self) -> None:
        self.items: list[tuple[str, str, str]] = []

    def add(self, level: str, step: str, msg: str) -> None:
        self.items.append((level, step, msg))
        print("%s %-22s %s" % (ICON[level], step, msg))

    def n(self, level: str) -> int:
        return sum(1 for lv, _, _ in self.items if lv == level)

    def to_dict(self) -> dict:
        return {
            "summary": {
                "fail": self.n(FAIL),
                "warn": self.n(WARN),
                "ok": self.n(OK),
                "total": len(self.items),
            },
            "items": [{"level": lv, "step": st, "message": msg} for lv, st, msg in self.items],
        }


# ------------------------------------------------------------------ helpers


def relpaths(root: str, skip_names: set[str]) -> set[str]:
    """目录下全部文件的相对路径（posix 分隔），跳过指定的顶层文件名。"""
    out: set[str] = set()
    for dirpath, _dirs, files in os.walk(root):
        for fname in files:
            rel = os.path.relpath(os.path.join(dirpath, fname), root).replace(os.sep, "/")
            if rel in skip_names:
                continue
            out.add(rel)
    return out


def manifest_paths(manifest: dict, sections: list[str] | None) -> list[tuple[str, int | None]]:
    """从 manifest 里抽取 (path, size)。容忍多种 manifest 结构。"""
    candidates: list = []
    container = manifest.get("content", manifest)
    if isinstance(container, dict):
        for section, items in container.items():
            if sections and section not in sections:
                continue
            if isinstance(items, list):
                candidates.extend(items)
    elif isinstance(container, list):
        candidates.extend(container)
    for key in ("files", "checkpoints", "cloud_scripts"):
        if not sections and isinstance(manifest.get(key), list):
            candidates.extend(manifest[key])

    out: list[tuple[str, int | None]] = []
    for it in candidates:
        if isinstance(it, str):
            out.append((it, None))
        elif isinstance(it, dict) and it.get("path"):
            size = it.get("size")
            out.append((str(it["path"]), int(size) if isinstance(size, int) else None))
    # 去重（同一路径可能在多个 section 出现）
    seen: dict[str, int | None] = {}
    for path, size in out:
        seen.setdefault(path, size)
    return sorted(seen.items())


def match_lenient(mpath: str, actual: set[str], by_base: dict[str, list[str]]) -> str | None:
    """把 manifest 里的路径匹配到磁盘上的实际路径。

    manifest 的路径前缀常常与解压目录不一致（打包脚本用了不同的 arcname），
    所以依次尝试：精确匹配 → 去掉首段后匹配 → basename 唯一匹配 → 末两段后缀匹配。
    """
    if mpath in actual:
        return mpath
    parts = mpath.split("/")
    for cut in range(1, min(len(parts), 3) + 1):
        cand = "/".join(parts[cut:])
        if cand in actual:
            return cand
    base = parts[-1]
    if len(by_base.get(base, [])) == 1:
        return by_base[base][0]
    if len(parts) >= 2:
        tail = "/".join(parts[-2:])
        for a in actual:
            if a.endswith(tail):
                return a
    return None


# ------------------------------------------------------------------ checks


def check_zip(rpt: Report, zip_path: str) -> None:
    if not os.path.isfile(zip_path):
        rpt.add(FAIL, "zip", "找不到 zip：%s" % zip_path)
        return
    try:
        with zipfile.ZipFile(zip_path) as z:
            bad = z.testzip()
            names = z.namelist()
    except zipfile.BadZipFile as e:
        rpt.add(FAIL, "zip", "不是合法 zip：%s" % e)
        return
    if bad is None:
        rpt.add(OK, "zip CRC", "全部 %d 项完好" % len(names))
    else:
        rpt.add(FAIL, "zip CRC", "损坏项：%s（传输不完整，必须重新下载）" % bad)

    tops = sorted(set(n.split("/")[0] for n in names if n.strip("/")))
    rpt.add(OK if tops else WARN, "zip 顶层目录", "%s" % (tops or "（空包）"))


def check_manifest(rpt: Report, root: str, sections: list[str] | None,
                   skip_names: set[str]) -> set[str]:
    mpath = os.path.join(root, "manifest.json")
    if not os.path.isfile(mpath):
        rpt.add(FAIL, "manifest", "缺少 manifest.json（无法核对内容清单）")
        return set()

    try:
        with open(mpath, encoding="utf-8") as fh:
            manifest = json.load(fh)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        rpt.add(FAIL, "manifest", "无法解析：%s" % e)
        return set()

    listed = manifest_paths(manifest, sections)
    actual = relpaths(root, skip_names)
    by_base: dict[str, list[str]] = {}
    for a in actual:
        by_base.setdefault(a.split("/")[-1], []).append(a)

    missing, size_mismatch = [], []
    for mpath_rel, size in listed:
        hit = match_lenient(mpath_rel, actual, by_base)
        if hit is None:
            missing.append(mpath_rel)
        elif size is not None:
            real = os.path.getsize(os.path.join(root, hit.replace("/", os.sep)))
            if real != size:
                size_mismatch.append("%s（manifest %d / 实际 %d）" % (hit, size, real))

    rpt.add(OK, "manifest 条目", "%d 条（磁盘 %d 个文件）" % (len(listed), len(actual)))
    if missing:
        rpt.add(FAIL, "manifest 缺失", "%d 个文件在 manifest 里但磁盘上没有：%s"
                % (len(missing), ", ".join(missing[:5]) + (" …" if len(missing) > 5 else "")))
    else:
        rpt.add(OK, "manifest 缺失", "无")

    if size_mismatch:
        rpt.add(WARN, "manifest 大小不符", "%d 项：%s" % (len(size_mismatch), "; ".join(size_mismatch[:3])))

    # 磁盘上多出来、manifest 未列的文件：通常无害（脚本/中间产物），但要说清楚
    matched = set()
    for mpath_rel, _ in listed:
        hit = match_lenient(mpath_rel, actual, by_base)
        if hit:
            matched.add(hit)
    extra = sorted(actual - matched)
    if extra:
        rpt.add(WARN, "manifest 未列文件", "%d 个：%s"
                % (len(extra), ", ".join(extra[:5]) + (" …" if len(extra) > 5 else "")))
    else:
        rpt.add(OK, "manifest 未列文件", "无")
    return actual


def check_reps(rpt: Report, root: str, stages: list[str], reps: int) -> None:
    """每个条件的每个阶段都必须有 rep1..repN。少 rep 是最常见的静默损坏。"""
    log_files = glob.glob(os.path.join(root, "**", "*.log"), recursive=True)
    # 阶段名/条件名都不预设字集：中文、数字、连字符都收（例如 ``阶段A_c1_rep2.log``）。
    pat = re.compile(r"^(?P<stage>[^_/\\]+)_(?P<cond>.+)_rep(?P<rep>\d+)\.log$")
    found: dict[tuple[str, str], set[int]] = {}
    for f in log_files:
        m = pat.match(os.path.basename(f))
        if m:
            key = (m.group("stage"), m.group("cond"))
            found.setdefault(key, set()).add(int(m.group("rep")))

    if not found:
        rpt.add(WARN, "重复次数", "没找到形如 {stage}_{cond}_rep{N}.log 的日志；"
                                  "若本项目命名不同，用 --stages / 忽略本项")
        return

    conds = sorted(set(k[1] for k in found))
    if not stages:
        # 不预设任何实验的阶段名：按日志里实际出现过的阶段现推。
        stages = sorted(set(k[0] for k in found))
        rpt.add(WARN, "阶段名", "--stages 未指定，按日志文件名现推：%s"
                "（若担心某个阶段整个没有日志，显式传 --stages）" % "+".join(stages))
    expected = set(range(1, reps + 1))
    incomplete = []
    for stage in stages:
        for cond in conds:
            got = found.get((stage, cond), set())
            if got != expected:
                incomplete.append("%s/%s 实际 reps=%s 期望 1..%d"
                                  % (stage, cond, sorted(got) or "无", reps))

    rpt.add(OK, "条件数", "%d 个条件 × %d 阶段" % (len(conds), len(stages)))
    if incomplete:
        rpt.add(FAIL, "rep 完整性", "%d 处不完整：%s"
                % (len(incomplete), "; ".join(incomplete[:4]) + (" …" if len(incomplete) > 4 else "")))
    else:
        rpt.add(OK, "rep 完整性", "全部条件在 %s 上均有 %d 个 rep" % ("+".join(stages), reps))

    # 未识别的阶段名（多半是写错了）
    other = sorted(set(k[0] for k in found) - set(stages))
    if other:
        rpt.add(WARN, "未知阶段名", "%s（--stages 里没有，确认是否拼写不同）" % ", ".join(other))


def check_checkpoints(rpt: Report, root: str) -> None:
    exts = (".pth", ".pt", ".ckpt", ".safetensors")
    ckpts = []
    for dirpath, _dirs, files in os.walk(root):
        for f in files:
            if f.endswith(exts):
                ckpts.append(os.path.relpath(os.path.join(dirpath, f), root).replace(os.sep, "/"))
    if ckpts:
        rpt.add(OK, "checkpoint", "%d 个权重文件" % len(ckpts))
    else:
        rpt.add(WARN, "checkpoint", "0 个权重文件（若协议要求每格最佳 ckpt，这是缺失项）")


def check_scripts(rpt: Report, root: str, actual: set[str]) -> None:
    """★ 云端修改过的脚本必须回来——同类项目漏过一次（**非本项目数据**）。"""
    dirs = [d for d in glob.glob(os.path.join(root, "**", "cloud_scripts"), recursive=True)
            if os.path.isdir(d)]
    if not dirs:
        rpt.add(FAIL, "cloud_scripts", "返回包里没有 cloud_scripts/ —— 云端实际运行的脚本没回来")
        return
    n = 0
    exts = (".py", ".sh", ".bash", ".json", ".yaml", ".yml", ".txt")
    names = []
    for d in dirs:
        for dirpath, _dirs, files in os.walk(d):
            for f in files:
                if f.endswith(exts):
                    n += 1
                    if len(names) < 6:
                        names.append(f)
    if n == 0:
        rpt.add(FAIL, "cloud_scripts", "目录存在但里面没有脚本文件")
    else:
        rpt.add(OK, "cloud_scripts", "%d 个脚本：%s" % (n, ", ".join(names)))

    note = [a for a in actual if a.endswith("CLOUD_AGENT_NOTE.md")]
    if note:
        rpt.add(OK, "CLOUD_AGENT_NOTE", note[0])
    else:
        rpt.add(FAIL, "CLOUD_AGENT_NOTE", "缺少云端说明文档（GPU/时长/重复次数/单机一致性）")


def check_csv(rpt: Report, root: str) -> None:
    """results.csv 行数应等于条件数 × 重复次数（每 rep 一行）。"""
    csvs = sorted(glob.glob(os.path.join(root, "**", "results.csv"), recursive=True))
    if not csvs:
        rpt.add(WARN, "results.csv", "没找到 results.csv（per-rep 原始值是唯一事实源，确认是否遗漏）")
        return
    for p in csvs:
        rel = os.path.relpath(p, root).replace(os.sep, "/")
        try:
            with open(p, encoding="utf-8") as fh:
                lines = [ln for ln in fh.read().splitlines() if ln.strip()]
        except (OSError, UnicodeDecodeError) as e:
            rpt.add(FAIL, "results.csv", "%s 无法读取：%s" % (rel, e))
            continue
        rpt.add(OK, "results.csv", "%s：%d 行数据（不含表头）" % (rel, max(len(lines) - 1, 0)))


# ------------------------------------------------------------------ main


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="云端返回包完整性核查（zip CRC / manifest 对照 / rep 完整性 / checkpoint / cloud_scripts）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="退出码：0=通过，1=有失败项（先别关云端实例），2=用法错误",
    )
    ap.add_argument("--root", required=True, help="返回包解压目录")
    ap.add_argument("--zip", default=None, help="返回包 zip（给了就额外做 CRC 校验）")
    ap.add_argument("--manifest", default=None, help="manifest 路径（默认 <root>/manifest.json）")
    ap.add_argument("--reps", type=int, default=3, help="每条件期望的重复次数（默认 3）")
    ap.add_argument("--stages", default=None,
                    help="阶段名，逗号分隔；缺省 = 从日志文件名现推（本模板不预设任何实验的阶段名）")
    ap.add_argument("--sections", default=None, help="只核对 manifest 里这些 section，逗号分隔")
    ap.add_argument("--expect-scripts", action="store_true", default=True,
                    help="要求 cloud_scripts/ 非空（默认开启）")
    ap.add_argument("--no-expect-scripts", dest="expect_scripts", action="store_false",
                    help="本次不要求 cloud_scripts/")
    ap.add_argument("--json", default=None, help="把报告写成 JSON 到该路径")
    args = ap.parse_args(argv)

    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        print("错误：--root 不是目录：%s" % root, file=sys.stderr)
        return 2

    stages = [s.strip() for s in args.stages.split(",") if s.strip()] if args.stages else []
    sections = [s.strip() for s in args.sections.split(",")] if args.sections else None

    # manifest.json 无法把自己列进自己；verify_integrity.py 是本地核查产物，都不算包内容
    skip = {"verify_integrity.py", "manifest.json", "verify_report.json"}
    if args.manifest and os.path.dirname(os.path.abspath(args.manifest)) != root:
        skip.add(os.path.basename(args.manifest))

    rpt = Report()
    print("\n返回包完整性核查 — %s\n%s" % (root, "-" * 64))

    if args.zip:
        check_zip(rpt, os.path.abspath(args.zip))
    else:
        rpt.add(WARN, "zip CRC", "未提供 --zip，跳过 CRC 校验（强烈建议补上）")

    actual = check_manifest(rpt, root, sections, skip)
    if args.expect_scripts:
        check_scripts(rpt, root, actual)
    check_reps(rpt, root, stages, args.reps)
    check_checkpoints(rpt, root)
    check_csv(rpt, root)

    print("-" * 64)
    n_fail, n_warn = rpt.n(FAIL), rpt.n(WARN)
    print("结论：%d 项失败 · %d 项警告 · %d 项检查" % (n_fail, n_warn, len(rpt.items)))
    if n_fail:
        print("\n>>> 不要关闭云端实例。把上面的失败项发给云端 Agent 补发一个补发包。")
    elif n_warn:
        print("\n>>> 通过（有警告）。可关闭云端实例；警告项请写进归档 README。")
    else:
        print("\n>>> 全部通过。可关闭云端实例并归档。")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(rpt.to_dict(), fh, ensure_ascii=False, indent=2)
        print("报告已写入 %s" % args.json)

    return 1 if n_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
