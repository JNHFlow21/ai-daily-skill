#!/usr/bin/env python3
import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import textwrap
import time
from typing import Any, Dict, List, Optional, Tuple

import requests

TIMEOUT_SECS = 30
DEFAULT_MODEL = "deepseek-chat"
DEFAULT_API_BASE = "https://api.deepseek.com"

FIX_KEYWORDS = [
    "fix", "fixed", "fixes", "bug", "bugs", "hotfix", "patch", "regression", "repair", "resolve", "resolved",
]


def run_git(args: List[str]) -> str:
    result = subprocess.run(
        ["git"] + args,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return result.stdout.strip()


def slugify(text: str, max_len: int = 48) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return slug[:max_len] if slug else "postmortem"


def is_fix_commit(subject: str, body: str) -> bool:
    text = f"{subject}\n{body}".lower()
    return any(re.search(rf"\b{re.escape(word)}\b", text) for word in FIX_KEYWORDS)


def load_env_file(path: str = ".env") -> None:
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


class DeepSeekClient:
    def __init__(self, api_key: str, model: str, api_base: Optional[str] = None) -> None:
        self.api_key = api_key
        self.model = model
        self.api_base = api_base or DEFAULT_API_BASE

    def generate_text(self, prompt: str, max_tokens: int = 1200) -> str:
        url = f"{self.api_base}/chat/completions"
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a senior software engineer. Return only Markdown text, no code fences. "
                    "Be concise, factual, and professional."
                ),
            },
            {"role": "user", "content": prompt},
        ]
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.2,
            "max_tokens": max_tokens,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        last_error: Optional[Exception] = None
        for attempt in range(5):
            try:
                response = requests.post(
                    url,
                    headers=headers,
                    data=json.dumps(payload),
                    timeout=TIMEOUT_SECS,
                )
                if response.status_code in (429, 500, 503):
                    raise requests.HTTPError(
                        f"DeepSeek status {response.status_code}", response=response
                    )
                response.raise_for_status()
                data = response.json()
                choices = data.get("choices", [])
                if not choices:
                    raise RuntimeError("DeepSeek returned no choices")
                content = choices[0].get("message", {}).get("content", "")
                if not content:
                    raise RuntimeError("DeepSeek returned empty content")
                return str(content).strip()
            except requests.HTTPError as exc:
                last_error = exc
                if getattr(exc.response, "status_code", None) in (429, 500, 503):
                    retry_after = None
                    if exc.response is not None:
                        retry_after = exc.response.headers.get("Retry-After")
                    if retry_after and retry_after.isdigit():
                        time.sleep(int(retry_after))
                    else:
                        time.sleep(min(2 ** attempt, 10))
                    continue
                raise
            except Exception as exc:
                last_error = exc
                time.sleep(min(2 ** attempt, 10))
        if last_error:
            raise RuntimeError(f"DeepSeek failed after retries: {last_error}") from last_error
        raise RuntimeError("DeepSeek failed without error")


def get_commits(range_expr: Optional[str]) -> List[Tuple[str, str, str, str]]:
    fmt = "%H%x1f%ad%x1f%s%x1f%b%x1e"
    args = ["log", "--date=iso-strict", f"--pretty=format:{fmt}"]
    if range_expr:
        args.insert(1, range_expr)
    raw = run_git(args)
    commits = []
    for record in raw.split("\x1e"):
        if not record.strip():
            continue
        parts = record.strip().split("\x1f")
        if len(parts) < 4:
            continue
        commits.append((parts[0], parts[1], parts[2], parts[3]))
    return commits


def commit_details(commit: str) -> Dict[str, str]:
    subject = run_git(["show", "-s", "--format=%s", commit])
    body = run_git(["show", "-s", "--format=%b", commit])
    files = run_git(["show", "--name-only", "--pretty=format:", commit])
    diffstat = run_git(["show", "--stat", "--pretty=format:", commit])
    patch = run_git(["show", "--unified=3", "--pretty=format:", commit])
    patch_lines = patch.splitlines()[:200]
    patch_trimmed = "\n".join(patch_lines)
    return {
        "subject": subject,
        "body": body,
        "files": files,
        "diffstat": diffstat,
        "patch": patch_trimmed,
    }


def prompt_for_commit(commit: str, date: str, details: Dict[str, str]) -> str:
    template = f"""
Create a software incident postmortem based only on the commit context.

Commit: {commit}
Date: {date}
Subject: {details['subject']}
Body: {details['body']}
Files changed:\n{details['files']}
Diffstat:\n{details['diffstat']}
Patch (truncated):\n{details['patch']}

Output Markdown with these sections:
- Summary (1-2 sentences)
- Impact
- Root Cause
- Trigger
- Detection
- Resolution
- Prevention / Follow-ups (bullets)
- Tests / Verification

Do not invent facts beyond the commit context. If unknown, say "Unknown".
"""
    return textwrap.dedent(template).strip()


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def previous_tag(current_tag: str) -> Optional[str]:
    tags_raw = run_git(["tag", "--sort=creatordate"]) if current_tag else ""
    tags = [t for t in tags_raw.splitlines() if t.strip()]
    if current_tag not in tags:
        return None
    idx = tags.index(current_tag)
    if idx == 0:
        return None
    return tags[idx - 1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate postmortem reports for fix commits")
    parser.add_argument("--output-dir", default="postmortem")
    parser.add_argument("--all-fixes", action="store_true")
    parser.add_argument("--since")
    parser.add_argument("--until", default="HEAD")
    parser.add_argument("--tag")
    parser.add_argument("--max-commits", type=int, default=50)
    args = parser.parse_args()

    load_env_file()

    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        print("DEEPSEEK_API_KEY is missing", file=sys.stderr)
        return 1
    model = os.getenv("DEEPSEEK_MODEL", DEFAULT_MODEL)
    api_base = os.getenv("DEEPSEEK_API_BASE", DEFAULT_API_BASE)
    client = DeepSeekClient(api_key=api_key, model=model, api_base=api_base)

    range_expr = None
    if args.all_fixes:
        range_expr = None
    else:
        since = args.since
        until = args.until
        if args.tag:
            until = args.tag
            since = previous_tag(args.tag)
        if since:
            range_expr = f"{since}..{until}"
        else:
            range_expr = until

    commits = get_commits(range_expr)
    fix_commits = [c for c in commits if is_fix_commit(c[2], c[3])]
    if args.max_commits:
        fix_commits = fix_commits[: args.max_commits]

    ensure_dir(args.output_dir)
    generated = 0
    for commit, date, subject, body in fix_commits:
        short_sha = commit[:7]
        filename = f"{dt.datetime.fromisoformat(date).strftime('%Y%m%d')}_{short_sha}_{slugify(subject)}.md"
        path = os.path.join(args.output_dir, filename)
        if os.path.exists(path):
            continue
        details = commit_details(commit)
        prompt = prompt_for_commit(commit, date, details)
        try:
            content = client.generate_text(prompt)
        except Exception as exc:
            print(f"LLM failed for {short_sha}: {exc}", file=sys.stderr)
            continue
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"# Postmortem: {details['subject']}\n\n")
            f.write(content.strip())
            f.write("\n")
        generated += 1

    print(f"Generated {generated} postmortem files in {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
