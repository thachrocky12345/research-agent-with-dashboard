# /init Skill — Project Sync & ADR Management

## Purpose
Synchronizes AI context with the current state of the codebase. Run `/init` after pulling changes, adding dependencies, or modifying architecture.

## When This Skill Runs
- User invokes `/init`
- On session start (auto-loaded)

---

## Step 1: Scan Project Structure

Scan the entire project directory tree. Identify:
- All source directories (src/, dashboard/src/, commands/, templates/, examples/)
- Configuration files (pyproject.toml, package.json, tsconfig.json, etc.)
- Documentation (docs/, README.md, CLAUDE.md)
- Test directories if present

---

## Step 2: Update CLAUDE.md

Update these sections in CLAUDE.md (preserve all other content):

### Tech Stack
Detect from pyproject.toml, package.json, and configuration files:
- Python version and dependencies
- Node.js/npm dependencies (from dashboard/package.json)
- Frameworks (Next.js, React, etc.)
- Build tools (hatchling, npm, etc.)

### Project Structure
Generate a clean directory tree showing:
- Top-level directories and their purpose
- Key files in each directory
- Exclude: .git, __pycache__, node_modules, .venv, *.pyc, .next

### Key Modules
Identify and describe:
- Main entry points
- Core business logic modules
- API routes
- Shared utilities

### Known Dependencies
Extract from pyproject.toml and dashboard/package.json:
```
Last synced: [current date]

Python (pyproject.toml):
- [list dependencies]

Node.js (dashboard/package.json):
- [list dependencies]
```

---

## Step 3: Update docs/architecture.md

Update the following sections:

### Last Updated
Set to current date/time

### Tech Stack
Mirror from CLAUDE.md

### System Layers
Describe the architectural layers:
- Commands layer (/ark:* skills)
- Dashboard layer (Next.js app)
- Templates layer (experiment scaffolding)
- Examples layer (reference implementations)

### Key Modules
List modules with their responsibilities

### Recent Decisions
Link to any ADRs in docs/decisions/

---

## Step 4: Update docs/deployment.md

Update the following sections:

### Last Updated
Set to current date/time

### Environment Variables
Verify and update the environment variables table:
- Check for any new required environment variables in the codebase
- Update descriptions if behavior has changed

### Deployment Checklist
Update requirements based on current dependencies:
- Node.js version requirements (check package.json engines if present)
- Python version requirements (check pyproject.toml)
- Any new build steps or prerequisites

### Components
Update component sections if new deployable components were added:
- New services or microservices
- New CLI tools or scripts
- New background workers

### Troubleshooting
Add new troubleshooting entries for:
- Common errors discovered during development
- New configuration requirements

---

## Step 5: Process Pending ADR Review

Check if `docs/decisions/.pending_adr_review` exists. If it does:

### CREATE new ADRs for:
- New major frameworks added (e.g., new ORM, auth library, database driver)
- New infrastructure dependencies (e.g., Docker, Redis, message queues)
- Significant architectural additions

### DEPRECATE ADRs when:
- A library has been completely removed from dependencies
- A pattern or tool is no longer in use

### UPDATE ADR status when:
- One decision supersedes another
- A proposed ADR should be marked as accepted

### SKIP (do not create ADRs for):
- Minor version bumps (e.g., react 19.2.2 -> 19.2.3)
- Dev/test-only dependencies (pytest, black, ruff, mypy, eslint, prettier)
- Type definition packages (@types/*)

### ADR Creation Process:
1. Copy from `docs/decisions/_template.md`
2. Use next available ADR number (check index.md)
3. Fill in all sections with context from the project
4. Add to `docs/decisions/index.md`

After processing, **DELETE** `docs/decisions/.pending_adr_review`

---

## Step 6: Update ADR Index

Update `docs/decisions/index.md`:
- Add any new ADRs
- Update status of modified ADRs
- Sort by ADR number

---

## Step 7: Update Known Dependencies Baseline

After all updates, ensure CLAUDE.md's Known Dependencies section reflects the current state.

---

## Step 8: Output Summary

Print a summary in this exact format:

```
✅ Init sync complete — updated: [list of files modified], created ADRs: [list or "none"], skipped: [reasons or "n/a"]
```

Examples:
- `✅ Init sync complete — updated: CLAUDE.md, docs/architecture.md, docs/deployment.md, created ADRs: ADR-0003-recharts-visualization, skipped: n/a`
- `✅ Init sync complete — updated: CLAUDE.md, docs/deployment.md, created ADRs: none, skipped: no dependency changes detected`

---

## Important Notes

- **ALWAYS** run all steps even if nothing appears to have changed
- **NEVER** skip the summary output
- **PRESERVE** existing content in CLAUDE.md that is not in the sections being updated
- **USE** the current date (not a placeholder) for timestamps
