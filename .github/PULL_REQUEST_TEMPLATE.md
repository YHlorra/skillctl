## Summary

One or two sentences on what this PR changes.

## Related issue

Link the issue this fixes (if any): `Closes #N` or `Refs #N`.

## Type of change

- [ ] Bug fix (non-breaking change that fixes an issue)
- [ ] New feature (non-breaking change that adds functionality)
- [ ] Breaking change (existing behavior changes)
- [ ] Documentation only
- [ ] Refactor (no behavior change)

## How was this tested?

- [ ] New pytest tests in `tests/`
- [ ] Manual smoke test in sandbox (`SKILL_LIBRARY_PATH=/tmp/...`)
- [ ] Other (describe below)

Describe the manual smoke test:

```bash
SKILL_LIBRARY_PATH=/tmp/test-lib python scripts/skillctl.py install ...
# observed: ...
```

## Checklist

- [ ] My code follows the project's coding conventions (see `CONTRIBUTING.md`)
- [ ] I have added tests that prove my fix/feature works
- [ ] New and existing unit tests pass locally (`pytest tests/ -v`)
- [ ] I have updated `CHANGELOG.md` under `[Unreleased]`
- [ ] I have updated `SKILL.md` routing table (if command surface changed)
- [ ] I have updated `references/cli-spec.md` (if CLI surface changed)

## Out-of-scope changes

If this PR includes any unrelated changes (refactors, formatting, dependency
bumps that aren't required for the fix), list them here so reviewers can
spot them.
