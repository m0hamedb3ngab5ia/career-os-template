"""Keep a private copy of this repo in sync with the public template.

A private copy = the template's code plus personal paths (personal/, profile/, config/, CLAUDE.local.md, data/)
and a few files it keeps different on purpose, listed in `.template-sync-keep` (one glob per line, `# reason`).

- `status`: template commits not merged yet, and drift = files changed here that differ from the template, outside
  personal paths and the keep list (those should be ported to the template).
- `pull`: merge the template's branch on a `sync/<date>` branch, run the local checks, print the PR command.
- `install-hook` / `check-template-push`: a pre-push guard that refuses personal paths going to a template URL.

Settings via git config: `careeros.personalPaths` (comma/space separated) and `careeros.templateUrlPattern`.
"""
from __future__ import annotations

import fnmatch
import re
import shlex
import stat
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Iterable

DEFAULT_REMOTE = "template"
DEFAULT_TEMPLATE_BRANCH = "main"
DEFAULT_BASE = "main"
DEFAULT_PERSONAL_PATHS: tuple[str, ...] = ("personal/", "profile/", "config/", "CLAUDE.local.md", "data/")
DEFAULT_URL_PATTERN = "*career-os-template*"
KEEP_FILE = ".template-sync-keep"
HOOK_MARKER = "careeros-template-guard"
CFG_PERSONAL = "careeros.personalPaths"
CFG_URL_PATTERN = "careeros.templateUrlPattern"

EXIT_IN_SYNC, EXIT_BEHIND, EXIT_DRIFT, EXIT_CONFLICT = 0, 1, 2, 3
ZERO_SHA = "0" * 40


class SyncError(Exception):
    """A refusal or git failure with a message meant for the user."""


class HookExists(SyncError):
    """A pre-push hook that careeros did not write is already there."""


# --- pure helpers -------------------------------------------------------------------------------------------

def parse_personal_paths(value: str | None) -> tuple[str, ...]:
    parts = tuple(p for p in re.split(r"[,\s]+", value or "") if p)
    return parts or DEFAULT_PERSONAL_PATHS


def _path_matches(path: str, entry: str) -> bool:
    """`dir/` matches everything under it; anything else matches exactly, as a directory prefix, or as a glob."""
    if entry.endswith("/"):
        return path.startswith(entry)
    return path == entry or path.startswith(entry + "/") or fnmatch.fnmatchcase(path, entry)


def is_personal(path: str, personal: Iterable[str]) -> bool:
    return any(_path_matches(path, e) for e in personal)


def parse_keep(text: str) -> list[str]:
    out = []
    for line in text.splitlines():
        line = re.sub(r"(^|\s)#.*$", "", line).strip()
        if line:
            out.append(line)
    return out


def matches_keep(path: str, globs: Iterable[str]) -> bool:
    return any(_path_matches(path, g) for g in globs)


def compute_drift(changed: Iterable[str], personal: Iterable[str], keep: Iterable[str]) -> list[str]:
    personal, keep = list(personal), list(keep)
    return sorted({p for p in changed
                   if p != KEEP_FILE and not is_personal(p, personal) and not matches_keep(p, keep)})


def status_exit_code(*, behind: int, drift: int) -> int:
    if drift:
        return EXIT_DRIFT
    return EXIT_BEHIND if behind else EXIT_IN_SYNC


def sync_branch_name(today: date, existing: set[str]) -> str:
    base = f"sync/{today.isoformat()}"
    name, n = base, 1
    while name in existing:
        n += 1
        name = f"{base}-{n}"
    return name


def url_matches(url: str, pattern: str) -> bool:
    return fnmatch.fnmatchcase(url, pattern)


def blocked_paths(paths: Iterable[str], personal: Iterable[str]) -> list[str]:
    personal = list(personal)
    return [p for p in paths if is_personal(p, personal)]


