"""Generate GitHub stats and top-language SVG cards for the profile README.

Runs in GitHub Actions (see .github/workflows/stats.yml) using only the
standard library. Needs GITHUB_TOKEN and USERNAME environment variables.
"""

import json
import os
import urllib.request
from html import escape

USERNAME = os.environ.get("USERNAME", "AdriaanBoshoff")
TOKEN = os.environ["GITHUB_TOKEN"]
OUT_DIR = os.environ.get("OUT_DIR", "assets")

QUERY = """
query($login: String!, $cursor: String) {
  user(login: $login) {
    name
    followers { totalCount }
    contributionsCollection {
      totalCommitContributions
      restrictedContributionsCount
      totalPullRequestContributions
      totalIssueContributions
    }
    repositories(first: 100, after: $cursor, ownerAffiliations: OWNER,
                 isFork: false, privacy: PUBLIC) {
      totalCount
      pageInfo { hasNextPage endCursor }
      nodes {
        stargazerCount
        forkCount
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name color } }
        }
      }
    }
  }
}
"""


def gql(variables):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": variables}).encode(),
        headers={"Authorization": f"bearer {TOKEN}", "User-Agent": "profile-stats"},
    )
    with urllib.request.urlopen(req) as resp:
        body = json.load(resp)
    if "errors" in body:
        raise SystemExit(f"GraphQL error: {body['errors']}")
    return body["data"]["user"]


def collect():
    cursor, user, repos = None, None, []
    while True:
        page = gql({"login": USERNAME, "cursor": cursor})
        user = user or page
        repos.extend(page["repositories"]["nodes"])
        info = page["repositories"]["pageInfo"]
        if not info["hasNextPage"]:
            break
        cursor = info["endCursor"]

    langs = {}
    for repo in repos:
        for edge in repo["languages"]["edges"]:
            name = edge["node"]["name"]
            entry = langs.setdefault(name, {"size": 0, "color": edge["node"]["color"] or "#8b949e"})
            entry["size"] += edge["size"]

    cc = user["contributionsCollection"]
    stats = {
        "Total stars": sum(r["stargazerCount"] for r in repos),
        "Total forks": sum(r["forkCount"] for r in repos),
        "Public repositories": user["repositories"]["totalCount"],
        "Commits (last year)": cc["totalCommitContributions"] + cc["restrictedContributionsCount"],
        "Pull requests (last year)": cc["totalPullRequestContributions"],
        "Followers": user["followers"]["totalCount"],
    }
    return stats, langs


# Colours adapt to the viewer's light/dark GitHub theme.
STYLE = """
<style>
  .bg { fill: #ffffff; stroke: #d0d7de; }
  .title { fill: #0969da; font: 600 17px 'Segoe UI', Ubuntu, sans-serif; }
  .label { fill: #57606a; font: 400 13px 'Segoe UI', Ubuntu, sans-serif; }
  .value { fill: #1f2328; font: 600 13px 'Segoe UI', Ubuntu, sans-serif; }
  .track { fill: #eaeef2; }
  @media (prefers-color-scheme: dark) {
    .bg { fill: #0d1117; stroke: #30363d; }
    .title { fill: #58a6ff; }
    .label { fill: #8b949e; }
    .value { fill: #e6edf3; }
    .track { fill: #21262d; }
  }
</style>
"""


def stats_svg(stats):
    w, row_h, top = 400, 26, 58
    h = top + row_h * len(stats) + 10
    rows = []
    for i, (label, value) in enumerate(stats.items()):
        y = top + i * row_h
        rows.append(
            f'<text class="label" x="25" y="{y}">{escape(label)}</text>'
            f'<text class="value" x="{w - 25}" y="{y}" text-anchor="end">{value:,}</text>'
        )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
        f"{STYLE}"
        f'<rect class="bg" x="0.5" y="0.5" rx="6" width="{w - 1}" height="{h - 1}"/>'
        f'<text class="title" x="25" y="32">GitHub stats</text>'
        + "".join(rows)
        + "</svg>"
    )


def langs_svg(langs, count=6):
    top_langs = sorted(langs.items(), key=lambda kv: kv[1]["size"], reverse=True)[:count]
    total = sum(v["size"] for _, v in top_langs) or 1
    w, bar_w = 360, 310
    h = 78 + 24 * ((len(top_langs) + 1) // 2)

    # Stacked bar
    bar, x = [], 25.0
    for name, v in top_langs:
        width = bar_w * v["size"] / total
        bar.append(f'<rect x="{x:.2f}" y="48" width="{width:.2f}" height="8" fill="{v["color"]}"/>')
        x += width

    # Two-column legend
    legend = []
    for i, (name, v) in enumerate(top_langs):
        col, row = i % 2, i // 2
        lx, ly = 25 + col * 165, 82 + row * 24
        pct = 100 * v["size"] / total
        legend.append(
            f'<circle cx="{lx + 5}" cy="{ly - 4}" r="5" fill="{v["color"]}"/>'
            f'<text class="value" x="{lx + 16}" y="{ly}">{escape(name)}</text>'
            f'<text class="label" x="{lx + 150}" y="{ly}" text-anchor="end">{pct:.1f}%</text>'
        )

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
        f"{STYLE}"
        f'<rect class="bg" x="0.5" y="0.5" rx="6" width="{w - 1}" height="{h - 1}"/>'
        f'<text class="title" x="25" y="32">Most used languages</text>'
        f'<clipPath id="r"><rect x="25" y="48" width="{bar_w}" height="8" rx="4"/></clipPath>'
        f'<rect class="track" x="25" y="48" width="{bar_w}" height="8" rx="4"/>'
        f'<g clip-path="url(#r)">{"".join(bar)}</g>'
        + "".join(legend)
        + "</svg>"
    )


def main():
    stats, langs = collect()
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "stats.svg"), "w", encoding="utf-8") as f:
        f.write(stats_svg(stats))
    with open(os.path.join(OUT_DIR, "top-langs.svg"), "w", encoding="utf-8") as f:
        f.write(langs_svg(langs))
    print(json.dumps(stats, indent=2))
    print({k: v["size"] for k, v in sorted(langs.items(), key=lambda kv: -kv[1]["size"])[:6]})


if __name__ == "__main__":
    main()
