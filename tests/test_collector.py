import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from collector import reddit_collector as rc

NOW = datetime(2026, 10, 9, tzinfo=timezone.utc)


def ts(days_ago):
    return (NOW - timedelta(days=days_ago)).timestamp()


class FakeClient:
    def __init__(self, posts, comments):
        self.posts, self.comments = posts, comments

    def listing(self, path, since):
        items = self.posts if path.endswith("/new") else self.comments
        return (i for i in items if i["created_utc"] >= since)


class Tests(unittest.TestCase):
    def test_mentions_word_boundaries(self):
        self.assertEqual(rc.mentions("Creatine before bed?"), {"creatine"})
        self.assertIn("magnesium", rc.mentions("magnesium glycinate vs citrate"))
        self.assertNotIn("nac", rc.mentions("snacks and maniacs"))

    def test_filters(self):
        self.assertFalse(rc.thread_allowed({"title": "Best vendor for creatine?"}))
        self.assertFalse(rc.thread_allowed({"title": "Creatine dose question"}))
        self.assertTrue(rc.thread_allowed({"title": "Creatine and sleep quality"}))

    def test_collect_stores_no_usernames_or_bodies(self):
        post = {"id": "a1", "title": "Creatine and sleep", "selftext": "secret body", "author": "someone",
                "permalink": "/r/Supplements/comments/a1/x/", "num_comments": 12, "score": 40,
                "created_utc": ts(2)}
        comment = {"body": "ashwagandha helped", "author": "x", "created_utc": ts(1)}
        old = dict(post, id="z9", created_utc=ts(45))
        out = rc.collect(FakeClient([post, old], [comment]), now=NOW)
        blob = json.dumps(out)
        self.assertNotIn("someone", blob)
        self.assertNotIn("secret body", blob)
        self.assertEqual(out["counts"]["creatine"]["posts"], len(rc.SUBREDDITS))
        self.assertEqual(out["counts"]["ashwagandha"]["comments"], len(rc.SUBREDDITS))
        self.assertNotIn("z9", out["threads"])

    def test_save_prunes_after_retention(self):
        d = Path(tempfile.mkdtemp())
        (d / "threads.json").write_text(json.dumps({
            "old": {"created_utc": ts(100)}, "aged": {"created_utc": ts(60)}, "gone": {"created_utc": ts(5)}}))
        rc.save({"date": "2026-10-09", "window_days": 30, "subreddits": [], "counts": {}, "threads": {}}, d, now=NOW)
        kept = json.loads((d / "threads.json").read_text())
        self.assertEqual(set(kept), {"aged"})  # >90d deleted; in-window but not re-seen (deleted on Reddit) dropped


if __name__ == "__main__":
    unittest.main()