def hook_script(python: str) -> str:
    return f"""#!/bin/sh
# {HOOK_MARKER}: installed by `careeros sync install-hook` (run it again to update).
# Refuses to push personal paths (git config {CFG_PERSONAL}) to a remote whose URL matches
# git config {CFG_URL_PATTERN} (default {DEFAULT_URL_PATTERN}). Other remotes are never checked.
remote="$1"; url="$2"
pattern="$(git config --get {CFG_URL_PATTERN} || echo '{DEFAULT_URL_PATTERN}')"
case "$url" in $pattern) ;; *) exit 0 ;; esac
PY={shlex.quote(python)}
[ -x "$PY" ] || PY="$(git rev-parse --show-toplevel)/.venv/bin/python"
if [ ! -x "$PY" ]; then
  echo "BLOCKED: cannot run the careeros push guard (no python at $PY); reinstall: careeros sync install-hook" >&2
  exit 1
fi
exec "$PY" -m careeros.cli sync check-template-push "$remote" "$url"
"""


def install_hook(hook: Path, python: str, force: bool = False) -> str:
    """Write the guard to `hook`. Returns installed | unchanged | updated | replaced (foreign hook, --force,
    old one kept as <hook>.bak). Raises HookExists for a foreign hook without force."""
    new = hook_script(python)
    result = "installed"
    if hook.exists():
        old = hook.read_text(errors="replace")
        if HOOK_MARKER in old:
            if old == new:
                return "unchanged"
            result = "updated"
        elif not force:
            raise HookExists(f"{hook} exists and was not written by careeros; rerun with --force "
                             f"(the current hook is kept as {hook.name}.bak)")
        else:
            hook.with_name(hook.name + ".bak").write_text(old)
            result = "replaced"
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text(new)
    hook.chmod(hook.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH | stat.S_IRUSR | stat.S_IWUSR)
    return result


def check_plan(root: Path, fallback_python: str) -> list[tuple[str, list[str], Path]]:
    """(name, argv, cwd) for the local checks: pytest with the repo's .venv, then the ui/ build when present."""
    venv = root / ".venv" / "bin" / "python"
    py = str(venv) if venv.exists() else fallback_python
    plan = [("pytest", [py, "-m", "pytest", "-q"], root)]
    ui = root / "ui"
    if (ui / "package.json").exists():
        plan += [("npm ci", ["npm", "ci"], ui), ("npm test", ["npm", "test", "--", "--run"], ui),
                 ("npm run build", ["npm", "run", "build"], ui)]
    return plan


def pr_command(*, branch: str, base: str, remote: str, template_branch: str, commits: list[str],
               results: list[tuple[str, str]]) -> str:
    day = branch.split("/", 1)[-1]
    title = f"sync: merge {remote}/{template_branch} ({day})"
    lines = [f"Merges {remote}/{template_branch} into {base} ({len(commits)} commit(s)):", ""]
    lines += [f"- {c}" for c in commits[:30]]
    if len(commits) > 30:
        lines.append(f"- ... and {len(commits) - 30} more")
    lines += ["", "Local checks (run by `careeros sync pull`, not CI):", ""]
    lines += [f"- {name}: {res}" for name, res in results] or ["- skipped (--no-checks)"]
    body = "\n".join(lines)
    return (f"gh pr create --base {shlex.quote(base)} --head {shlex.quote(branch)} "
            f"--title {shlex.quote(title)} --body {shlex.quote(body)}")


# --- git plumbing -------------------------------------------------------------------------------------------

@dataclass
class Git:
    root: Path

    def run(self, *args: str, check: bool = True, input: str | None = None) -> subprocess.CompletedProcess:
        r = subprocess.run(["git", *args], cwd=self.root, capture_output=True, text=True, input=input)
        if check and r.returncode != 0:
            raise SyncError(f"git {' '.join(args)} failed: {(r.stderr or r.stdout).strip()}")
        return r

    def out(self, *args: str) -> str:
        return self.run(*args).stdout.strip()

    def lines(self, *args: str) -> list[str]:
        return [ln for ln in self.run(*args).stdout.splitlines() if ln.strip()]

    def config(self, key: str) -> str | None:
        r = self.run("config", "--get", key, check=False)
        return r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else None

    def ref_exists(self, ref: str) -> bool:
        return self.run("rev-parse", "--verify", "--quiet", ref + "^{commit}", check=False).returncode == 0


def git_root(start: Path) -> Path:
    r = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=start, capture_output=True, text=True)
    if r.returncode != 0:
        raise SyncError(f"{start} is not inside a git repository")
    return Path(r.stdout.strip())


