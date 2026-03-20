# Architecture Overview

Last Updated: 2026-03-20 12:48:38

## Overview

AutoResearch Kit (ARK) is a companion toolkit for Karpathy's autoresearch project. It provides an interactive onboarding experience (`/ark:new`) that designs experiments through AI conversation, and a real-time Next.js dashboard for visualizing experiment progress.

## Tech Stack

### Python
- Python >= 3.10
- hatchling (build system)
- No runtime dependencies

### Node.js / Dashboard
- Next.js 16.1.6
- React 19.2.3
- Recharts 3.8.0 (data visualization)
- Tailwind CSS 4.x (styling)
- TypeScript 5.x (strict mode)

## System Layers

```
┌─────────────────────────────────────────────────────────────┐
│                      Commands Layer                          │
│  /ark:new  /ark:go  /ark:run  /ark:dashboard  /ark:report   │
│  (Claude Code skills — conversation-driven experiment setup) │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                     Dashboard Layer                          │
│  Next.js app with API routes reading experiment files        │
│  - page.tsx: KPIs, charts, tables, event log                │
│  - route.ts: Loads kit.json + TSV + events.log              │
│  - data.ts: File readers with type coercion                 │
│  - types.ts: TypeScript interfaces                          │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                     Templates Layer                          │
│  Universal templates for experiment scaffolding              │
│  - program.md: Agent protocol (domain-specific)             │
│  - laws.md: Immutable experiment rules                      │
│  - agent-context.md: CLAUDE.md/AGENTS.md template           │
│  - journal.md: Knowledge base structure                     │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                  Validation Layer                            │
│  kit_schema.py: kit.json validation and helpers             │
│  - Schema validation (required fields, metric patterns)     │
│  - Phase management (get_current_phase, get_active_metric)  │
│  - Floor aggregation (get_all_floors)                       │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                     Examples Layer                           │
│  Reference implementations (config only, not runnable)       │
│  - ml-pretraining: Simple metric (minimize val_bpb)         │
│  - trading-strategy: Floors (Sharpe + max_drawdown)         │
│  - sequential-metrics: Phased (convergence → optimization)  │
└─────────────────────────────────────────────────────────────┘
```

## Key Modules

### Commands (`commands/ark/`)
| Command | Purpose |
|---------|---------|
| `new.md` | Expert-driven experiment design conversation |
| `go.md` | Launch dashboard + start experiment loop |
| `run.md` | Autonomous experiment loop (no dashboard) |
| `dashboard.md` | Dashboard only (no experiments) |
| `report.md` | Plain-language progress report |
| `help.md` | Command reference |

### Dashboard (`dashboard/src/`)
| File | Responsibility |
|------|----------------|
| `app/page.tsx` | Main UI — status, KPIs, charts, tables, event log |
| `app/api/data/route.ts` | API endpoint, calls loadAll() |
| `lib/data.ts` | File readers: TSV, events.log, kit.json |
| `lib/types.ts` | TypeScript interfaces for kit.json, experiments, events |

### Templates (`templates/`)
| Template | Purpose |
|----------|---------|
| `program.md` | Agent protocol with `{placeholder}` syntax |
| `laws.md` | Immutable experiment rules (NEVER STOP, logging) |
| `agent-context.md` | CLAUDE.md/AGENTS.md generation |
| `journal.md` | Knowledge base structure |
| `events.log` | Event format specification |

### Validation (`kit_schema.py`)
| Function | Purpose |
|----------|---------|
| `load(path)` | Load and validate kit.json |
| `save(kit, path)` | Validate and save kit.json |
| `validate(kit)` | Schema validation with detailed errors |
| `get_current_phase()` | Determine active phase from events |
| `get_active_metric()` | Get current metric name + direction |
| `get_all_floors()` | Merge top-level and phase-specific floors |

## Data Contract: kit.json

The bridge between `/ark:new` (writer) and dashboard (reader):

```
kit.json
├── version: 1
├── name, description, created_at
├── metric
│   ├── primary: string
│   ├── direction: "lower" | "higher"
│   ├── explanation: string (plain-language)
│   ├── floors: { [name]: { value, direction } }
│   ├── phases: Phase[] | null
│   └── composite_formula: string | null
├── eval_command, parse_command
├── mutable_files[], immutable_files[]
├── columns[], status_values[]
├── time_budget_minutes, timeout_minutes
└── context, goals, data_description
```

## Recent Decisions

- See [docs/decisions/index.md](decisions/index.md) for Architecture Decision Records

## Open Questions

- [ ] Should we add authentication for multi-user dashboard scenarios?
- [ ] How should we handle experiment versioning/branching?
- [ ] Should templates be customizable per-domain?
