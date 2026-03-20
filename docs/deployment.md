# Deployment Guide

Last Updated: 2026-03-20 12:50:00

## Overview

AutoResearch Kit has two deployment targets:
1. **ARK Skills** — `/ark:*` commands installed to user's Claude Code
2. **Dashboard** — Next.js app for experiment visualization

## Requirements

- Node.js >= 18 (for dashboard)
- Python >= 3.10 (for kit_schema.py validation)
- An AI coding agent: Claude Code, Gemini CLI, Codex CLI, or GitHub Copilot

No GPU required. No API keys required.

## Components

### ARK Skills Installation

Install globally via:
```bash
curl -fsSL https://raw.githubusercontent.com/leagueofdrazn/ark/main/install.sh | sh
```

Or run locally:
```bash
./install.sh
```

This copies skill files to `~/.claude/commands/ark/` (and equivalent locations for other agents).

Verify installation:
```
/ark:help
```

### Dashboard

#### Development
```bash
cd dashboard
npm install
EXP_DIR=/path/to/experiment npm run dev
```

#### Production Build
```bash
cd dashboard
npm run build
npm start
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `EXP_DIR` | Yes | Path to experiment directory containing kit.json |
| `PORT` | No | Port for dashboard server (default: 3000) |

## Deployment Checklist

- [ ] Node.js >= 18 installed (`node --version`)
- [ ] Python >= 3.10 installed (`python3 --version`)
- [ ] Dashboard dependencies installed (`cd dashboard && npm install`)
- [ ] `EXP_DIR` environment variable set
- [ ] Experiment directory contains valid `kit.json`
- [ ] Production build completed (`npm run build`)
- [ ] Reverse proxy configured (if needed)

## Hosting Options

### Local Development
```bash
EXP_DIR=/path/to/experiment npm run dev
```
Hot-reloading enabled at http://localhost:3000

### Self-Hosted Production
```bash
cd dashboard
npm run build
EXP_DIR=/path/to/experiment npm start
```

Configure reverse proxy (nginx, caddy) to forward traffic to port 3000.

### Docker (Future)
Docker support is planned but not yet implemented.

## Recommended: Skip Permissions Mode

ARK is designed for autonomous overnight experiments:
```bash
# Claude Code
claude --dangerously-skip-permissions

# Gemini
gemini --yolo

# Codex
codex --full-auto
```

## Troubleshooting

### Dashboard shows "No data" or "No experiment"
- Verify `EXP_DIR` environment variable is set
- Check that `kit.json` exists in the experiment directory
- Validate kit.json: `python3 -c "import kit_schema; kit_schema.load('path/to/kit.json')"`

### Dashboard shows "Loading..." indefinitely
- Check browser console for API errors
- Verify experiment directory is readable
- Check that `results.tsv` exists (can be header-only)

### Skills not found after install
- Run `./install.sh` again
- Verify `~/.claude/commands/ark/` contains `.md` files
- Restart your AI agent session

### "Live" indicator stays off
- Dashboard checks if `results.tsv` was modified in last 5 minutes
- Run an experiment or touch the file: `touch results.tsv`

## Related

- [Architecture](./architecture.md)
- [Runbooks](./runbooks/)
- [ADR Index](./decisions/index.md)