def personal_paths(g: Git) -> tuple[str, ...]:
    return parse_personal_paths(g.config(CFG_PERSONAL))


def _fetch(g: Git, remote: str, template_branch: str) -> str:
    if remote not in g.lines("remote"):
        raise SyncError(f"no git remote named {remote!r}; add it: git remote add {remote} <template repo URL> "
                        f"(or pass --remote)")
    g.run("fetch", "--quiet", remote)
    ref = f"{remote}/{template_branch}"
    if not g.ref_exists(ref):
        raise SyncError(f"{ref} not found after fetching {remote}")
    return ref


# --- status -------------------------------------------------------------------------------------------------

@dataclass
class Status:
    ref: str
    behind: list[str] = field(default_factory=list)
    drift: list[str] = field(default_factory=list)

    @property
    def exit_code(self) -> int:
        return status_exit_code(behind=len(self.behind), drift=len(self.drift))


def _keep_globs(root: Path) -> list[str]:
    f = root / KEEP_FILE
    return parse_keep(f.read_text()) if f.exists() else []


def compute_status(root: Path, remote: str = DEFAULT_REMOTE, template_branch: str = DEFAULT_TEMPLATE_BRANCH,
                   fetch: bool = True) -> Status:
    g = Git(root)
    ref = _fetch(g, remote, template_branch) if fetch else f"{remote}/{template_branch}"
    if not g.ref_exists(ref):
        raise SyncError(f"{ref} not found; fetch it first (drop --no-fetch)")
    behind = g.lines("log", "--format=%h %s", f"HEAD..{ref}")
    differs = set(g.lines("diff", "--name-only", ref, "HEAD"))
    # Only files changed on this side count as drift, not the template's own unmerged changes.
    mb = g.run("merge-base", ref, "HEAD", check=False).stdout.strip()
    changed = differs & set(g.lines("diff", "--name-only", mb, "HEAD")) if mb else differs
    return Status(ref=ref, behind=behind, drift=compute_drift(changed, personal_paths(g), _keep_globs(root)))


def format_status(st: Status) -> list[str]:
    out = []
    if st.behind:
        out.append(f"behind: {len(st.behind)} commit(s) on {st.ref} not merged here")
        out += [f"  {c}" for c in st.behind]
        out.append("  -> careeros sync pull")
    if st.drift:
        out.append(f"drift: {len(st.drift)} file(s) differ from {st.ref} "
                   f"(not personal, not in {KEEP_FILE}); port them to the template:")
        out += [f"  {p}" for p in st.drift]
        out.append(f"  -> in a template checkout (or here: git switch -c fix/<topic> {st.ref}), apply the change, "
                   f"PR it, then careeros sync pull. Intentionally different? add it to {KEEP_FILE} with a reason.")
    if not out:
        out.append(f"in sync with {st.ref}")
    return out


# --- pull ---------------------------------------------------------------------------------------------------

@dataclass
class PullResult:
    code: int
    lines: list[str]
    err: list[str] = field(default_factory=list)


def run_checks(root: Path, fallback_python: str = sys.executable) -> list[tuple[str, str]]:
    results: list[tuple[str, str]] = []
    plan = check_plan(root, fallback_python)
    ui_failed = False
    for name, argv, cwd in plan:
        if name.startswith("npm") and ui_failed:
            results.append((name, "not run (earlier ui step failed)"))
            continue
        try:
            r = subprocess.run(argv, cwd=cwd, capture_output=True, text=True)
            ok = r.returncode == 0
            tail = (r.stdout + r.stderr).strip().splitlines()[-1:] if r.stdout or r.stderr else []
        except FileNotFoundError:
            ok, tail = False, [f"{argv[0]} not found"]
        res = "passed" if ok else "failed" + (f" ({tail[0].strip()})" if tail else "")
        results.append((name, res))
        if not ok and name.startswith("npm"):
            ui_failed = True
    if not any(n.startswith("npm") for n, _, _ in plan):
        results.append(("ui", "skipped (no ui/package.json)"))
    return results


