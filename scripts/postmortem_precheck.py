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


def run_git(args: List[str]) -> str:
    result = subprocess.run(
        ["git"] + args,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return result.stdout.strip()


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

    def generate_text(self, prompt: str, max_tokens: int = 900) -> str:
        url = f"{self.api_base}/chat/completions"
        messages = [
            {
                "role": "system",
                "content": (
                    "Return only valid JSON. Do not include markdown or extra text."
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


def safe_json_from_text(text: str) -> Optional[Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE | re.DOTALL).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    def try_parse_substring(start: int, opening: str, closing: str) -> Optional[Any]:
        depth = 0
        for idx in range(start, len(text)):
            ch = text[idx]
            if ch == opening:
                depth += 1
            elif ch == closing:
                depth -= 1
                if depth == 0:
                    snippet = text[start : idx + 1]
                    try:
                        return json.loads(snippet)
                    except json.JSONDecodeError:
                        return None
        return None

    for idx, ch in enumerate(text):
        if ch == "{":
            parsed = try_parse_substring(idx, "{", "}")
            if parsed is not None:
                return parsed
        elif ch == "[":
            parsed = try_parse_substring(idx, "[", "]")
            if parsed is not None:
                return parsed

    return None


def previous_tag(current_tag: str) -> Optional[str]:
    tags_raw = run_git(["tag", "--sort=creatordate"]) if current_tag else ""
    tags = [t for t in tags_raw.splitlines() if t.strip()]
    if current_tag not in tags:
        return None
    idx = tags.index(current_tag)
    if idx == 0:
        return None
    return tags[idx - 1]


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


def commit_summary(commit: str) -> str:
    subject = run_git(["show", "-s", "--format=%s", commit])
    files = run_git(["show", "--name-only", "--pretty=format:", commit])
    files = "\n".join([line for line in files.splitlines() if line.strip()][:15])
    return f"{commit[:7]} {subject}\nFiles:\n{files}"


def load_postmortems(path: str, max_files: int) -> List[Tuple[str, str]]:
    if not os.path.isdir(path):
        return []
    files = [f for f in os.listdir(path) if f.endswith(".md")]
    files = [f for f in files if not f.startswith("precheck_")]
    files.sort()
    result = []
    for name in files[:max_files]:
        full_path = os.path.join(path, name)
        with open(full_path, "r", encoding="utf-8") as f:
            content = f.read().strip()
        snippet = "\n".join(content.splitlines()[:80])
        result.append((name, snippet))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Pre-release postmortem trigger check")
    parser.add_argument("--postmortem-dir", default="postmortem")
    parser.add_argument("--since")
    parser.add_argument("--until", default="HEAD")
    parser.add_argument("--tag")
    parser.add_argument("--max-commits", type=int, default=50)
    parser.add_argument("--max-postmortems", type=int, default=50)
    parser.add_argument("--output")
    parser.add_argument("--fail-on-trigger", action="store_true")
    args = parser.parse_args()

    load_env_file()

    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        print("DEEPSEEK_API_KEY is missing", file=sys.stderr)
        return 1
    model = os.getenv("DEEPSEEK_MODEL", DEFAULT_MODEL)
    api_base = os.getenv("DEEPSEEK_API_BASE", DEFAULT_API_BASE)
    client = DeepSeekClient(api_key=api_key, model=model, api_base=api_base)

    since = args.since
    until = args.until
    if args.tag:
        until = args.tag
        since = previous_tag(args.tag)

    range_expr = f"{since}..{until}" if since else until
    commits = get_commits(range_expr)
    commit_summaries = [commit_summary(c[0]) for c in commits[: args.max_commits]]

    postmortems = load_postmortems(args.postmortem_dir, args.max_postmortems)

    prompt = f"""
You are checking whether new commits might re-trigger past postmortems.

Postmortems:
"""
    for name, snippet in postmortems:
        prompt += f"\n### {name}\n{snippet}\n"

    prompt += "\nRelease commits:\n" + "\n\n".join(commit_summaries)
    prompt += """

Return strict JSON with keys:
- triggered: array of {postmortem_file, commit, reason}
- summary: short string
If no risk, return an empty triggered array.
"""

    raw = client.generate_text(textwrap.dedent(prompt).strip())
    parsed = safe_json_from_text(raw)
    if not isinstance(parsed, dict):
        print("LLM output is not JSON", file=sys.stderr)
        return 2
    triggered = parsed.get("triggered", [])
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(parsed, f, ensure_ascii=False, indent=2)
    else:
        print(json.dumps(parsed, ensure_ascii=False, indent=2))

    if args.fail_on_trigger and isinstance(triggered, list) and len(triggered) > 0:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
