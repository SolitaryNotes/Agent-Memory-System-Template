#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""云端实验实时仪表盘服务端（纯 stdlib，零依赖）。

用法:
  python3 server.py --root <实验输出目录> --logs <日志目录> --matrix <矩阵csv> --port 8501

接口:
  /            -> index.html（仪表盘页面）
  /api/state   -> dashboard_state.json（实时进度，实验脚本经 progress.py 写入）
  /api/matrix  -> 实验矩阵（格子的静态定义，来自矩阵 CSV）
  /api/loglist -> 日志文件列表
  /api/logs?name=<文件>&tail=<N> -> 日志尾部
"""
import argparse
import csv
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = '.'
LOGS = '.'
MATRIX = ''


def _tail(path, n):
    try:
        with open(path, 'rb') as f:
            f.seek(0, 2)
            size = f.tell()
            data = b''
            while size > 0 and len(data.split(b'\n')) < n + 1:
                size = max(0, size - 8192)
                f.seek(size)
                data = f.read() + data
        return data.decode('utf-8', errors='replace')
    except Exception as e:
        return '(读取失败: %s)' % e


def _read_state():
    try:
        with open(os.path.join(ROOT, 'dashboard_state.json'), encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def _read_matrix():
    if not MATRIX or not os.path.exists(MATRIX):
        return []
    rows = []
    try:
        with open(MATRIX, encoding='utf-8-sig') as f:
            for r in csv.DictReader(f):
                # 原样透传矩阵 CSV 的全部列（不预设任何项目特有的列名）。
                # ⚠️ 但前端 `index.html` 仍假定矩阵是「三段 × 三取值」的形态：
                # 首段 → 三个 3×3 面板，第二段 → 行，第三段 → 列。
                # 换实验形态时改 index.html 的分组逻辑（`stage1`/`stage2`/`stage3`
                # 这几个列名也要跟着改）——本文件不是通用仪表盘。
                rows.append(dict(r))
    except Exception as e:
        rows = [{'error': str(e)}]
    return rows


def _list_logs():
    try:
        return sorted(f for f in os.listdir(LOGS) if f.endswith('.log'))[-60:]
    except Exception:
        return []


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass  # 不刷访问日志

    def _send(self, code, body, ctype):
        try:
            self.send_response(code)
            self.send_header('Content-Type', ctype + '; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ('/', '/index.html'):
            with open(os.path.join(HERE, 'index.html'), 'rb') as f:
                self._send(200, f.read(), 'text/html')
        elif path == '/api/state':
            self._send(200, json.dumps(_read_state()).encode('utf-8'), 'application/json')
        elif path == '/api/matrix':
            self._send(200, json.dumps(_read_matrix()).encode('utf-8'), 'application/json')
        elif path == '/api/loglist':
            self._send(200, json.dumps(_list_logs()).encode('utf-8'), 'application/json')
        elif path == '/api/logs':
            q = parse_qs(urlparse(self.path).query)
            name = q.get('name', [''])[0]
            tail_n = int((q.get('tail', ['150']) or ['150'])[0])
            if name:
                body = _tail(os.path.join(LOGS, name), tail_n).encode('utf-8')
            else:
                body = ('\n'.join(_list_logs())).encode('utf-8')
            self._send(200, body, 'text/plain')
        else:
            self._send(404, b'not found', 'text/plain')


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description='Cloud experiment live dashboard')
    ap.add_argument('--root', default='.', help='目录（含 dashboard_state.json）')
    ap.add_argument('--logs', default=None, help='日志目录（默认 = root）')
    ap.add_argument('--matrix', default='', help='矩阵 CSV 路径（默认 <root>/matrix.csv）')
    ap.add_argument('--port', type=int, default=8501)
    a = ap.parse_args()
    ROOT = os.path.abspath(a.root)
    LOGS = os.path.abspath(a.logs) if a.logs else ROOT
    MATRIX = a.matrix or os.path.join(ROOT, 'matrix.csv')
    print('Dashboard: http://0.0.0.0:%d/  (root=%s)' % (a.port, ROOT))
    ThreadingHTTPServer(('0.0.0.0', a.port), Handler).serve_forever()
