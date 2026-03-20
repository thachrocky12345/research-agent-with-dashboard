# /code-review Skill

## Purpose
Perform a thorough code review of specified files or recent changes.

## Usage
```
/code-review [file or directory]
/code-review --staged
/code-review --last-commit
```

## Review Checklist

1. **Correctness** — Does the code do what it's supposed to?
2. **Security** — Any vulnerabilities (injection, XSS, secrets in code)?
3. **Performance** — Obvious inefficiencies or N+1 queries?
4. **Readability** — Clear naming, appropriate comments?
5. **Maintainability** — DRY, single responsibility, testable?
6. **Edge Cases** — Error handling, boundary conditions?

## Output Format

For each issue found:
```
[SEVERITY] file:line — Description
  Suggestion: How to fix
```

Severity levels: CRITICAL, WARNING, SUGGESTION

End with a summary:
```
✅ Review complete: X issues (Y critical, Z warnings)
```
