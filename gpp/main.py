#!/usr/bin/env python

import subprocess
import shutil
import sys
import json
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(help="Git productivity tools")
pr_app = typer.Typer(help="Pull request helpers", invoke_without_command=True)
wt_app = typer.Typer(help="Git worktree helpers")


def run_git_command(cmd: list[str]) -> tuple[int, str, str]:
    """Run a git command and return exit code, stdout, stderr"""
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def check_git_repo():
    """Ensure we're in a git repository"""
    if not Path(".git").exists():
        typer.echo("Error: Not in a git repository", err=True)
        raise typer.Exit(1)


def title_to_branch_name(title: str) -> str:
    """Convert a title to a kebab-case branch name"""
    import re
    # Remove special characters and convert to lowercase
    cleaned = re.sub(r'[^\w\s-]', '', title.lower())
    # Replace spaces and underscores with hyphens
    kebab = re.sub(r'[\s_]+', '-', cleaned.strip())
    # Remove multiple consecutive hyphens
    kebab = re.sub(r'-+', '-', kebab)
    # Remove leading/trailing hyphens
    return kebab.strip('-')


@app.command()
def move(branch_name: str):
    """
    Move current unstaged changes to a new branch based on updated master.
    
    This command will:
    1. Stash current changes
    2. Switch to master
    3. Pull latest changes from origin
    4. Create and switch to the new branch
    5. Apply stashed changes
    """
    check_git_repo()
    
    typer.echo(f"Moving changes to new branch: {branch_name}")
    
    # Check if there are unstaged changes to stash
    exit_code, stdout, stderr = run_git_command(["git", "status", "--porcelain"])
    if exit_code != 0:
        typer.echo(f"Error checking git status: {stderr}", err=True)
        raise typer.Exit(1)
    
    has_changes = bool(stdout.strip())
    stash_created = False
    
    if has_changes:
        typer.echo("Stashing current changes...")
        exit_code, _, stderr = run_git_command(["git", "stash", "push", "-m", f"gpp move to {branch_name}"])
        if exit_code != 0:
            typer.echo(f"Error stashing changes: {stderr}", err=True)
            raise typer.Exit(1)
        stash_created = True
    else:
        typer.echo("No unstaged changes to stash")
    
    # Switch to master
    typer.echo("Switching to master...")
    exit_code, _, stderr = run_git_command(["git", "checkout", "master"])
    if exit_code != 0:
        typer.echo(f"Error switching to master: {stderr}", err=True)
        raise typer.Exit(1)
    
    # Pull latest changes
    typer.echo("Pulling latest changes from origin...")
    exit_code, _, stderr = run_git_command(["git", "pull", "origin", "master"])
    if exit_code != 0:
        typer.echo(f"Error pulling from origin: {stderr}", err=True)
        raise typer.Exit(1)
    
    # Create and switch to new branch
    typer.echo(f"Creating and switching to branch: {branch_name}")
    exit_code, _, stderr = run_git_command(["git", "checkout", "-b", branch_name])
    if exit_code != 0:
        typer.echo(f"Error creating branch: {stderr}", err=True)
        raise typer.Exit(1)
    
    # Apply stashed changes if we created a stash
    if stash_created:
        typer.echo("Applying stashed changes...")
        exit_code, _, stderr = run_git_command(["git", "stash", "pop"])
        if exit_code != 0:
            typer.echo(f"Error applying stashed changes: {stderr}", err=True)
            typer.echo("Your changes are still in the stash. Use 'git stash pop' to apply them manually.")
            raise typer.Exit(1)
    
    typer.echo(f"✅ Successfully moved to branch '{branch_name}'")


@app.command()
def diff():
    """Show git diff. If unstaged commits exist, show working tree diff. Otherwise, show diff from master."""
    check_git_repo()
    
    # Check if there are unstaged changes
    exit_code, stdout, stderr = run_git_command(["git", "status", "--porcelain"])
    if exit_code != 0:
        typer.echo(f"Error checking git status: {stderr}", err=True)
        raise typer.Exit(1)
    
    has_unstaged_changes = bool(stdout.strip())
    
    if has_unstaged_changes:
        typer.echo("Showing working tree diff...")
        cmd = ["git", "diff"]
    else:
        typer.echo("Showing diff from master to current branch...")
        cmd = ["git", "diff", "master...HEAD"]
    
    # Run git diff and stream output directly
    result = subprocess.run(cmd)
    if result.returncode != 0:
        raise typer.Exit(result.returncode)


