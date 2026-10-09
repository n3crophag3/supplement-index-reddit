"""Read-only Reddit collector for a supplement attention index.

Once a day: reads recent public posts and comments from a fixed list of subreddits
through the official OAuth Data API, counts mentions of ~40 over-the-counter supplements,
and keeps only aggregate counts plus minimal thread metadata.

Never posts, comments, votes, messages or moderates. Text is scanned in memory and discarded.
Stored per thread: title, permalink, comment count, score, created time. No usernames, no bodies.
"""
from __future__ import annotations

import base64
import json
import os
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

SUBREDDITS = ["Supplements", "Nootropics", "Biohackers", "longevity", "sleep", "Fitness"]
WINDOW_DAYS = 30          # only content from the last 30 days is read
THREAD_RETENTION_DAYS = 90  # thread records older than this are deleted
MAX_PAGES = 10            # per listing, 100 items per page
MIN_INTERVAL_S = 1.1      # <= ~55 requests/minute even before reading rate-limit headers
API = "https://oauth.reddit.com"
EXCLUDE_TITLE = re.compile(
    r"\b(vendor|vendors|source|sourcing|buy|buying|sell|selling|discount|coupon|promo|code|"
    r"dose|dosage|dosing|mg|how much|where to get)\b", re.I)

HERE = Path(__file__).resolve().parent
ALIASES: dict[str, list[str]] = json.loads((HERE / "aliases.json").read_text())


def compile_patterns(aliases: dict[str, list[str]]) -> dict[str, re.Pattern]:
    return {cid: re.compile(r"(?<![\w-])(" + "|".join(re.escape(a) for a in sorted(al, key=len, reverse=True)) + r")(?![\w-])", re.I)
            for cid, al in aliases.items()}


PATTERNS = compile_patterns(ALIASES)


def mentions(text: str, patterns: dict[str, re.Pattern] = PATTERNS) -> set[str]:
    """Supplement ids mentioned in text. The text itself is not kept."""
    return {cid for cid, p in patterns.items() if p.search(text or "")}


def thread_allowed(post: dict) -> bool:
    return not (post.get("over_18") or post.get("removed_by_category") or post.get("locked")
                or post.get("author") == "[deleted]" or EXCLUDE_TITLE.search(post.get("title", "")))


class RedditClient:
    def __init__(self):
        self.ua = os.environ["REDDIT_USER_AGENT"]
        self._token, self._last = self._auth(), 0.0

    def _auth(self) -> str:
        cid, secret = os.environ["REDDIT_CLIENT_ID"], os.environ["REDDIT_CLIENT_SECRET"]
        body = urllib.parse.urlencode({"grant_type": "password", "username": os.environ["REDDIT_USERNAME"],
                                       "password": os.environ["REDDIT_PASSWORD"]}).encode()
        req = urllib.request.Request("https://www.reddit.com/api/v1/access_token", data=body, headers={
            "User-Agent": self.ua, "Authorization": "Basic " + base64.b64encode(f"{cid}:{secret}".encode()).decode()})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)["access_token"]

    def get(self, path: str, **params) -> dict:
        wait = self._last + MIN_INTERVAL_S - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        url = f"{API}{path}?{urllib.parse.urlencode({**params, 'raw_json': 1})}"
        req = urllib.request.Request(url, headers={"User-Agent": self.ua, "Authorization": f"bearer {self._token}"})
        with urllib.request.urlopen(req, timeout=30) as r:
            self._last = time.monotonic()
            remaining = float(r.headers.get("X-Ratelimit-Remaining", 100))
            reset = float(r.headers.get("X-Ratelimit-Reset", 0))
            if remaining < 5:
                time.sleep(reset + 1)
            return json.load(r)

    def listing(self, path: str, since: float):
        after = None
        for _ in range(MAX_PAGES):
            data = self.get(path, limit=100, **({"after": after} if after else {}))["data"]
            for child in data["children"]:
                if child["data"]["created_utc"] < since:
                    return
                yield child["data"]
            after = data.get("after")
            if not after:
                return


def collect(client: RedditClient, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    since = (now - timedelta(days=WINDOW_DAYS)).timestamp()
    counts = {cid: {"posts": 0, "comments": 0} for cid in ALIASES}
    threads = {}
    for sub in SUBREDDITS:
        for post in client.listing(f"/r/{sub}/new", since):
            hit = mentions(post.get("title", "") + "\n" + post.get("selftext", ""))
            for cid in hit:
                counts[cid]["posts"] += 1
            if hit and thread_allowed(post):
                threads[post["id"]] = {"subreddit": sub, "title": post["title"],
                                       "url": "https://www.reddit.com" + post["permalink"],
                                       "num_comments": post["num_comments"], "score": post["score"],
                                       "created_utc": post["created_utc"], "compounds": sorted(hit)}
        for comment in client.listing(f"/r/{sub}/comments", since):
            for cid in mentions(comment.get("body", "")):
                counts[cid]["comments"] += 1
    return {"date": now.strftime("%Y-%m-%d"), "window_days": WINDOW_DAYS, "subreddits": SUBREDDITS,
            "counts": counts, "threads": threads}


def save(result: dict, out_dir: Path, now: datetime | None = None) -> None:
    """Write today's aggregate counts; merge thread metadata; delete expired and missing threads."""
    now = now or datetime.now(timezone.utc)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"counts-{result['date']}.json").write_text(json.dumps(
        {k: result[k] for k in ("date", "window_days", "subreddits", "counts")}, indent=1))
    cutoff = (now - timedelta(days=THREAD_RETENTION_DAYS)).timestamp()
    path = out_dir / "threads.json"
    # Threads not seen in today's window (deleted/removed or aged out) are dropped unless still within retention.
    old = json.loads(path.read_text()) if path.exists() else {}
    window_start = (now - timedelta(days=WINDOW_DAYS)).timestamp()
    kept = {tid: t for tid, t in old.items() if t["created_utc"] >= cutoff and t["created_utc"] < window_start}
    kept.update(result["threads"])
    path.write_text(json.dumps(kept, indent=1))


if __name__ == "__main__":
    save(collect(RedditClient()), Path(os.environ.get("OUT_DIR", "output")))
