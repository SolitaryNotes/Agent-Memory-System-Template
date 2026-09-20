# 模块：hooks（可选会话自启动）

## 这个模块加什么

一个 Claude Code `SessionStart` hook，在每次会话开始时把**极短**的当前状态注入上下文
（BOOT.md 陈旧度、当前阶段、未完成待办数、活跃计划、最近会话）。

它解决的是本系统最大的结构性弱点：**启动序列原本只是文字约定**。
`CLAUDE.md` 里写着「Boot Sequence」，但没有任何东西保证 Agent 真的执行；
不执行的会话就会在缺少上下文的情况下开始工作。

## 默认不安装

用 `--modules` 显式勾选才会落地：

```bash
python tools/init.py --target DIR --modules research,hooks
```

即使落地了，**hook 也不会自动生效**——还需要手工把配置片段合并进 `.claude/settings.json`。
这是刻意的双重确认：写文件不等于改变会话行为。

## 为什么默认关闭（这是本模块最重要的说明）

启用后每次会话都要付固定上下文成本。本实现的注入量约 4–6 行 / 60–100 token。
对长会话可忽略，对「开个会话问一句话」的用法则占比很高。

**判断标准：如果你经常开短会话问零散问题，就别开。**

这也是它在源项目里长期停留在「想到了但没做」的原因——那是个正确的直觉，
只是缺一个明确的取舍判据。本模块把判据写下来了。

## 落地内容

| 文件 | 说明 |
|---|---|
| `hooks/session_start.py` | hook 脚本，stdlib-only，永不抛错 |
| `hooks/README.md` | 在本项目内如何启用 / 验证 / 关闭，含开销核算 |

## 已知限制

- 脚本按 `CLAUDE_PROJECT_DIR` 定位项目根；该环境变量由 Claude Code 注入。
  手动测试时用 `CLAUDE_PROJECT_DIR=. python hooks/session_start.py`。
- 输出上限硬编码为 8 行（`MAX_LINES`）。要调就改脚本，不要靠约定。
- 只注入**指针**（去哪读），不注入**内容**（读到了什么）。这是它便宜的原因，
  也是它不能替代真正 Boot Sequence 的原因——两者是互补的，不是替代关系。
