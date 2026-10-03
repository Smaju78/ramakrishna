"""Download the Kathamrita scan pages from Bengali Wikisource into cache/wikisource/.

Source: bn.wikisource.org (Safe in source-register.md). Parts 1, 3, 4, 5 exist; Part 2 does not yet.
Each scan page is fetched once (50 per API request, 1 second apart); cached pages are never re-downloaded.
Writes cache/wikisource/<part>.json: {page_number: {"title", "text", "quality"}}.
quality is Wikisource's proofread level: 0 no text, 1 not proofread, 2 problematic, 3 proofread, 4 validated.
"""
import json
import time
from pathlib import Path

import requests

API = "https://bn.wikisource.org/w/api.php"
HEADERS = {"User-Agent": "ramakrishna-song-index/0.1 (personal research)"}
DELAY = 5.0  # Wikisource returned 429 at 1 request/second
OUT = Path(__file__).parent / "cache" / "wikisource"
PARTS = {
    1: "শ্রীশ্রীরামকৃষ্ণ কথামৃত প্রথম ভাগ.djvu",
    3: "শ্রীশ্রীরামকৃষ্ণ কথামৃত তৃতীয় ভাগ.djvu",
    4: "শ্রীশ্রীরামকৃষ্ণ কথামৃত চতুর্থ ভাগ.djvu",
    5: "শ্রীশ্রীরামকৃষ্ণ কথামৃত পঞ্চম ভাগ.djvu",
}
BN_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")


def get(session, params):
    for attempt in (1, 2):
        try:
            # POST: 50 Bengali titles percent-encoded are too long for a GET URL
            r = session.post(API, data={**params, "format": "json", "formatversion": 2},
                             headers=HEADERS, timeout=60)
            r.raise_for_status()
            time.sleep(DELAY)
            return r.json()
        except Exception as e:  # noqa: BLE001
            print(f"  attempt {attempt} failed: {e}")
            # honour the server's Retry-After on 429, else back off a little
            retry = getattr(getattr(e, "response", None), "headers", {}).get("Retry-After", "")
            time.sleep(min(int(retry), 600) if retry.isdigit() else 30)
    raise RuntimeError("request failed twice")


def list_pages(session, filename):
    titles, cont = [], {}
    while True:
        r = get(session, {"action": "query", "list": "allpages", "apnamespace": 104,
                          "apprefix": filename + "/", "aplimit": 500, **cont})
        titles += [p["title"] for p in r["query"]["allpages"]]
        if "continue" not in r:
            return titles
        cont = r["continue"]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    s = requests.Session()
    for part, filename in PARTS.items():
        path = OUT / f"part{part}.json"
        pages = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        titles = list_pages(s, filename)
        todo = [t for t in titles if t.rsplit("/", 1)[1].translate(BN_DIGITS) not in pages]
        print(f"Part {part}: {len(titles)} pages listed, {len(todo)} to download")
        for i in range(0, len(todo), 50):
            batch = todo[i:i + 50]
            r = get(s, {"action": "query", "prop": "revisions|proofread", "rvprop": "content",
                        "rvslots": "main", "titles": "|".join(batch)})
            for p in r["query"]["pages"]:
                if "revisions" not in p:
                    continue
                n = p["title"].rsplit("/", 1)[1].translate(BN_DIGITS)
                pages[n] = {
                    "title": p["title"],
                    "text": p["revisions"][0]["slots"]["main"]["content"],
                    "quality": p.get("proofread", {}).get("quality"),
                }
            # save after every batch so an interrupted run resumes without re-downloading
            path.write_text(json.dumps(pages, ensure_ascii=False, indent=0), encoding="utf-8")
        print(f"  cached {len(pages)} pages")


if __name__ == "__main__":
    main()