def pull(root: Path, *, remote: str = DEFAULT_REMOTE, template_branch: str = DEFAULT_TEMPLATE_BRANCH,
         base: str = DEFAULT_BASE, branch: str | None = None, checks: bool = True,
         today: date | None = None) -> PullResult:
    g = Git(root)
    if g.out("status", "--porcelain", "--untracked-files=no"):
        return PullResult(1, [], ["refusing to sync: uncommitted changes; commit or stash them first"])
    ref = _fetch(g, remote, template_branch)
    if not g.ref_exists(base):
        return PullResult(1, [], [f"base branch {base!r} not found (pass --base)"])
    if g.run("merge-base", "--is-ancestor", ref, base, check=False).returncode == 0:
        return PullResult(0, [f"{base} is already up to date with {ref}; nothing to sync"])
    commits = g.lines("log", "--format=%h %s", f"{base}..{ref}")
    existing = {b.strip() for b in g.lines("for-each-ref", "--format=%(refname:short)", "refs/heads/")}
    if branch is None:
        branch = sync_branch_name(today or date.today(), existing)
    elif branch in existing:
        return PullResult(1, [], [f"branch {branch!r} already exists; pick another --branch"])
    g.run("switch", "--quiet", "-c", branch, base)
    lines = [f"on {branch} (from {base}): merging {len(commits)} commit(s) from {ref}"]
    m = g.run("merge", "--no-ff", "--no-edit", "-m", f"Merge {ref} into {branch}", ref, check=False)
    if m.returncode != 0:
        conflicts = g.lines("diff", "--name-only", "--diff-filter=U")
        if not conflicts:
            raise SyncError(f"git merge failed: {(m.stderr or m.stdout).strip()}")
        err = [f"merge conflict in {len(conflicts)} file(s):", *[f"  {c}" for c in conflicts], "",
               "resolve them (keep the template's code; keep your personal values), then:",
               f"  git add {' '.join(shlex.quote(c) for c in conflicts)}",
               "  git commit --no-edit",
               "  careeros sync status          # expect exit 0",
               "  .venv/bin/python -m pytest -q  # and the ui/ checks if you have ui/",
               "or give up on this sync:",
               f"  git merge --abort && git switch {base} && git branch -D {branch}"]
        return PullResult(EXIT_CONFLICT, lines, err)
    lines.append("merged.")
    results: list[tuple[str, str]] = []
    if checks:
        results = run_checks(root)
        lines.append("local checks:")
        lines += [f"  {n}: {r}" for n, r in results]
        if any(r.startswith("failed") for _, r in results):
            return PullResult(1, lines, [f"checks failed on {branch}; fix, commit, rerun the checks, then open the PR"])
    lines += ["", "next:", f"  git push -u origin {branch}",
              "  " + pr_command(branch=branch, base=base, remote=remote, template_branch=template_branch,
                                commits=commits, results=results)]
    return PullResult(0, lines)


# --- pre-push guard -----------------------------------------------------------------------------------------

def hook_path(root: Path) -> Path:
    p = Path(Git(root).out("rev-parse", "--git-path", "hooks/pre-push"))
    return p if p.is_absolute() else root / p


def check_push(root: Path, url: str, updates: str) -> list[str]:
    """Error lines if this push (pre-push stdin: `<lref> <lsha> <rref> <rsha>` per line) would send personal
    paths to a template URL; [] when allowed."""
    g = Git(root)
    pattern = g.config(CFG_URL_PATTERN) or DEFAULT_URL_PATTERN
    if not url_matches(url, pattern):
        return []
    personal = personal_paths(g)
    for line in updates.splitlines():
        parts = line.split()
        if len(parts) != 4 or parts[1] == ZERO_SHA:
            continue
        lref, lsha = parts[0], parts[1]
        bad = blocked_paths(g.lines("ls-tree", "-r", "--name-only", lsha), personal)
        if bad:
            shown = [f"  {p}" for p in bad[:10]] + ([f"  ... and {len(bad) - 10} more"] if len(bad) > 10 else [])
            return [f"BLOCKED: {lref} contains personal paths; never push them to the template ({url}):", *shown,
                    "Branch template work from the template instead: git switch -c fix/<topic> template/main"]
    return []
