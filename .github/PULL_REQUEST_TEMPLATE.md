# Description

<!-- What does this change and why? Link the issue it closes, e.g. "Closes #12". -->

## Type of change

- [ ] Bug fix (non-breaking change that fixes an issue)
- [ ] New feature (non-breaking change that adds functionality)
- [ ] Breaking change (existing behavior changes)
- [ ] Documentation
- [ ] Tests or CI
- [ ] Refactor / chore

## How was this tested?

<!--
There is no automated suite yet, so describe your manual verification.
The checklist in CONTRIBUTING.md ("Testing") is a good baseline.
-->

## Checklist

- [ ] `ruff check backend/` passes (if backend code changed)
- [ ] `npm run build` passes in `frontend/` (if frontend code changed)
- [ ] I updated the docs for any behavior change (README, ARCHITECTURE, `.env.example`)
- [ ] New configuration is exposed through `core/config.py`, not hard-coded
- [ ] Any user-supplied text reaching the LLM passes through PII sanitization
- [ ] No build artifacts, virtualenvs, `.db`/`.faiss` files, or secrets are committed
- [ ] I added an entry under `## [Unreleased]` in `CHANGELOG.md` (skip for docs-only changes)

## Screenshots

<!-- For UI changes, before/after images are very helpful. -->
