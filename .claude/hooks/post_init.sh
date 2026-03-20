#!/bin/bash
# post_init.sh — Runs after /init to prepare dependency diffs and update docs
# This script is called by the Makefile or can be run standalone

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Ensure docs directories exist
mkdir -p "$PROJECT_ROOT/docs/decisions"
mkdir -p "$PROJECT_ROOT/docs/runbooks"
mkdir -p "$PROJECT_ROOT/tools/scripts"
mkdir -p "$PROJECT_ROOT/tools/prompts"

# --- Update Last Updated timestamp in docs/architecture.md ---
ARCH_FILE="$PROJECT_ROOT/docs/architecture.md"
if [ -f "$ARCH_FILE" ]; then
    # Use portable date format
    TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

    # Update the Last Updated line (works on both macOS and Linux)
    if grep -q "^Last Updated:" "$ARCH_FILE"; then
        # Use a temp file for portability
        sed "s/^Last Updated:.*/Last Updated: $TIMESTAMP/" "$ARCH_FILE" > "$ARCH_FILE.tmp"
        mv "$ARCH_FILE.tmp" "$ARCH_FILE"
    fi
    echo "✓ Updated timestamp in docs/architecture.md"
fi

# --- Regenerate docs/structure.md with current file tree ---
STRUCTURE_FILE="$PROJECT_ROOT/docs/structure.md"
echo "# Project Structure" > "$STRUCTURE_FILE"
echo "" >> "$STRUCTURE_FILE"
echo "Auto-generated on $(date '+%Y-%m-%d %H:%M:%S')" >> "$STRUCTURE_FILE"
echo "" >> "$STRUCTURE_FILE"
echo "\`\`\`" >> "$STRUCTURE_FILE"

# Generate tree, excluding common directories
cd "$PROJECT_ROOT"
if command -v tree &> /dev/null; then
    tree -I '.git|__pycache__|venv|.venv|*.pyc|node_modules|.next|.idea' --noreport >> "$STRUCTURE_FILE"
else
    # Fallback if tree is not installed
    find . -type f \
        -not -path './.git/*' \
        -not -path './__pycache__/*' \
        -not -path './venv/*' \
        -not -path './.venv/*' \
        -not -path './node_modules/*' \
        -not -path './.next/*' \
        -not -path './.idea/*' \
        -not -name '*.pyc' \
        | sort >> "$STRUCTURE_FILE"
fi

echo "\`\`\`" >> "$STRUCTURE_FILE"
echo "✓ Regenerated docs/structure.md"

# --- Dependency diff logic ---
DEPS_SNAPSHOT="$PROJECT_ROOT/docs/decisions/.last_deps_snapshot"
PENDING_REVIEW="$PROJECT_ROOT/docs/decisions/.pending_adr_review"
CURRENT_DEPS=$(mktemp)

# Collect current dependencies
{
    echo "=== Python Dependencies (pyproject.toml) ==="
    if [ -f "$PROJECT_ROOT/pyproject.toml" ]; then
        grep -A 100 '^\[project\]' "$PROJECT_ROOT/pyproject.toml" | grep -E '^dependencies|^  "' | head -20 || echo "(none)"
    elif [ -f "$PROJECT_ROOT/requirements.txt" ]; then
        cat "$PROJECT_ROOT/requirements.txt"
    else
        echo "(no Python dependencies file found)"
    fi

    echo ""
    echo "=== Node.js Dependencies (dashboard/package.json) ==="
    if [ -f "$PROJECT_ROOT/dashboard/package.json" ]; then
        # Extract dependencies section
        grep -A 20 '"dependencies"' "$PROJECT_ROOT/dashboard/package.json" | head -25 || echo "(none)"
    else
        echo "(no package.json found)"
    fi
} > "$CURRENT_DEPS"

# Compare with previous snapshot
if [ -f "$DEPS_SNAPSHOT" ]; then
    if ! diff -q "$DEPS_SNAPSHOT" "$CURRENT_DEPS" > /dev/null 2>&1; then
        echo ""
        echo "⚠️  Dependency changes detected!"
        echo ""

        # Write diff to pending review file
        {
            echo "# Pending ADR Review"
            echo ""
            echo "Generated: $(date '+%Y-%m-%d %H:%M:%S')"
            echo ""
            echo "The following dependency changes were detected:"
            echo ""
            echo "\`\`\`diff"
            diff "$DEPS_SNAPSHOT" "$CURRENT_DEPS" || true
            echo "\`\`\`"
            echo ""
            echo "## Action Required"
            echo ""
            echo "Review these changes and determine if any require a new ADR:"
            echo "- New major framework? → CREATE ADR"
            echo "- Library removed? → DEPRECATE existing ADR"
            echo "- Minor version bump? → SKIP"
            echo "- Dev dependency only? → SKIP"
        } > "$PENDING_REVIEW"

        echo "⚠️  Dependency diff written to docs/decisions/.pending_adr_review"
        echo "   Run /init in Claude Code to process ADR updates"
    else
        echo "✓ No dependency changes detected"
    fi
else
    echo "✓ Creating initial dependency snapshot"
fi

# Update snapshot
cp "$CURRENT_DEPS" "$DEPS_SNAPSHOT"
rm "$CURRENT_DEPS"

echo ""
echo "✅ post_init.sh complete"
echo "   Now run /init inside Claude Code to sync AI context"
