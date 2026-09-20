# dashboard_template — 云端实验实时仪表盘（参考实现）

> ⚠️ **它带着一个实验形态的烙印。** 本模板是为「**三段 × 三取值**」的矩阵画的
> ——首段分三个 3×3 面板，第二段是行、第三段是列。这是它来自的那个实验的形态，
> **不是通用仪表盘**。换形态需要改两处：`server.py` 的列投影、`index.html` 的分组逻辑。
> 保留它作为**起点**（它解决了实时性、零依赖、原子写这些不因形态而变的问题），
> 但别指望开箱适配任何矩阵。

> 让云端实验"看得见"：宏观进度 + 逐格结果 + 实时日志，零第三方依赖（纯 Python stdlib + 单文件 HTML），适配 AutoDL。
> 完整协同流程见 `cloud/docs/cloud_coordination.md` §6（实时监督与展示）。

## 三个文件

| 文件 | 作用 |
|------|------|
| `progress.py` | **实验脚本调用**，把实时进度写入 `dashboard_state.json` |
| `server.py` | HTTP 服务：`/`（页面）、`/api/state`、`/api/matrix`、`/api/logs`、`/api/loglist` |
| `index.html` | 单文件仪表盘（3s 轮询，浅色清爽设计，零 CDN） |

## 接入实验脚本（让实验"会汇报"）

在 run 脚本的关键节点调用（以你的实验驱动脚本为例）：

```bash
STATE=results/dashboard_state.json

# 开始时
python3 progress.py init "$STATE" --experiment "<实验名>" --total <本次 run 总数>

# 每个格子/重复开始时
python3 progress.py update "$STATE" '{"current":{"code":"<格子>","rep":1,"stage":"<阶段A>"}}'

# 阶段推进（阶段 A→B、epoch 里程碑）—— 低频调用即可，避免每 epoch 开销
python3 progress.py update "$STATE" '{"current":{"code":"<格子>","rep":1,"stage":"<阶段B>","epoch":45}}'

# 每完成一个重复（done_runs 自增由 done 命令做，也可 update 手动写）
python3 progress.py update "$STATE" '{"done_runs":12}'

# 一格 3 次重复全部完成
python3 progress.py done "$STATE" <格子> <指标值> <std> <n>
```

> 阶段名（`<阶段A>` / `<阶段B>`）由你按自己的实验命名，仪表盘只做展示，不校验取值。
> `update` 为**深度合并**（可改 current/done_runs/notes 等任意字段）；`done` 自动累加 `done_runs` 并写入 `results[code]`。state 文件为**原子写**（先写 .tmp 再 rename），仪表盘永远不会读到半截 JSON。
> **指标键名**：state 里存的是通用键 `value`（不是某个指标专名）。你的指标叫 mse / accuracy / loss 都行——
> 改的时候 `progress.py` 的 `done`、`index.html` 的取值、`cloud_coordination.md` §6.4 三处一起改。

## 启动

```bash
# 后台运行（不随 SSH 会话退出）
nohup python3 server.py \
  --root  <实验输出目录> \
  --logs  <日志目录> \
  --matrix <矩阵csv路径> \
  --port  8501 > dashboard.log 2>&1 &
```

- `--root` 必须含 `dashboard_state.json`
- `--logs` 默认 = root；`--matrix` 默认 = `<root>/matrix.csv`（矩阵缺失时热力图显示"未加载"，其余功能正常）

## 用户访问

- **AutoDL 自定义服务**（推荐）：AutoDL 控制台 → 更多 → 自定义服务 → 发布 8501 端口 → 得到公网 URL，浏览器直接打开。
- **SSH 端口转发**：`ssh -p <端口> root@<region>.autodl.com -L 8501:127.0.0.1:8501` → 浏览器打开 `http://localhost:8501`。

## 数据流

```
实验脚本 --progress.py--> dashboard_state.json --server.py /api/state--> index.html(3s轮询)
实验矩阵 CSV     -------------------->  /api/matrix     ----------->
每 run 日志      -------------------->  /api/logs        ----------->
```

格子的静态定义（code/stage/本地是否已跑）来自矩阵 CSV；实时增量（当前格子、done_runs、逐格 mean±std）来自 state 文件；两者在前端合并成热力图。
