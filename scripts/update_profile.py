#!/usr/bin/env python3
import json
import os
import re
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone

README_PATH = os.getenv("README_PATH", "README.md")
GITHUB_REPO = os.getenv("GITHUB_REPOSITORY", "")  # e.g., "texxasrulez/texxasrulez"
GITHUB_USER = (GITHUB_REPO.split("/", 1)[0] if "/" in GITHUB_REPO else os.getenv("GITHUB_ACTOR", "texxasrulez"))
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")

QUOTE_START = r"<!--QUOTE:START-->"
QUOTE_END = r"<!--QUOTE:END-->"
STREAKS_START = r"<!--STREAKS:START-->"
STREAKS_END = r"<!--STREAKS:END-->"
DATE_START = r"<!--DATE:START-->"
DATE_END = r"<!--DATE:END-->"

def read_file(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

def write_file(path: str, content: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

def replace_block(content: str, start_marker: str, end_marker: str, new_inner: str) -> str:
    pattern = re.compile(
        rf"({re.escape(start_marker)})(.*?){re.escape(end_marker)}",
        flags=re.DOTALL
    )
    if not pattern.search(content):
        # If markers missing, append a safe block at the end
        return content + f"\n{start_marker}\n{new_inner}\n{end_marker}\n"
    return pattern.sub(rf"\1\n{new_inner}\n{end_marker}", content)

def fetch_quote() -> str:
    """Fetch quote from ZenQuotes (no external deps). Provide graceful fallback."""
    url = "https://zenquotes.io/api/random"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
            if isinstance(data, list) and data:
                q = data[0].get("q", "").strip()
                a = data[0].get("a", "").strip()
                if q and a:
                    return f"> “{q}”\n— <em>{a}</em>"
                if q:
                    return f"> “{q}”"
    except Exception:
        # Silent fallback below
        pass
    return "> “Perfect is the enemy of shipped.”\n— <em>Pragmatic Bot</em>"

def gh_graphql(query: str, variables: dict = None) -> dict:
    if not GITHUB_TOKEN:
        raise RuntimeError("GITHUB_TOKEN not available in env for GraphQL call.")
    req = urllib.request.Request("https://api.github.com/graphql",
                                 data=json.dumps({"query": query, "variables": variables or {}}).encode("utf-8"),
                                 headers={
                                     "Authorization": f"Bearer {GITHUB_TOKEN}",
                                     "Content-Type": "application/json",
                                     "User-Agent": "profile-updater"
                                 })
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))

def calc_streaks(contrib_weeks) -> tuple[int, int]:
    """Return (current_streak, longest_streak) based on last 365 days contribution calendar."""
    days = []
    for w in contrib_weeks:
        for d in w.get("contributionDays", []):
            count = d.get("contributionCount", 0)
            days.append(count > 0)
    # Ensure chronological order (API returns chronological weeks; days inside are chronological)
    # current streak: count from end while True
    longest = 0
    current = 0
    running = 0
    for active in days:
        if active:
            running += 1
            if running > longest:
                longest = running
        else:
            running = 0
    # Current streak counts from the end backwards
    for active in reversed(days):
        if active:
            current += 1
        else:
            break
    return current, longest

def fetch_streaks(username: str) -> tuple[int, int]:
    query = """
    query($login: String!) {
      user(login: $login) {
        contributionsCollection {
          contributionCalendar {
            weeks {
              contributionDays {
                date
                contributionCount
              }
            }
          }
        }
      }
    }"""
    try:
        data = gh_graphql(query, {"login": username})
        weeks = (data.get("data", {})
                    .get("user", {})
                    .get("contributionsCollection", {})
                    .get("contributionCalendar", {})
                    .get("weeks", []))
        if not weeks:
            return (0, 0)
        return calc_streaks(weeks)
    except Exception:
        return (0, 0)

def update_readme():
    content = read_file(README_PATH)

    # Update date block (UTC)
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S %Z")
    content = replace_block(content, DATE_START, DATE_END, now_utc)

    # Update quote block
    quote_md = fetch_quote()
    content = replace_block(content, QUOTE_START, QUOTE_END, quote_md)

    # Update streaks block
    current, longest = fetch_streaks(GITHUB_USER)
    streaks_md = f"Current Streak: {current} days  \nLongest Streak: {longest} days"
    content = replace_block(content, STREAKS_START, STREAKS_END, streaks_md)

    write_file(README_PATH, content)

if __name__ == "__main__":
    try:
        update_readme()
        print("README updated successfully.")
    except Exception as e:
        print(f"Updater error: {e}", file=sys.stderr)
        sys.exit(1)
