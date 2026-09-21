# Upstream Synchronization Strategy

Canonical fork: `josebautista2020/MoneyPrinterTurbo`  
Upstream: `harry0703/MoneyPrinterTurbo`

## Policy

Never pull upstream changes directly into a Content Studio feature branch or merge them unreviewed into `main`.

Use an isolated synchronization branch:

```bash
git remote add upstream https://github.com/harry0703/MoneyPrinterTurbo.git
git fetch upstream
git checkout main
git pull origin main
git checkout -b sync/upstream-YYYYMMDD
git merge --no-ff upstream/main
```

If the `upstream` remote already exists, verify it with `git remote -v` instead of adding it again.

## Required review

Before merging an upstream sync:

1. Inspect changed files, release notes, migrations, configuration changes, dependency updates, and publishing behavior.
2. Pay special attention to `app/`, `pyproject.toml`, `uv.lock`, Docker files, APIs, CLI behavior, and workflows.
3. Resolve conflicts in favor of keeping Content Studio additions isolated under additive extension paths whenever possible.
4. Run the full upstream baseline CI plus Content Studio architecture gates.
5. Run MPTAdapter compatibility tests when its integration surface changes.
6. Open a pull request from `sync/upstream-YYYYMMDD` to `main`; never push an unverified sync directly to `main`.

## Regression rule

An upstream failure that also reproduces on the unmodified upstream revision may be documented as pre-existing. A failure introduced only in the fork blocks the sync.

## Version traceability

Every Content Studio release must record the upstream commit/tag it was validated against. Automatic consumption of upstream `main` or an unpinned `latest` image is prohibited for production.