@app.command()
def cherry(
    title: str,
    merge: bool = typer.Option(False, "--merge", "-m", help="Add 'merge' label to the PR"),
    num_commits: Optional[int] = typer.Option(None, "--num", "-n", help="Number of previous commits to cherry-pick"),
    body: Optional[str] = typer.Option(None, "--body", "-b", help="PR body (defaults to title)"),
):
    """
    Cherry-pick workflow: commit changes, create new branch from master, cherry-pick, and create PR.
    
    This command will:
    1. Commit any unstaged changes with the given title (if any exist, errors if -n is used with unstaged changes)
    2. Switch to master and pull latest changes
    3. Create a new branch with kebab-case name from title
    4. Cherry-pick the last n commits from the original branch (default: 1)
    5. Create a PR with the title/body
    6. Switch back to the original branch
    """
    check_git_repo()
    
    if shutil.which("gh") is None:
        typer.echo(
            "Error: GitHub CLI 'gh' not found. Install from https://cli.github.com/",
            err=True,
        )
        raise typer.Exit(1)
    
    # Get current branch name
    exit_code, original_branch, stderr = run_git_command(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    if exit_code != 0:
        typer.echo(f"Error getting current branch: {stderr}", err=True)
        raise typer.Exit(1)
    
    original_branch = original_branch.strip()
    typer.echo(f"Starting cherry-pick workflow from branch: {original_branch}")
    
    # Check for unstaged changes
    exit_code, status_output, stderr = run_git_command(["git", "status", "--porcelain"])
    if exit_code != 0:
        typer.echo(f"Error checking git status: {stderr}", err=True)
        raise typer.Exit(1)
    
    has_unstaged_changes = bool(status_output.strip())
    commits_to_pick = []
    
    # If -n flag is used, error if there are unstaged commits
    if num_commits is not None and has_unstaged_changes:
        typer.echo("Error: Cannot use -n flag when there are unstaged commits.", err=True)
        typer.echo("Please commit or stash your changes first.", err=True)
        raise typer.Exit(1)
    
    if has_unstaged_changes:
        typer.echo("Committing unstaged changes...")
        
        # Stage all changes
        exit_code, _, stderr = run_git_command(["git", "add", "-A"])
        if exit_code != 0:
            typer.echo(f"Error staging changes: {stderr}", err=True)
            raise typer.Exit(1)
        
        # Commit with the provided title
        exit_code, _, stderr = run_git_command(["git", "commit", "-m", title])
        if exit_code != 0:
            typer.echo(f"Error creating commit: {stderr}", err=True)
            raise typer.Exit(1)
        
        # Get the commit hash we just created
        exit_code, commit_hash, stderr = run_git_command(["git", "rev-parse", "HEAD"])
        if exit_code != 0:
            typer.echo(f"Error getting commit hash: {stderr}", err=True)
            raise typer.Exit(1)
        commits_to_pick = [commit_hash.strip()]
    else:
        # Get the last n commits (or just 1 if no -n flag)
        num_to_get = num_commits if num_commits is not None else 1
        typer.echo(f"Getting last {num_to_get} commit{'s' if num_to_get > 1 else ''} to cherry-pick")
        
        # Get commit hashes in reverse order (oldest first for cherry-picking)
        exit_code, commit_output, stderr = run_git_command([
            "git", "rev-list", "--reverse", f"HEAD~{num_to_get}..HEAD"
        ])
        if exit_code != 0:
            typer.echo(f"Error getting commit hashes: {stderr}", err=True)
            raise typer.Exit(1)
        
        commits_to_pick = commit_output.strip().split('\n') if commit_output.strip() else []
        if len(commits_to_pick) != num_to_get:
            typer.echo(f"Error: Could only find {len(commits_to_pick)} commits, but {num_to_get} were requested", err=True)
            raise typer.Exit(1)
    
    # Switch to master
    typer.echo("Switching to master...")
    exit_code, _, stderr = run_git_command(["git", "checkout", "master"])
    if exit_code != 0:
        typer.echo(f"Error switching to master: {stderr}", err=True)
        raise typer.Exit(1)
    
    # Pull latest changes
    typer.echo("Pulling latest changes from origin...")
    exit_code, _, stderr = run_git_command(["git", "pull", "origin", "master"])
    if exit_code != 0:
        typer.echo(f"Error pulling from origin: {stderr}", err=True)
        raise typer.Exit(1)
    
    # Create new branch with kebab-case name
    branch_name = title_to_branch_name(title)
    typer.echo(f"Creating new branch: {branch_name}")
    exit_code, _, stderr = run_git_command(["git", "checkout", "-b", branch_name])
    if exit_code != 0:
        typer.echo(f"Error creating branch: {stderr}", err=True)
        raise typer.Exit(1)
    
    # Cherry-pick the commits
    for i, commit_hash in enumerate(commits_to_pick, 1):
        if len(commits_to_pick) > 1:
            typer.echo(f"Cherry-picking commit {i}/{len(commits_to_pick)}: {commit_hash[:8]}")
        else:
            typer.echo(f"Cherry-picking commit: {commit_hash[:8]}")
        
        exit_code, _, stderr = run_git_command(["git", "cherry-pick", commit_hash])
        if exit_code != 0:
            typer.echo(f"Error cherry-picking commit {commit_hash[:8]}: {stderr}", err=True)
            typer.echo("You may need to resolve conflicts manually")
            raise typer.Exit(1)
    
    # Push the new branch
    typer.echo(f"Pushing branch '{branch_name}' to origin...")
    exit_code, _, stderr = run_git_command(["git", "push", "-u", "origin", branch_name])
    if exit_code != 0:
        typer.echo(f"Error pushing branch: {stderr}", err=True)
        raise typer.Exit(1)
    
    # Create PR
    typer.echo("Creating pull request...")
    pr_body = body if body is not None else title
    pr_cmd = ["gh", "pr", "create", "--title", title, "--body", pr_body]
    if merge:
        pr_cmd += ["--label", "merge"]
    
    result = subprocess.run(pr_cmd)
    if result.returncode != 0:
        typer.echo("Error creating PR, but branch was created successfully", err=True)
        raise typer.Exit(result.returncode)
    
    # Switch back to original branch
    typer.echo(f"Switching back to original branch: {original_branch}")
    exit_code, _, stderr = run_git_command(["git", "checkout", original_branch])
    if exit_code != 0:
        typer.echo(f"Error switching back to original branch: {stderr}", err=True)
        typer.echo(f"You are currently on branch: {branch_name}")
        raise typer.Exit(1)
    
    typer.echo(f"✅ Cherry-pick workflow completed successfully!")
    typer.echo(f"   Branch created: {branch_name}")
    typer.echo(f"   Original branch: {original_branch}")


@app.command()
def branch():
    """List the top 10 most recent branches by last change."""
    check_git_repo()
    
    # Get branches sorted by last commit date
    cmd = [
        "git", "for-each-ref", 
        "--sort=-committerdate",
        "--count=10",
        "--format=%(refname:short)|%(committerdate:relative)",
        "refs/heads/"
    ]
    
    exit_code, stdout, stderr = run_git_command(cmd)
    if exit_code != 0:
        typer.echo(f"Error fetching branches: {stderr}", err=True)
        raise typer.Exit(exit_code)
    
    if not stdout.strip():
        typer.echo("No branches found")
        return
    
    # Create rich table
    console = Console()
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Branch", style="green", no_wrap=True)
    table.add_column("Last Change", style="yellow", no_wrap=True)
    
    for line in stdout.strip().split('\n'):
        if '|' in line:
            parts = line.split('|', 1)
            if len(parts) == 2:
                branch, date = parts
                table.add_row(branch, date)
    
    console.print(table)


@app.command()
def merge(pr_number: str):
    """Add 'merge' label to a PR by number."""
    check_git_repo()
    
    if shutil.which("gh") is None:
        typer.echo(
            "Error: GitHub CLI 'gh' not found. Install from https://cli.github.com/",
            err=True,
        )
        raise typer.Exit(1)
    
    # Parse PR number - handle both "123" and "#123" formats
    if pr_number.startswith("#"):
        pr_number = pr_number[1:]
    
    typer.echo(f"Adding 'merge' label to PR #{pr_number}...")
    
    cmd = ["gh", "pr", "edit", pr_number, "--add-label", "merge"]
    result = subprocess.run(cmd)
    if result.returncode != 0:
        raise typer.Exit(result.returncode)
    
    typer.echo(f"✅ Added 'merge' label to PR #{pr_number}")


@app.command(name="list")
def list_prs(
    author: str = typer.Option(
        "@me", "--author", "-a", help="Author to filter PRs by (passed to gh)"
    ),
):
    """List PRs via GitHub CLI with check statuses in a table."""
    # Ensure we're in a git repo so `gh` resolves the repository context
    check_git_repo()

    if shutil.which("gh") is None:
        typer.echo(
            "Error: GitHub CLI 'gh' not found. Install from https://cli.github.com/",
            err=True,
        )
        raise typer.Exit(1)

    # Fetch PR data with JSON output to get detailed info
    cmd = ["gh", "pr", "list", "--author", author, "--json", "number,title,headRefName,statusCheckRollup"]
    exit_code, stdout, stderr = run_git_command(cmd)
    
    if exit_code != 0:
        typer.echo(f"Error fetching PRs: {stderr}", err=True)
        raise typer.Exit(exit_code)
    
    if not stdout.strip():
        typer.echo("No PRs found")
        return
    
    try:
        prs = json.loads(stdout)
    except json.JSONDecodeError:
        typer.echo("Error parsing PR data", err=True)
        raise typer.Exit(1)
    
    # Create rich table
    console = Console()
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("PR #", style="cyan", no_wrap=True)
    table.add_column("Title", style="white")
    table.add_column("Branch", style="green")
    table.add_column("Checks", style="yellow", no_wrap=True)
    
    for pr in prs:
        # Parse check status from detailed rollup
        status_rollup = pr.get("statusCheckRollup", [])
        
        if not status_rollup:
            check_status = "❓ No checks"
        else:
            # Count different status types
            success_count = 0
            failure_count = 0
            pending_count = 0
            skipped_count = 0
            
            for check in status_rollup:
                if check.get("__typename") == "CheckRun":
                    conclusion = check.get("conclusion", "").upper()
                    if conclusion == "SUCCESS":
                        success_count += 1
                    elif conclusion == "FAILURE":
                        failure_count += 1
                    elif conclusion == "SKIPPED":
                        skipped_count += 1
                    elif check.get("status") == "IN_PROGRESS":
                        pending_count += 1
                elif check.get("__typename") == "StatusContext":
                    state = check.get("state", "").upper()
                    if state == "SUCCESS":
                        success_count += 1
                    elif state == "FAILURE":
                        failure_count += 1
                    elif state == "PENDING":
                        pending_count += 1
            
            # Format status summary
            total_checks = len(status_rollup)
            if failure_count > 0:
                check_status = f"❌ {failure_count}/{total_checks} failed"
            elif pending_count > 0:
                check_status = f"⏳ {pending_count}/{total_checks} pending"
            elif success_count > 0:
                check_status = f"✅ {success_count}/{total_checks} passed"
            else:
                check_status = f"⚪ {skipped_count}/{total_checks} skipped"
        
        table.add_row(
            f"#{pr['number']}",
            pr["title"],
            pr["headRefName"],
            check_status
        )
    
    console.print(table)


@pr_app.callback()
def pr_default(
    message: str = typer.Argument(..., help="PR title and body"),
    commit: bool = typer.Option(False, "--commit", "-c", help="Commit unstaged changes first"),
    merge: bool = typer.Option(False, "--merge", "-m", help="Add label 'merge' to the PR"),
    body: Optional[str] = typer.Option(None, "--body", "-b", help="PR body (defaults to title)"),
):
    """Create a PR with given title/body; optionally commit changes first."""
    check_git_repo()

    if shutil.which("gh") is None:
        typer.echo(
            "Error: GitHub CLI 'gh' not found. Install from https://cli.github.com/",
            err=True,
        )
        raise typer.Exit(1)

    if commit:
        # Stage and commit any changes; if none, continue without error
        exit_code, status_out, status_err = run_git_command(["git", "status", "--porcelain"])
        if exit_code != 0:
            typer.echo(f"Error checking git status: {status_err}", err=True)
            raise typer.Exit(1)

        if status_out.strip():
            typer.echo("Staging changes...")
            exit_code, _, add_err = run_git_command(["git", "add", "-A"])
            if exit_code != 0:
                typer.echo(f"Error staging changes: {add_err}", err=True)
                raise typer.Exit(1)

            typer.echo("Creating commit...")
            exit_code, _, commit_err = run_git_command(["git", "commit", "-m", message])
            if exit_code != 0:
                typer.echo(f"Error creating commit: {commit_err}", err=True)
                raise typer.Exit(1)
        else:
            typer.echo("No changes to commit; proceeding to PR creation.")

    # Determine current branch
    exit_code, branch, branch_err = run_git_command(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    if exit_code != 0:
        typer.echo(f"Error determining branch: {branch_err}", err=True)
        raise typer.Exit(1)

    branch = branch.strip()

    # Ensure origin exists
    exit_code, _, remote_err = run_git_command(["git", "remote", "get-url", "origin"])
    if exit_code != 0:
        typer.echo("Error: remote 'origin' not set. Cannot push branch.", err=True)
        raise typer.Exit(1)

    # Push branch
    typer.echo(f"Pushing branch '{branch}' to origin...")
    exit_code, _, push_err = run_git_command(["git", "push", "-u", "origin", branch])
    if exit_code != 0:
        typer.echo(f"Error pushing branch: {push_err}", err=True)
        raise typer.Exit(1)

    # Create PR
    typer.echo("Creating pull request...")
    pr_body = body if body is not None else message
    pr_cmd = [
        "gh",
        "pr",
        "create",
        "--title",
        message,
        "--body",
        pr_body,
    ]
    if merge:
        pr_cmd += ["--label", "merge"]
    result = subprocess.run(pr_cmd)
    if result.returncode != 0:
        raise typer.Exit(result.returncode)


app.add_typer(pr_app, name="pr")
app.add_typer(wt_app, name="wt")


def get_repo_name() -> str:
    """Get the current repository name from the git remote or directory name."""
    exit_code, stdout, _ = run_git_command(["git", "remote", "get-url", "origin"])
    if exit_code == 0 and stdout:
        repo_name = stdout.rstrip(".git").split("/")[-1]
        return repo_name
    return Path.cwd().name


def get_main_worktree() -> Path:
    """Get the path to the main worktree."""
    exit_code, stdout, _ = run_git_command(["git", "worktree", "list", "--porcelain"])
    if exit_code == 0 and stdout:
        for line in stdout.split("\n"):
            if line.startswith("worktree "):
                return Path(line.split(" ", 1)[1])
    return Path.cwd()


@wt_app.command("create")
def wt_create(
    branch: str = typer.Argument(..., help="Branch name for the worktree"),
    new_branch: bool = typer.Option(True, "--new/--existing", "-n/-e", help="Create new branch or use existing"),
    shell: bool = typer.Option(False, "--shell", "-s", help="Output shell commands to eval (for cd and uv sync)"),
):
    """
    Create a git worktree as a sibling directory with .envrc symlinked.

    Creates ../repo-branch/ with a symlink to ../repo/.envrc

    Use with --shell to cd into the directory and run uv sync:
        eval "$(ghg wt create feature-xyz --shell)"

    Or add a shell alias:
        gwta() { eval "$(ghg wt create "$1" --shell)"; }
    """
    check_git_repo()

    repo_name = get_repo_name()
    main_worktree = get_main_worktree()
    worktree_path = main_worktree.parent / f"{repo_name}-{branch}"

    if worktree_path.exists():
        typer.echo(f"Error: Directory already exists: {worktree_path}", err=True)
        raise typer.Exit(1)

    if not shell:
        typer.echo(f"Creating worktree at {worktree_path}...", err=shell)

    if new_branch:
        cmd = ["git", "worktree", "add", str(worktree_path), "-b", branch]
    else:
        cmd = ["git", "worktree", "add", str(worktree_path), branch]

    exit_code, _, stderr = run_git_command(cmd)
    if exit_code != 0:
        typer.echo(f"Error creating worktree: {stderr}", err=True)
        raise typer.Exit(1)

    main_envrc = main_worktree / ".envrc"
    if main_envrc.exists():
        worktree_envrc = worktree_path / ".envrc"
        relative_envrc = Path("..") / repo_name / ".envrc"
        worktree_envrc.symlink_to(relative_envrc)
        if not shell:
            typer.echo(f"Created .envrc symlink -> {relative_envrc}")

    if shell:
        typer.echo(f'cd "{worktree_path}" && uv sync')
    else:
        typer.echo(f"✅ Worktree created at {worktree_path}")
        typer.echo(f"   Run: cd {worktree_path} && uv sync")


def find_worktree_by_branch(branch: str) -> Optional[Path]:
    """Find worktree path by branch name."""
    exit_code, stdout, _ = run_git_command(["git", "worktree", "list", "--porcelain"])
    if exit_code != 0:
        return None

    current_worktree = None
    for line in stdout.split("\n"):
        if line.startswith("worktree "):
            current_worktree = Path(line.split(" ", 1)[1])
        elif line.startswith("branch ") and current_worktree:
            worktree_branch = line.split("/")[-1]
            if worktree_branch == branch:
                return current_worktree
    return None


@wt_app.command("delete")
def wt_delete(
    branch: str = typer.Argument(..., help="Branch name of the worktree to delete"),
    force: bool = typer.Option(False, "--force", "-f", help="Force removal even with uncommitted changes"),
    keep_branch: bool = typer.Option(False, "--keep-branch", "-k", help="Keep the branch after removing worktree"),
):
    """
    Remove a git worktree and optionally delete the branch.

    Finds the worktree by branch name regardless of where it's located.
    """
    check_git_repo()

    worktree_path = find_worktree_by_branch(branch)

    if not worktree_path:
        typer.echo(f"Error: No worktree found for branch: {branch}", err=True)
        raise typer.Exit(1)

    typer.echo(f"Removing worktree at {worktree_path}...")

    cmd = ["git", "worktree", "remove", str(worktree_path)]
    if force:
        cmd.append("--force")

    exit_code, _, stderr = run_git_command(cmd)
    if exit_code != 0:
        typer.echo(f"Error removing worktree: {stderr}", err=True)
        raise typer.Exit(1)

    if not keep_branch:
        typer.echo(f"Deleting branch {branch}...")
        exit_code, _, stderr = run_git_command(["git", "branch", "-D", branch])
        if exit_code != 0:
            typer.echo(f"Warning: Could not delete branch: {stderr}", err=True)
        else:
            typer.echo(f"Deleted branch {branch}")

    typer.echo(f"✅ Worktree removed")


@wt_app.command("list")
def wt_list(
    all_worktrees: bool = typer.Option(False, "--all", "-a", help="Show all worktrees, not just ghg-managed ones"),
):
    """List worktrees for this repository.

    By default, only shows ghg-managed worktrees (sibling directories matching repo-branch pattern).
    Use --all to show all worktrees including those created by other tools.
    """
    check_git_repo()

    exit_code, stdout, stderr = run_git_command(["git", "worktree", "list"])
    if exit_code != 0:
        typer.echo(f"Error listing worktrees: {stderr}", err=True)
        raise typer.Exit(1)

    if not stdout:
        typer.echo("No worktrees found")
        return

    if all_worktrees:
        typer.echo(stdout)
        return

    repo_name = get_repo_name()
    main_worktree = get_main_worktree()
    expected_parent = main_worktree.parent

    filtered_lines = []
    for line in stdout.strip().split("\n"):
        if not line:
            continue
        worktree_path = Path(line.split()[0])
        is_main = worktree_path == main_worktree
        is_ghg_managed = (
            worktree_path.parent == expected_parent
            and worktree_path.name.startswith(f"{repo_name}-")
        )
        if is_main or is_ghg_managed:
            filtered_lines.append(line)

    if filtered_lines:
        typer.echo("\n".join(filtered_lines))
    else:
        typer.echo("No ghg-managed worktrees found (use --all to see all worktrees)")


def main() -> None:
    """CLI entrypoint for uv console script."""
    app()


if __name__ == "__main__":
    main()
