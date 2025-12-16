#!/usr/bin/env python3
import os, sys, json, urllib.request, urllib.error
from datetime import datetime, timezone

USER = (os.getenv("GITHUB_REPOSITORY") or "texxasrulez/texxasrulez").split("/")[0]
TOKEN = os.getenv("GITHUB_TOKEN", "")
README_PATH = os.getenv("README_PATH", "README.md")
START, END = "<!--ACTIVITY:START-->", "<!--ACTIVITY:END-->"
MAX_ITEMS = int(os.getenv("ACTIVITY_MAX_ITEMS", "10"))

def http_json(url: str):
    headers = {"User-Agent": "profile-activity"}
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))

def fetch_events(user: str):
    # public events only; fine for a profile README
    url = f"https://api.github.com/users/{user}/events/public?per_page=50"
    try:
        return http_json(url)
    except Exception as e:
        print(f"activity fetch error: {e}", file=sys.stderr)
        return []

def fmt_event(e):
    t = e.get("type", "")
    repo = e.get("repo", {}).get("name", "")
    created = e.get("created_at", "")
    when = created.replace("T", " ").replace("Z", " UTC")
    # A few friendly mappings
    if t == "PushEvent":
        payload = e.get("payload", {})
        n = payload.get("size")
        if n is None:
            n = len(payload.get("commits", []))
        if n is None:
            n = 0
        branch = payload.get("ref", "")
        if branch.startswith("refs/heads/"):
            branch = branch.split("/", 2)[-1]
        branch_part = f" on `{branch}`" if branch else ""
        return f"- ⬆️ Pushed {n} commit(s){branch_part} to **{repo}** · {when}"
    if t == "CreateEvent":
        ref = e.get("payload", {}).get("ref_type", "")
        name = e.get("payload", {}).get("ref", "") or ""
        what = f"{ref} {name}" if name else ref
        return f"- ✨ Created {what} in **{repo}** · {when}"
    if t == "ReleaseEvent":
        rel = e.get("payload", {}).get("release", {})
        tag = rel.get("tag_name") or rel.get("name") or ""
        return f"- 🏷️ Published release **{tag}** in **{repo}** · {when}"
    if t == "IssuesEvent":
        act = e.get("payload", {}).get("action", "")
        num = e.get("payload", {}).get("issue", {}).get("number", 0)
        return f"- 🐛 {act.capitalize()} issue #{num} in **{repo}** · {when}"
    if t == "PullRequestEvent":
        act = e.get("payload", {}).get("action", "")
        num = e.get("payload", {}).get("number", 0)
        return f"- 🔀 {act.capitalize()} PR #{num} in **{repo}** · {when}"
    # fallback
    return f"- 📌 {t} in **{repo}** · {when}"

def replace_block(content: str, start: str, end: str, inner: str) -> str:
    import re
    pat = __import__("re").compile(rf"({__import__('re').escape(start)})(.*?){__import__('re').escape(end)}", re.DOTALL)
    if not pat.search(content):
        return content
    return pat.sub(rf"\1\n{inner}\n{end}", content)

def main():
    content = open(README_PATH, "r", encoding="utf-8").read()
    events = fetch_events(USER)
    if not events:
        new = "_No recent public activity._"
    else:
        lines = [fmt_event(e) for e in events[:MAX_ITEMS]]
        new = "\n".join(lines)
    content = replace_block(content, START, END, new)
    open(README_PATH, "w", encoding="utf-8").write(content)
    print("Recent activity updated.")

if __name__ == "__main__":
    main()
