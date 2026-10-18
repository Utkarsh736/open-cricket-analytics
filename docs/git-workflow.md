# Git and GitHub CLI workflow

Use these instructions from the root of the repository. Do not run `git init` again if this repository is already initialized.

## 1. Check what is tracked

```bash
git status --short --branch
git remote -v
git ls-files data/raw data/processed
```

`data/raw/` and `data/processed/` are intentionally ignored. They contain downloaded match files and reproducible outputs; do not publish them. If `git ls-files` lists files from those directories, they are already tracked and must be untracked explicitly before the next commit:

```bash
git rm -r --cached data/raw data/processed
```

That command removes those paths from Git's index but leaves the local files on disk. Verify `git status` before committing.

## 2. Lock dependencies and run checks

```bash
uv lock
uv sync --extra dev --extra app --extra notebooks
uv run pytest
uv run ruff check .
```

Commit `pyproject.toml` and `uv.lock` together so the environment can be reproduced. The project source and docs should be committed; downloaded JSON and generated tables should not.

## 3. Stage and commit

Inspect the staged diff before committing:

```bash
git add .gitignore pyproject.toml uv.lock README.md DATA_SOURCES.md docs scripts src apps notebooks tests
git diff --cached --stat
git diff --cached
```

Suggested short commit message for the current upgrade:

```bash
git commit -m "Add descriptive analytics explorer"
```

If the first pipeline has not been committed yet, use a message covering both milestones instead, for example `Add cricket analytics pipeline`.

## 4. Authenticate and publish with `gh`

Check GitHub CLI authentication:

```bash
gh auth status
```

If required, authenticate interactively:

```bash
gh auth login
```

### If the GitHub repository does not exist yet and no remote is configured

Use your preferred visibility. Public is appropriate if you intend to open-source the code and have checked every source license and file for secrets or private data.

```bash
gh repo create open-cricket-analytics --public --source=. --remote=origin --push
```

For a private repository, replace `--public` with `--private`.

### If `origin` already exists

```bash
git remote -v
git push -u origin HEAD
```

### If the repository exists on GitHub but no remote is configured

```bash
git remote add origin https://github.com/YOUR_USERNAME/open-cricket-analytics.git
git push -u origin HEAD
```

Replace `YOUR_USERNAME` with your GitHub username. If the default branch has not been pushed before, `-u` sets the upstream so later pushes can simply use `git push`.

## 5. After each small project

```bash
git status --short --branch
uv run pytest
uv run ruff check .
git add <relevant source files>
git commit -m "Describe the small change"
git push
```

Keep commits focused: data ingestion, descriptive metrics, model experiments and app changes should usually be separate commits when they represent distinct milestones.
