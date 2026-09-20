#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""进度写入器：实验脚本在关键节点调用，把实时进度写进 dashboard_state.json。
纯 stdlib，零依赖。云端 Agent 按此接口让实验"会汇报"。

用法:
  python3 progress.py init   <statefile> --experiment NAME --total N
  python3 progress.py update <statefile> '{"current":{...},"done_runs":N,"notes":[...]}'
  python3 progress.py done   <statefile> CODE VALUE [STD [N]]

- init   : 创建初始状态文件（experiment / total_runs / started_ts）
- update : 深度合并一个 JSON patch（可改 current / done_runs / results / notes 等）
- done   : 标记一格完成（累加 done_runs += N，写入 results[code]）

**指标键名**：状态文件里指标值存在**通用键 `value`** 下（VALUE 就是你这一步测出来的数，
mse / accuracy / loss 都可以）。它不是某个指标的专名——若你想直接以指标名为键，
改 `METRIC_KEY` 一行，并同步改 `index.html` 的取值处与 `cloud_coordination.md` §6.4。

dashboard_state.json 的结构与约定见 cloud/docs/cloud_coordination.md §6.4。
"""
import json
import os
import sys
import time

# 状态文件里指标值用的键名。改这里时，index.html 的取值处与
# cloud_coordination.md §6.4 要一起改（三处必须一致）。
METRIC_KEY = 'value'


def load(path):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def save(path, state):
    state['updated_at'] = time.strftime('%Y-%m-%d %H:%M:%S')
    state['elapsed_sec'] = int(time.time() - state.get('started_ts', time.time()))
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)   # 原子写，避免仪表盘读到半截 JSON


def merge(base, patch):
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            merge(base[k], v)
        else:
            base[k] = v


def main():
    if len(sys.argv) < 3:
        sys.exit('用法: progress.py {init|update|done} <statefile> [...]')
    cmd, state = sys.argv[1], sys.argv[2]
    s = load(state)

    if cmd == 'init':
        exp, total = '', 0
        rest = sys.argv[3:]
        i = 0
        while i < len(rest):
            if rest[i] == '--experiment' and i + 1 < len(rest):
                exp = rest[i + 1]
                i += 2
            elif rest[i] == '--total' and i + 1 < len(rest):
                total = int(rest[i + 1])
                i += 2
            else:
                i += 1
        s = {'experiment': exp, 'total_runs': total, 'done_runs': 0,
             'started_ts': int(time.time()), 'current': {}, 'results': {}, 'notes': []}
    elif cmd == 'update':
        if len(sys.argv) < 4:
            sys.exit('update 需要 JSON patch 参数')
        merge(s, json.loads(sys.argv[3]))
    elif cmd == 'done':
        if len(sys.argv) < 5:
            sys.exit('done 需要 CODE 和 VALUE 参数')
        code, value = sys.argv[3], float(sys.argv[4])
        std = float(sys.argv[5]) if len(sys.argv) > 5 else 0.0
        n = int(sys.argv[6]) if len(sys.argv) > 6 else 1
        s.setdefault('results', {})[code] = {METRIC_KEY: value, 'std': std, 'n': n}
        s['done_runs'] = s.get('done_runs', 0) + n
        s['current'] = {}
        s.setdefault('notes', []).append('%s done: %.4f ± %.4f' % (code, value, std))
        s['notes'] = s['notes'][-30:]
    else:
        sys.exit('未知命令: %s' % cmd)

    save(state, s)


if __name__ == '__main__':
    main()
