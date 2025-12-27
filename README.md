# ghg

Git productivity tools for streamlined branch and PR workflows.

## Installation

Requires Python 3.11+ and [uv](https://github.com/astral-sh/uv).

```bash
# Install
uv tool install .

# Or for development
uv tool install --editable .
```

Some commands require the [GitHub CLI](https://cli.github.com/) (`gh`).

## Commands

### `ghg move <branch>`

Move uncommitted changes to a new branch based on updated master.

```bash
ghg move feature-xyz
```

This will:
1. Stash current changes
2. Switch to master and pull latest
3. Create the new branch
4. Apply stashed changes

### `ghg cherry <title>`

Cherry-pick workflow: commit changes, create a new branch from master, cherry-pick, and create a PR.

```bash
# Commit current changes and create PR
ghg cherry "Add user authentication"

# Cherry-pick last 3 commits instead
ghg cherry "Add user authentication" -n 3

# Add 'merge' label to PR
ghg cherry "Fix login bug" --merge

# Custom PR body
ghg cherry "Update config" --body "Detailed description here"
```

### `ghg pr <message>`

Create a PR from the current branch.

```bash
# Push and create PR
ghg pr "Add new feature"

# Commit changes first, then create PR
ghg pr "Fix bug" --commit

# Add 'merge' label
ghg pr "Quick fix" --merge
```

### `ghg diff`

Smart diff: shows working tree diff if there are uncommitted changes, otherwise shows diff from master.

```bash
ghg diff
```

### `ghg branch`

List the 10 most recently modified local branches.

```bash
ghg branch
```

### `ghg list`

List open PRs with CI check status.

```bash
# Your PRs
ghg list

# Another author's PRs
ghg list --author username
```

### `ghg merge <pr>`

Add the 'merge' label to a PR.

```bash
ghg merge 123
ghg merge "#123"
```

### `ghg wt create <branch>`

Create a git worktree as a sibling directory with `.envrc` symlinked.

```bash
# Creates ../repo-feature-xyz/
ghg wt create feature-xyz

# Use existing branch
ghg wt create existing-branch --existing

# Output shell commands for eval (cd + uv sync)
eval "$(ghg wt create feature-xyz --shell)"
```

Shell alias for convenience:
```bash
gwta() { eval "$(ghg wt create "$1" --shell)"; }
```

### `ghg wt delete <branch>`

Remove a worktree and delete the branch.

```bash
ghg wt delete feature-xyz

# Keep the branch
ghg wt delete feature-xyz --keep-branch

# Force remove with uncommitted changes
ghg wt delete feature-xyz --force
```

### `ghg wt list`

List worktrees.

```bash
# ghg-managed worktrees only
ghg wt list

# All worktrees
ghg wt list --all
```

## Shell Completion

```bash
ghg --install-completion
```

## License

MIT
