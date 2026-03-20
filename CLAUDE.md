# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 🔁 Init Behavior (ALWAYS FOLLOW)

Whenever `/init` is run:
1. Read `.claude/skills/init/SKILL.md` and follow it completely
2. Update CLAUDE.md — refresh structure, stack, modules, known dependencies
3. Update `docs/architecture.md` — timestamp, new layers, new dependencies
4. Update `docs/deployment.md` — timestamp, environment variables, deployment checklist
5. Check and process `docs/decisions/.pending_adr_review`
6. Update `docs/decisions/index.md`
7. Confirm with: "✅ Init sync complete — updated: [files]"

**DO NOT skip these steps even if nothing seems changed.**

---

## Commands

### Dashboard Development
```bash
cd dashboard && npm install    # Install dependencies
cd dashboard && npm run dev    # Start dev server (set EXP_DIR first)
cd dashboard && npm run build  # Production build
```

The dashboard requires `EXP_DIR` environment variable pointing to an experiment directory containing `kit.json`.

### Project Automation
```bash
make init       # Run post_init hook + prompt for /init
make dashboard  # Start dashboard (alias: make dev)
make install    # Install dashboard npm dependencies
make build      # Build dashboard for production
```

### Installing ARK Skills
```bash
./install.sh    # Installs /ark:* commands to ~/.claude/commands/ark/
```

---

## Architecture

ARK is a companion to Karpathy's [autoresearch](https://github.com/karpathy/autoresearch) that provides:
1. **Onboarding** — `/ark:new` designs experiments via AI conversation
2. **Dashboard** — Next.js app for real-time experiment visualization

### Data Flow

```
/ark:new (conversation)
    │
    ├── reads: templates/*
    │
    └── writes: experiment_dir/
          ├── kit.json          ← Config contract (dashboard reads this)
          ├── program.md        ← Domain-specific agent protocol
          ├── laws.md           ← Immutable experiment rules
          ├── journal.md        ← Knowledge base (agent writes findings)
          ├── results.tsv       ← Experiment history (append-only)
          └── events.log        ← System events

dashboard/
    │
    └── reads: kit.json + results.tsv + events.log via API route
              └── renders: KPIs, charts, experiment table, event log
```

### kit.json Contract

The bridge between onboarding and dashboard. Three metric patterns:

| Pattern | Use Case | Structure |
|---------|----------|-----------|
| **Simple** | Single metric + optional floors | `metric.primary` + `metric.direction` + `metric.floors` |
| **Sequential** | Ordered phases with gates | `metric.phases[]` with gate conditions |
| **Composite** | Formula combining metrics | `metric.composite_formula` |

Validation logic in `kit_schema.py` — use `kit_schema.load(path)` to validate.

### Dashboard Components

The dashboard (`dashboard/src/app/page.tsx`) renders:
- **Status indicator** — Live/Idle based on `results.tsv` modification time
- **Phase banner** — Current phase + gate progress (sequential experiments)
- **KPI cards** — Best metric, baseline, improvement %, keep rate
- **Progress chart** — Scatter + running best line, floor reference lines
- **Floor gauges** — Constraint status with pass/fail indicators
- **Experiment table** — Filterable, searchable, highlights best values
- **Event log** — Collapsible event history
- **Diminishing returns** — Warns when improvement slows

Data loading (`dashboard/src/lib/data.ts`):
- `resolveExpDir()` — Finds experiment via `EXP_DIR` env var or auto-discovery
- `readKit()` — Parses kit.json
- `readExperiments()` — Parses TSV with type coercion
- `readEvents()` — Parses multiple event log formats
- `isResearchActive()` — Checks if results.tsv was modified in last 5 minutes

---

## Key Modules

### Commands (`commands/ark/`)
Skill definitions that define the `/ark:*` slash commands:
- `new.md` — Expert-driven experiment design conversation
- `go.md` — Launch dashboard + start experiment loop
- `run.md` — Autonomous experiment loop only
- `dashboard.md` — Dashboard only
- `report.md` — Plain-language progress report

### Templates (`templates/`)
Scaffolding templates with `{placeholder}` syntax:
- `program.md` — Agent protocol (domain config, mutable/immutable rules)
- `laws.md` — Immutable experiment laws (NEVER STOP, logging, crash handling)
- `agent-context.md` — Generates CLAUDE.md and AGENTS.md for experiments
- `journal.md` — Knowledge base structure

### Validation (`kit_schema.py`)
Python module for kit.json validation:
- `load(path)` — Load and validate
- `save(kit, path)` — Validate and save
- `get_current_phase(kit, events_log_path)` — Determine active phase
- `get_active_metric(kit, events_log_path)` — Get current metric + direction
- `get_all_floors(kit, events_log_path)` — Merge top-level and phase floors

---

## Known Dependencies

<!-- Claude auto-updates this section on every /init — do not edit manually -->

Last synced: 2026-03-20

### Python (pyproject.toml)
- Python >= 3.10
- hatchling (build system)
- No runtime dependencies

### Node.js (dashboard/package.json)
**Dependencies:**
- next: 16.1.6
- react: 19.2.3
- react-dom: 19.2.3
- recharts: ^3.8.0

**Dev Dependencies:**
- @tailwindcss/postcss: ^4
- tailwindcss: ^4
- typescript: ^5

---

## Conventions

- **Type hints:** Required in Python
- **Docstrings:** Google style
- **TypeScript:** Strict mode enabled
- **Formatter:** black (Python), prettier (TypeScript)
- **Template syntax:** `{placeholder}` for simple substitution
