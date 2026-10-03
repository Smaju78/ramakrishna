"""Search YouTube for renditions of the songs used on problem pages.

Reads YOUTUBE_API_KEY from .env (never printed). Searches only songs listed in
data/problems.json, embeddable videos only, and caches results in
cache/youtube/<key>.json so a song is never searched twice (each search costs 100 quota units).
Writes data/youtube_candidates.json for picking; the chosen video goes in data/youtube.csv.
Register: YouTube is "Embed only" — we store video ids and embed; nothing is downloaded.
"""
import hashlib
import json
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).parent
CACHE = ROOT / "cache" / "youtube"
API = "https://www.googleapis.com/youtube/v3/search"
# Extra queries, tried in order when the Bengali first line returns nothing.
ALT_QUERIES = {
    "অভয় পদে প্রাণ সঁপেছি": ["অভয় পদে প্রাণ সঁপেছি শ্যামাসঙ্গীত", "Abhoy pode pran sopechi"],
    "আমি দুর্গা দুর্গা বলে মা যদি মরি": ["আমি দুর্গা দুর্গা বলে মা যদি মরি শ্যামাসঙ্গীত", "Ami Durga Durga bole Ma jodi mori"],
}


def api_key():
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith("YOUTUBE_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    sys.exit("YOUTUBE_API_KEY not found in .env")


def search(key, query):
    path = CACHE / (hashlib.sha1(query.encode()).hexdigest()[:16] + ".json")
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))["items"]
    r = requests.get(API, params={
        "part": "snippet", "q": query, "type": "video", "videoEmbeddable": "true",
        "maxResults": 8, "relevanceLanguage": "bn", "regionCode": "IN", "key": key}, timeout=30)
    if r.status_code != 200:
        # never echo the URL: it contains the key
        sys.exit(f"YouTube API error {r.status_code}: {r.json().get('error', {}).get('message', '')[:200]}")
    items = [{"video_id": it["id"]["videoId"], "title": it["snippet"]["title"],
              "channel": it["snippet"]["channelTitle"], "published": it["snippet"]["publishedAt"][:10]}
             for it in r.json().get("items", [])]
    path.write_text(json.dumps({"query": query, "items": items}, ensure_ascii=False, indent=1), encoding="utf-8")
    time.sleep(1)
    return items


def main():
    CACHE.mkdir(parents=True, exist_ok=True)
    key = api_key()
    catalog = {s["normalized_first_line"]: s for s in json.loads((ROOT / "data" / "catalog.json").read_text(encoding="utf-8"))}
    problems = json.loads((ROOT / "data" / "problems.json").read_text(encoding="utf-8"))
    out = {}
    for p in problems:
        for k in p["songs"]:
            if k in out:
                continue
            s = catalog[k]
            first = s["first_line"].strip("“”‘’ ।॥৷,")
            found = search(key, first)
            for alt in ALT_QUERIES.get(k, []):  # Bengali first line found nothing: try how people title it
                if found:
                    break
                found = search(key, alt)
            out[k] = {"first_line": s["first_line"], "candidates": found}
            print(f"{first[:40]}: {len(out[k]['candidates'])} candidates")
    (ROOT / "data" / "youtube_candidates.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
