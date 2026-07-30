# GitHub Publishing Checklist

1. Review project name and trademark availability.
2. Replace any repository placeholders with the final GitHub URL.
3. Confirm `git status` contains no credentials, `.env`, database, or service-account files.
4. Run `pytest -q`, `ruff check .`, and `docker compose build`.
5. Create an empty repository without a generated README or license.
6. Commit and push.
7. Enable branch protection, Dependabot, secret scanning, CodeQL, Discussions, and private vulnerability reporting.
8. Create release tag `v1.0.0-rc1` and attach the source ZIP.

```bash
git init
git branch -M main
git add .
git commit -m "Release OpenDataGraph v1.0.0 RC1 Phase 1"
git remote add origin https://github.com/hellnbak/OpenDataGraph.git
git push -u origin main
git tag -a v1.0.0-rc1 -m "OpenDataGraph v1.0.0 RC1 Phase 1"
git push origin v1.0.0-rc1
```
