#!/usr/bin/env python3
import json
import os
import re
import sys
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, date
from hashlib import sha1
from typing import List, Tuple

README_PATH = os.getenv("README_PATH", "README.md")
REPO = os.getenv("GITHUB_REPOSITORY", "texxasrulez/texxasrulez")
OWNER = REPO.split("/")[0]
USER = os.getenv("GITHUB_ACTOR", OWNER)
TOKEN = os.getenv("GITHUB_TOKEN", "")

BLOG_RSS_URL = os.getenv("BLOG_RSS_URL", "").strip()
TIPS_FILE = os.getenv("TIPS_FILE", "data/tips.txt")
FEATURED_FILE = os.getenv("FEATURED_FILE", "data/featured_repos.txt")
MAX_RELEASE_REPOS = int(os.getenv("MAX_RELEASE_REPOS", "6"))
MAX_BLOG_ITEMS = int(os.getenv("MAX_BLOG_ITEMS", "5"))

# FEATURED rendering controls
FEATURED_COUNT = max(1, int(os.getenv("FEATURED_COUNT", "2")))  # how many cards to show
FEATURED_LIGHT_THEME = os.getenv("FEATURED_LIGHT_THEME", "default")
FEATURED_DARK_THEME = os.getenv("FEATURED_DARK_THEME", "tokyonight")
FEATURED_ROTATION = os.getenv("FEATURED_ROTATION", "daily").lower()  # daily|weekly|monthly
FEATURED_SEED = os.getenv("FEATURED_SEED", "featured")  # optional salt to reshuffle schedule

# Markers
QUOTE_S, QUOTE_E = "<!--QUOTE:START-->", "<!--QUOTE:END-->"
STREAK_S, STREAK_E = "<!--STREAKS:START-->", "<!--STREAKS:END-->"
DATE_S, DATE_E = "<!--DATE:START-->", "<!--DATE:END-->"
TIP_S, TIP_E = "<!--TIP:START-->", "<!--TIP:END-->"
REL_S, REL_E = "<!--RELEASES:START-->", "<!--RELEASES:END-->"
FEAT_S, FEAT_E = "<!--FEATURED:START-->", "<!--FEATURED:END-->"
BLOG_S, BLOG_E = "<!--BLOG:START-->", "<!--BLOG:END-->"


def read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def write_text(path: str, content: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def replace_block(content: str, start_marker: str, end_marker: str, new_inner: str) -> str:
    pattern = re.compile(rf"({re.escape(start_marker)})(.*?){re.escape(end_marker)}", re.DOTALL)
    if not pattern.search(content):
        # If markers missing, do nothing (safer for profile READMEs)
        return content
    return pattern.sub(rf"\1\n{new_inner}\n{end_marker}", content)


def http_json(url: str, headers: dict | None = None, timeout: int = 15):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read().decode("utf-8", errors="replace")
    return json.loads(data)


def gh_rest(url_path: str):
    if not TOKEN:
        raise RuntimeError("Missing GITHUB_TOKEN for GitHub API.")
    url = f"https://api.github.com{url_path}"
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "profile-updater",
    }
    return http_json(url, headers=headers)


def gh_graphql(query: str, variables: dict | None = None):
    if not TOKEN:
        raise RuntimeError("Missing GITHUB_TOKEN for GraphQL.")
    body = json.dumps({"query": query, "variables": variables or {}}).encode("utf-8")
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=body,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": "profile-updater",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def fetch_quote_md() -> str:
    url = "https://zenquotes.io/api/random"
    try:
        data = http_json(url, timeout=10)
        if isinstance(data, list) and data:
            q = (data[0].get("q") or "").strip()
            a = (data[0].get("a") or "").strip()
            if q and a:
                return f"> “{q}”\n— <em>{a}</em>"
            if q:
                return f"> “{q}”"
    except Exception:
        pass
    return "> “Perfect is the enemy of shipped.”\n— <em>Pragmatic Bot</em>"


def calc_streaks(weeks) -> Tuple[int, int]:
    days = []
    for w in weeks:
        for d in w.get("contributionDays", []):
            days.append(d.get("contributionCount", 0) > 0)
    longest = running = 0
    for active in days:
        running = running + 1 if active else 0
        longest = max(longest, running)
    current = 0
    for active in reversed(days):
        if active:
            current += 1
        else:
            break
    return current, longest


def fetch_streaks_md(username: str) -> str:
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
        weeks = (
            data.get("data", {})
            .get("user", {})
            .get("contributionsCollection", {})
            .get("contributionCalendar", {})
            .get("weeks", [])
        )
        cur, longest = calc_streaks(weeks) if weeks else (0, 0)
        return f"Current Streak: {cur} days  \nLongest Streak: {longest} days"
    except Exception:
        return "Current Streak: 0 days  \nLongest Streak: 0 days"


def rotation_key() -> str:
    """Return a period key that changes per FEATURED_ROTATION."""
    today = datetime.now(timezone.utc).date()
    if FEATURED_ROTATION == "weekly":
        y, w, _ = today.isocalendar()
        return f"{y}-W{w}"
    if FEATURED_ROTATION == "monthly":
        return f"{today:%Y-%m}"
    # default: daily
    return f"{today:%Y-%j}"  # year + day-of-year


def deterministic_shuffle(items: List[str], key: str, seed: str) -> List[str]:
    """Stable 'shuffle': sort by sha1(key + seed + item)."""
    return sorted(items, key=lambda it: sha1(f"{key}::{seed}::{it}".encode()).digest())


