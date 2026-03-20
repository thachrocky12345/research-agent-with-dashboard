# /refactor Skill

## Purpose
Safely refactor code while maintaining behavior.

## Usage
```
/refactor [file] --extract-function
/refactor [file] --rename <old> <new>
/refactor [file] --simplify
```

## Refactoring Principles

1. **Preserve Behavior** — Tests must pass before and after
2. **Small Steps** — Make one change at a time
3. **Verify** — Run tests between each change
4. **Document** — Explain what changed and why

## Common Refactorings

- **Extract Function** — Pull out a block into a named function
- **Rename** — Change symbol names consistently across codebase
- **Simplify** — Reduce complexity, remove dead code
- **Inline** — Replace function call with its body
- **Move** — Relocate code to a more appropriate module

## Output Format

```
📝 Refactoring: [description]

Changes:
- file1.ts: Extracted `functionName` from lines X-Y
- file2.ts: Updated 3 call sites

✅ Refactoring complete. Run tests to verify.
```
