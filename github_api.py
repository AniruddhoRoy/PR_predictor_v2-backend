"""Fetch the GitHub data needed by the notebook models."""

import json
import os
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fastapi import HTTPException


PR_URL = re.compile(
    r"https?://github\.com/([\w-]+)/([\w.-]+)/pull/([1-9][0-9]*)/?(?:[?#][^\s]*)?",
    re.IGNORECASE | re.ASCII,
)


def _get(path):
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "PR-Predictor",
        "X-GitHub-Api-Version": "2026-03-10",
    }
    token = os.getenv("GITHUB_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        with urlopen(Request("https://api.github.com" + path, headers=headers), timeout=20) as response:
            return json.load(response)
    except HTTPError as error:
        message = error.read().decode("utf-8", errors="replace").lower()
        if error.code == 404:
            raise HTTPException(404, "GitHub PR or repository not found; check the URL and GITHUB_TOKEN access") from error
        if error.code == 429 or (error.code == 403 and (
            error.headers.get("X-RateLimit-Remaining") == "0"
            or error.headers.get("Retry-After") or "rate limit" in message
        )):
            raise HTTPException(429, "GitHub API rate limit reached; try again later or set GITHUB_TOKEN") from error
        if error.code in (401, 403):
            raise HTTPException(502, "GitHub access denied; check the server's GITHUB_TOKEN and repository permissions") from error
        raise HTTPException(502, "GitHub API request failed; try again later") from error
    except (URLError, OSError, ValueError) as error:
        raise HTTPException(502, "Cannot read GitHub data; check the connection and try again") from error


def _task_type(title):
    # Recognize conventional-commit prefixes and a few common title verbs.
    word = re.match(r"[a-z]+", title.strip().lower())
    word = word.group() if word else ""
    if word in {"feat", "fix", "docs", "test", "refactor", "chore", "build", "ci", "perf", "style", "revert"}:
        return word
    return {"add": "feat", "implement": "feat", "support": "feat", "fixes": "fix",
            "bugfix": "fix", "tests": "test", "document": "docs", "optimize": "perf"}.get(word, "unknown")


def _agent(pr):
    author = (pr.get("user") or {}).get("login", "")
    branch = (pr.get("head") or {}).get("ref", "")
    for marker, name in {"codex": "OpenAI_Codex", "devin": "Devin", "copilot": "Copilot",
                         "cursor": "Cursor", "claude": "Claude_Code"}.items():
        if re.search(rf"(^|[^a-z0-9]){marker}([^a-z0-9]|$)", f"{author} {branch}", re.I):
            return name
    return "unknown"


def get_pull_request(url):
    """Return repository metadata, PR metadata, and all 15 model features."""
    match = PR_URL.fullmatch(url.strip())
    if not match or match[2] in {".", ".."}:
        raise HTTPException(400, "Use a GitHub pull request URL such as https://github.com/owner/repo/pull/12")
    owner, repo, number = match.groups()
    path = f"/repos/{owner}/{repo}"
    pr = _get(f"{path}/pulls/{number}")
    repository = _get(path)
    try:
        count = pr["changed_files"]
        if count > 3000:
            raise HTTPException(422, "PRs with more than 3000 changed files are not supported by GitHub's files API")
        files = []
        for page in range(1, (count + 99) // 100 + 1):
            files.extend(_get(f"{path}/pulls/{number}/files?per_page=100&page={page}"))
        if len(files) != count:
            raise HTTPException(502, "GitHub returned an incomplete file list; try again")
        features = {
            "title_word_count": len((pr.get("title") or "").split()),
            "body_word_count": len((pr.get("body") or "").split()),
            "total_lines_added": pr["additions"],
            "total_lines_deleted": pr["deletions"],
            "total_lines_changed": pr["additions"] + pr["deletions"],
            "total_files_touched": count,
            "files_added": sum(file["status"] == "added" for file in files),
            "files_modified": sum(file["status"] == "modified" for file in files),
            "files_deleted": sum(file["status"] == "removed" for file in files),
            "total_commits": pr["commits"],
            "stars": repository["stargazers_count"],
            "forks": repository["forks_count"],
            "language": repository.get("language") or "unknown",
            "agent": _agent(pr),
            "task_type": _task_type(pr.get("title") or ""),
        }
        # These fields are present in normal GitHub responses. The fallbacks
        # keep the small adapter usable with compatible GitHub proxies too.
        repository.setdefault("owner", {}).setdefault("login", owner)
        repository.setdefault("name", repo)
        repository.setdefault("html_url", f"https://github.com/{owner}/{repo}")
        pr.setdefault("number", int(number))
        pr.setdefault("html_url", url.strip())
        pr.setdefault("title", f"Pull request #{number}")
        pr.setdefault("state", "open")
    except (KeyError, TypeError, ValueError, AttributeError) as error:
        raise HTTPException(502, "GitHub returned incomplete PR data; try again") from error
    return repository, pr, features