def _pin_card(owner: str, repo: str) -> str:
    """Theme-aware pin card HTML using <picture>, matching your style."""
    light = f"https://github-readme-stats.vercel.app/api/pin/?username={owner}&repo={repo}&theme={FEATURED_LIGHT_THEME}"
    dark = f"https://github-readme-stats.vercel.app/api/pin/?username={owner}&repo={repo}&theme={FEATURED_DARK_THEME}"
    return (
        f'<a href="https://github.com/{owner}/{repo}">\n'
        f'  <picture>\n'
        f'    <source media="(prefers-color-scheme: dark)" srcset="{dark}">\n'
        f'    <img src="{light}" alt="{repo}" />\n'
        f'  </picture>\n'
        f'</a>'
    )


def load_lines(path: str) -> List[str]:
    try:
        return [ln.strip() for ln in read_text(path).splitlines() if ln.strip() and not ln.strip().startswith("#")]
    except FileNotFoundError:
        return []


def fetch_featured_md() -> str:
    repos = load_lines(FEATURED_FILE)
    if not repos:
        return "_Add repositories to `data/featured_repos.txt` to enable rotation._"

    # Deterministic daily/weekly/monthly shuffle; then take first N
    key = rotation_key()
    shuffled = deterministic_shuffle(repos, key, FEATURED_SEED)
    chosen = shuffled[:FEATURED_COUNT]

    cards = []
    for full in chosen:
        try:
            owner, repo = full.split("/", 1)
        except ValueError:
            continue
        cards.append(_pin_card(owner, repo))

    if not cards:
        return "_No valid repositories listed in `data/featured_repos.txt`._"

    return '<p align="center">\n' + "\n".join(cards) + "\n</p>"


def fetch_tip_md() -> str:
    tips = load_lines(TIPS_FILE)
    if not tips:
        return "_Add tips to `data/tips.txt` to enable tips._"
    key = rotation_key()
    # rotate within tips too
    idx = int.from_bytes(sha1(f"{key}::{FEATURED_SEED}::tips".encode()).digest()[:2], "big") % len(tips)
    return tips[idx]


def fetch_release_stats_md(owner: str) -> str:
    """Aggregate release asset downloads for recent repos."""
    try:
        repos = gh_rest(f"/users/{owner}/repos?per_page=100&type=owner&sort=updated")
    except Exception:
        return "_Release stats unavailable (API error)._"

    rows = []
    checked = 0
    for r in repos:
        if checked >= MAX_RELEASE_REPOS:
            break
        if r.get("archived") or r.get("disabled"):
            continue
        name = r.get("name")
        full = r.get("full_name", "").lower()
        if full == f"{owner}/{owner}".lower():  # skip profile repo
            continue
        try:
            rels = gh_rest(f"/repos/{owner}/{name}/releases?per_page=10")
        except Exception:
            continue
        total = 0
        latest_tag = ""
        for rel in rels:
            latest_tag = latest_tag or (rel.get("tag_name") or rel.get("name") or "")
            for asset in rel.get("assets", []):
                total += int(asset.get("download_count", 0))
        if total > 0:
            rows.append((name, total, latest_tag))
        checked += 1

    if not rows:
        return "_No release downloads found across recent repositories._"

    rows.sort(key=lambda x: x[1], reverse=True)
    md = "| Repo | Downloads | Latest Tag |\n|---|---:|---|\n"
    for name, total, tag in rows[:10]:
        md += f"| [{name}](https://github.com/{owner}/{name}/releases) | {total:,} | {tag or '—'} |\n"
    return md.strip()


def fetch_blog_md() -> str:
    if not BLOG_RSS_URL:
        return "Add `BLOG_RSS_URL` to enable blog posts."
    try:
        req = urllib.request.Request(BLOG_RSS_URL, headers={"User-Agent": "profile-updater"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            xml = resp.read()
        root = ET.fromstring(xml)
        items = []
        # RSS 2.0
        for itm in root.findall(".//item"):
            title = (itm.findtext("title") or "").strip()
            link = (itm.findtext("link") or "").strip()
            if title and link:
                items.append((title, link))
        # Atom
        if not items:
            for entry in root.findall(".//{http://www.w3.org/2005/Atom}entry"):
                title = (entry.findtext("{http://www.w3.org/2005/Atom}title") or "").strip()
                link_el = entry.find("{http://www.w3.org/2005/Atom}link")
                href = link_el.get("href") if link_el is not None else ""
                if title and href:
                    items.append((title, href))
        if not items:
            return "_No posts found in RSS feed._"
        items = items[:MAX_BLOG_ITEMS]
        return "\n".join(f"- [{t}]({u})" for t, u in items)
    except Exception:
        return "_Blog feed fetch failed. Check `BLOG_RSS_URL`._"


def main():
    try:
        content = read_text(README_PATH)

        # Date
        now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S %Z")
        content = replace_block(content, DATE_S, DATE_E, now_utc)

        # Quote
        content = replace_block(content, QUOTE_S, QUOTE_E, fetch_quote_md())

        # Streaks (use OWNER; fallback to USER)
        streak_user = OWNER or USER
        content = replace_block(content, STREAK_S, STREAK_E, fetch_streaks_md(streak_user))

        # Tip of the Day
        content = replace_block(content, TIP_S, TIP_E, fetch_tip_md())

        # Featured rotating (deterministic shuffle per rotation period)
        content = replace_block(content, FEAT_S, FEAT_E, fetch_featured_md())

        # Release stats
        content = replace_block(content, REL_S, REL_E, fetch_release_stats_md(OWNER))

        # Blog posts
        content = replace_block(content, BLOG_S, BLOG_E, fetch_blog_md())

        write_text(README_PATH, content)
        print("README updated successfully.")
    except Exception as e:
        print(f"Updater error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
