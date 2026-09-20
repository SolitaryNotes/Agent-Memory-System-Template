# Agent Memory System — Template

> **English entry point.** The full documentation is in Chinese:
> [`README.md`](README.md). Read this page to evaluate and try the template;
> see [Language](#language) below for what to expect.

A reusable **memory system for coding agents**. A fresh agent session opens in your
project and already knows what the project is, where it stands, and which file to
touch — **without you restating the context.**

---

## What it actually is

A directory layout plus three small scripts. No service, no database, no dependencies
(Python standard library only).

The design rests on three ideas:

1. **Progressive disclosure.** Only one short file (`CLAUDE.md`) is loaded every session.
   Everything else is read on demand, in layers: a state snapshot → a full manual →
   history. The question that decides where something goes is *"does every session need
   to know this?"*
2. **One source of truth, checked by machine.** `AGENTS.md` is *generated* from
   `CLAUDE.md`, never hand-written. Conventions that can be checked by script
   (naming, plan lifecycle, broken paths) are checked by script, not by memory.
3. **Never let a template slot assert something it can't back up.** A `[x]` next to an
   empty item, or a required field with no value available, silently pushes an agent to
   *invent* an answer. Every such slot says what to write instead.

## Who it is for

People who run long-lived projects with an AI coding agent and are tired of
re-explaining context every session. Especially suited to research codebases
(experiments, results, papers), but the core is domain-agnostic.

## Quick start

```bash
python tools/init.py --target /path/to/new-project     # interactive
python tools/init.py --target DIR --yes --modules research,cloud
python tools/init.py --target DIR --dry-run            # see what would be written
```

`init.py` fills in what it can and leaves everything else as explicit `[TODO: ...]`
markers, then prints the list. Open a fresh agent session **inside the target project**
and let it fill them in — that is the intended split, not a shortcoming.

The reason is worth stating: `init.py` is mechanical (it needs no knowledge of the
project it is landing in), while the routing table and invariants it leaves blank can
only be written by something that has read the project. An agent filling them from the
outside would be inventing them, and a plausible invention is worse than an honest blank.

`init.py` skips existing files by default and only overwrites with `--force`, so it will
not clobber anything already in the target.

Afterwards:

```bash
python tools/check_conventions.py            # runs 10 checks
python tools/check_conventions.py --list     # what it checks
```

## What you get

- **`core/`** (always installed) — the kernel, the layered memory files, and the
  conventions that govern them
- **Five optional modules** — `research` (experiment conventions + run provenance),
  `cloud` (remote GPU experiment pipeline), `reproduction` (paper replication),
  `meetings` (paper notes, group meetings), `hooks` (optional session auto-start)
- **Three tools** — `init.py`, `check_conventions.py`, `sync_agents_md.py`
- **Two design documents** — `docs/design.md` (rationale and context-budget accounting),
  `docs/mechanism.md` (how each mechanism works, and the cold-start validation log)

## Language

**The documentation is Chinese. The tools' output is also Chinese.**

An English speaker can read this page, run the commands, and let their agent do the
work — LLM agents read Chinese without difficulty, and the generated files are mostly
`[TODO: ...]` placeholders for you and your agent to fill in.

What you *will* find opaque is the tools' own console output (prompts, reports,
error messages). There is no `--lang en` flag today. This is a known limitation,
stated here rather than discovered by you after running something.

## Status

Built and validated through repeated cold-start testing (an agent with zero context
is dropped in and must navigate using only the generated files), but **not yet
piloted on a real project.** Treat it as promising and usable, not battle-tested.

## Related

- [`README.md`](README.md) — full documentation (Chinese)
- [`docs/design.md`](docs/design.md) — why it is built this way
- [`docs/mechanism.md`](docs/mechanism.md) — how each mechanism works
