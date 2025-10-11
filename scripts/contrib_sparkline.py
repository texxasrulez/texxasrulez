
#!/usr/bin/env python3
import os, sys, json, urllib.request
from datetime import datetime

OWNER = (os.getenv("GITHUB_REPOSITORY") or "texxasrulez/texxasrulez").split("/")[0]
TOKEN = os.getenv("GITHUB_TOKEN", "")
OUT = os.getenv("SPARKLINE_OUT", "assets/contrib-sparkline.svg")

Q = """
query($login:String!) {
  user(login:$login) {
    contributionsCollection {
      contributionCalendar {
        weeks {
          contributionDays { contributionCount date }
        }
      }
    }
  }
}
"""

def graphql(q, variables):
    body = json.dumps({"query": q, "variables": variables}).encode()
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=body,
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json", "User-Agent": "sparkline"},
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())

def make_svg(values):
    if not values:
        return '<svg xmlns="http://www.w3.org/2000/svg" width="600" height="80"></svg>'
    N = len(values)
    W, H, P = 600, 80, 6  # width, height, padding
    vmax = max(values) or 1
    # points across width, baseline at H-P
    coords = []
    for i, v in enumerate(values):
        x = P + i * (W - 2*P) / max(1, N-1)
        y = H - P - (H - 2*P) * (v / vmax)
        coords.append((x, y))
    path = "M " + " L ".join(f"{x:.1f},{y:.1f}" for x, y in coords)
    # gradient fill under line
    poly = " ".join(f"{x:.1f},{y:.1f}" for x, y in coords) + f" {coords[-1][0]:.1f},{H-P} {coords[0][0]:.1f},{H-P}"
    today = datetime.utcnow().strftime("%Y-%m-%d")
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">
  <defs>
    <linearGradient id="g" x1="0" x2="0" y1="0" y2="1">
      <stop offset="0%" stop-color="#4ea1ff" stop-opacity="0.6"/>
      <stop offset="100%" stop-color="#4ea1ff" stop-opacity="0.05"/>
    </linearGradient>
  </defs>
  <rect width="100%" height="100%" fill="transparent"/>
  <polyline fill="none" stroke="#4ea1ff" stroke-width="2" points="{' '.join(f'{x:.1f},{y:.1f}' for x,y in coords)}"/>
  <polygon points="{poly}" fill="url(#g)"/>
  <text x="{W-P}" y="{H-4}" font-size="10" text-anchor="end" fill="#888">through {today} (UTC)</text>
</svg>'''

def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    data = graphql(Q, {"login": OWNER})
    weeks = (data.get("data", {})
               .get("user", {})
               .get("contributionsCollection", {})
               .get("contributionCalendar", {})
               .get("weeks", []))
    vals = []
    for w in weeks:
        for d in w.get("contributionDays", []):
            vals.append(int(d.get("contributionCount", 0)))
    # last 365 values
    vals = vals[-365:]
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(make_svg(vals))
    print(f"Wrote sparkline to {OUT}")

if __name__ == "__main__":
    if not TOKEN:
        print("Missing GITHUB_TOKEN", file=sys.stderr)
        sys.exit(0)  # don’t fail the build
    main()
