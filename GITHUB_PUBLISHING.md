# GitHub Publishing Checklist

## Before publishing

1. Choose the final repository and organization name; perform a naming/trademark check.
2. Replace `YOUR-ORG` in the README clone command.
3. Decide whether Apache-2.0 matches the intended business model. Do not switch to FSL or another source-available license without updating the README and getting legal review.
4. Add a private security contact or enable GitHub private vulnerability reporting.
5. Review the entire repository for credentials and proprietary information:

```bash
git grep -nEi '(api[_-]?key|secret|password|token|private[_-]?key)' -- ':!GITHUB_PUBLISHING.md' ':!app/classification.py'
find . -type f -size +10M -print
```

6. Run validation:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
ruff check .
pytest -q
docker compose up --build
```

## Create and push the repository

Create an empty GitHub repository without a generated README or license, then run:

```bash
cd opendatagraph-v1
git init
git branch -M main
git add .
git commit -m "Initial OpenDataGraph V1"
git remote add origin git@github.com:YOUR-ORG/opendatagraph.git
git push -u origin main
```

For HTTPS authentication, use GitHub CLI or a personal access token; GitHub does not accept account passwords for Git operations.

## Suggested first release

```bash
git tag -a v0.1.0 -m "OpenDataGraph V1 community preview"
git push origin v0.1.0
```

Use the `0.1.0` changelog entry as the release notes and mark the release as a prerelease.
