# supplement-index-reddit

Read-only Reddit collector for a free iOS reference app about over-the-counter supplements.
This is the complete code that accesses the Reddit Data API.

## What it does

- **Read-only.** Never posts, comments, votes, messages or moderates.
- **Access:** one registered "script" OAuth client. Once a day it reads the `/r/{sub}/new` and
  `/r/{sub}/comments` listings for r/Supplements, r/Nootropics, r/Biohackers, r/longevity, r/sleep and
  r/Fitness, back to 30 days, up to 10 pages each — at most ~120 requests per run, paced at ≤ 55 requests/minute
  and honouring the `X-Ratelimit-*` headers. Descriptive user agent.
- **Processing:** post titles, post bodies and comments are scanned in memory for ~40 supplement names
  (`collector/aliases.json`) and then discarded.
- **Storage:**
  - `counts-YYYY-MM-DD.json` — per-supplement daily totals of matching posts and comments. No Reddit content.
  - `threads.json` — for matching threads only: title, permalink, comment count, score, created time.
    **No usernames, no post or comment text, no images.** Records are deleted after 90 days; threads that are
    deleted/removed on Reddit drop out on the next run.
- **Display:** the app shows an aggregate attention index per supplement next to published research, plus up to
  3 thread titles per supplement linking to the thread on reddit.com. Threads about selling, sourcing or dosing
  and NSFW/locked/removed posts are excluded; users can hide any thread.
- **Not used for** AI/ML training, advertising, user profiling or resale.

## Run

```bash
export REDDIT_CLIENT_ID=... REDDIT_CLIENT_SECRET=... REDDIT_USERNAME=... REDDIT_PASSWORD=...
export REDDIT_USER_AGENT="ios:com.lucasfox.supplements:v0.1 (by /u/<username>)"
python3 -m collector.reddit_collector      # writes to ./output
python3 -m unittest discover tests
```

No third-party dependencies (Python 3.10+ standard library only).

## Contact

Lucas Fox — open an issue on this repository.

## License

MIT
