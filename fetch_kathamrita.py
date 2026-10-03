"""Download Kathamrita section pages into cache/.

Source: ramakrishnavivekananda.info (the only allowed source for this step).
Each page is fetched once; cached pages are never re-downloaded.
Writes cache/sections.json: the ordered list of sections from the contents page.
"""
import html
import json
import re
import time
from pathlib import Path

import requests

BASE = "https://www.ramakrishnavivekananda.info/kathamrita/unicodekathamrita/"
CONTENTS = "kathamrita_contents.html"
SKIP_CHAPTERS = {61, 62, 63, 64}  # appendices
CACHE = Path(__file__).parent / "cache"
HEADERS = {"User-Agent": "ramakrishna-song-index/0.1 (personal research)"}
DELAY = 1.0

BN_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")


def bn_to_int(s):
    return int(s.translate(BN_DIGITS))


def clean(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s)).strip()


def fetch(name, session):
    """Return page text, downloading only if not cached. Returns (text, downloaded)."""
    path = CACHE / name
    if path.exists():
        return path.read_bytes(), False
    r = session.get(BASE + name, headers=HEADERS, timeout=60)
    r.raise_for_status()
    path.write_bytes(r.content)
    time.sleep(DELAY)
    return r.content, True


def decode(raw):
    # Pages declare iso-8859-1 but Bengali is stored as numeric entities.
    return html.unescape(raw.decode("utf-8", errors="replace") if b"charset=utf-8" in raw[:2000].lower()
                         else raw.decode("latin-1"))


def parse_contents(text):
    sections = []
    for tab in re.split(r'<div class="tab">', text)[1:]:
        m = re.search(r'<label class="tab-label"[^>]*>(.*?)</label>', tab, re.S)
        if not m:
            continue
        label = clean(m.group(1))
        cm = re.match(r"([০-৯]+)\s*(.*)", label)
        if not cm:
            continue
        ch_no, ch_title = bn_to_int(cm.group(1)), cm.group(2)
        for href, inner in re.findall(r'<a href="([^"]+\.html)"[^>]*>(.*?)</a>', tab, re.S):
            t = clean(inner)
            sm = re.match(r"\(([০-৯]+)\)\s*(.*)", t)
            sections.append({
                "chapter": ch_no,
                "chapter_title": ch_title,
                "section": bn_to_int(sm.group(1)) if sm else None,
                "section_title": sm.group(2) if sm else t,
                "file": href,
                "url": BASE + href,
            })
    return sections


def main():
    CACHE.mkdir(exist_ok=True)
    s = requests.Session()
    raw, _ = fetch(CONTENTS, s)
    # The appendices sit inside chapter 60's block on the contents page, so skip by
    # the chapter number in the file name, not by the block they appear in.
    sections = [x for x in parse_contents(decode(raw))
                if int(x["file"].split("_")[0]) not in SKIP_CHAPTERS]
    # Dedupe by file, keep first occurrence order.
    seen, uniq = set(), []
    for x in sections:
        if x["file"] not in seen:
            seen.add(x["file"])
            uniq.append(x)
    (CACHE / "sections.json").write_text(json.dumps(uniq, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(uniq)} section pages listed")

    failed, new = [], 0
    for i, x in enumerate(uniq, 1):
        for attempt in (1, 2):
            try:
                _, dl = fetch(x["file"], s)
                new += dl
                break
            except Exception as e:  # noqa: BLE001
                print(f"  attempt {attempt} failed {x['file']}: {e}")
                time.sleep(3)
        else:
            failed.append(x["file"])
        if i % 50 == 0:
            print(f"  {i}/{len(uniq)} (new downloads: {new})", flush=True)
    print(f"done: {len(uniq) - len(failed)} cached, {new} newly downloaded, {len(failed)} failed")
    for f in failed:
        print("  FAILED:", f)


if __name__ == "__main__":
    main()
