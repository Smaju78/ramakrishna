"""Build the static site's data files.

  python3 build_site.py            public build -> site/data/  (only Safe material)
  python3 build_site.py --preview  as public, but includes non-Safe songs, flagged as a draft
  python3 build_site.py --private  private reading copy -> private_site/ (gitignored), which
                                   adds the Sri Ma Trust English (source-register.md:
                                   "Private reading only — permission requested")

Bengali text comes from our own copy of the Kathamrita Unicode edition (register: Safe, main
text only; footnotes and appendices excluded). The site never links to that site. Problem
titles and passage headlines (both languages) are our own words, so both builds carry them.
"""
import csv
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).parent
DATA = ROOT / "data"
SITE = ROOT / "site"
PRIVATE = ROOT / "private_site"
SHOW_VIDEOS = False  # YouTube is phase 2 (decided 2026-10-03); data/youtube.csv is kept for then


def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def build_songs(out_dir, preview):
    songs = json.loads((DATA / "catalog.json").read_text(encoding="utf-8"))
    out = []
    for s in songs:
        if s["kind"] != "song" or (not preview and s["status"] != "Safe"):
            continue
        out.append({
            "id": s["id"], "first_line": s["first_line"], "status": s["status"],
            "composer": s["composer"], "composer_source": s["composer_source"],
            "thakur": s["sung_by_thakur"], "lyrics": s["full_lyrics"],
            "wikisource": [{k: w[k] for k in ("part", "page", "url", "quality", "ocr_text")}
                           for w in s["wikisource"][:2]],
            "occurrences": [{
                "date_bn": o["date_bn"], "date_iso": o["date_iso"], "date_precision": o["date_precision"],
                "chapter": o["chapter"], "section": o["section"], "section_title": o["section_title"],
                "singer": o["singer_hint"], "thakur": o["sung_by_thakur"],
                "context": o["context_before"].split(" ", 1)[-1],  # drop the cut-off first word
            } for o in s["occurrences"]],
        })
    write_json(out_dir / "data" / "songs.json", {"meta": {"preview": preview, "count": len(out)}, "songs": out})
    print(f"  songs: {len(out)}")
    return {s["id"]: s for s in out}, {s["normalized_first_line"]: s["id"] for s in songs}


def load_youtube():
    """Chosen videos from data/youtube.csv (status proposed or approved). Embed only."""
    path = DATA / "youtube.csv"
    if not SHOW_VIDEOS or not path.exists():
        return {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        return {r["song_key"]: r for r in csv.DictReader(f)
                if r["video_id"].strip() and r["status"].strip() in ("proposed", "approved")}


def english_days(english, pages_path):
    """Private build: for each English passage, that day's English pages (read more)."""
    pages = json.loads(pages_path.read_text(encoding="utf-8"))
    by_page = {(p["vol"], p["page"]): p for p in pages}
    days = {}
    for ref, e in english.items():
        date = by_page[(e["vol"], e["page"])]["date_iso"]
        key = f"v{e['vol']}_{date}"
        if key not in days:
            days[key] = [p["text"] for p in pages if p["vol"] == e["vol"] and p["date_iso"] == date]
        e["day"] = key
    return days


def build_problems(out_dir, songs_by_id, song_id_by_key, private):
    problems = json.loads((DATA / "problems.json").read_text(encoding="utf-8"))
    sections = json.loads((DATA / "sections_text.json").read_text(encoding="utf-8"))
    english, days = {}, {}
    if private:
        english = json.loads((DATA / "english_srimatrust.json").read_text(encoding="utf-8"))
        days = english_days(english, ROOT / "cache" / "srimatrust" / "english_pages.json")
    videos = load_youtube()
    used, out, missing = set(), [], []
    for p in problems:
        items = []
        for it in p["passages"]:
            file, para = it["ref"].split("#p")
            sec = sections[file]
            block = next((b for b in sec["blocks"] if b["i"] == int(para)), None)
            if not block:
                missing.append(it["ref"])
                continue
            used.add(file)
            e = english.get(it["ref"])
            items.append({
                "ref": it["ref"], "file": file, "para": int(para), "type": it.get("type", "saying"),
                "head": it["head"], "head_en": it.get("head_en", ""), "text": block["text"],
                "en": {"text": e["text"], "vol": e["vol"], "page": e["page"], "day": e["day"]} if e else None,
                "date_bn": sec["date_bn"], "chapter": sec["chapter"], "section": sec["section"],
                "section_title": sec["section_title"],
            })
        song_items = []
        for key in p["songs"]:
            sid = song_id_by_key.get(key)
            if not sid or sid not in songs_by_id:
                missing.append(f"song: {key}")
                continue
            s, v = songs_by_id[sid], videos.get(key)
            song_items.append({
                "id": sid, "first_line": s["first_line"], "lyrics": s["lyrics"], "composer": s["composer"],
                "thakur": s["thakur"], "times": len(s["occurrences"]),
                "video": {"id": v["video_id"], "title": v["title"], "channel": v["channel"]} if v else None,
            })
        out.append({"id": p["id"], "title": p["title"], "subtitle": p["subtitle"],
                    "title_en": p.get("title_en", ""), "subtitle_en": p.get("subtitle_en", ""),
                    "passages": items, "songs": song_items})
    write_json(out_dir / "data" / "problems.json", out)
    groups_path = DATA / "groups.json"
    write_json(out_dir / "data" / "groups.json",
               json.loads(groups_path.read_text(encoding="utf-8")) if groups_path.exists() else [])
    # every section, not only those behind picked passages: search results can point anywhere
    for file, sec in sections.items():
        write_json(out_dir / "data" / "sections" / f"{file}.json", sec)
    for key, texts in days.items():
        write_json(out_dir / "data" / "english" / f"{key}.json", texts)
    ready = sum(1 for p in out if p["passages"])
    print(f"  problems: {ready} ready of {len(out)}; {len(sections)} Bengali sections"
          + (f"; English for {len(english)} passages, {len(days)} English days" if private else ""))
    for m in missing:
        print("  MISSING:", m)


def main():
    private = "--private" in sys.argv
    preview = "--preview" in sys.argv or private
    out_dir = PRIVATE if private else SITE
    if private:
        # a fresh private copy of the page; its data lives only here (gitignored)
        shutil.rmtree(out_dir / "data", ignore_errors=True)
        out_dir.mkdir(exist_ok=True)
        shutil.copy(SITE / "index.html", out_dir / "index.html")
    print(f"{'PRIVATE' if private else 'PREVIEW' if preview else 'PUBLIC'} build -> {out_dir.name}/")
    songs_by_id, song_id_by_key = build_songs(out_dir, preview)
    build_problems(out_dir, songs_by_id, song_id_by_key, private)
    write_json(out_dir / "data" / "meta.json", {"private": private, "preview": preview})
    # question search: index from embed_index.py, plus the everyday phrases for the instant match
    search = DATA / "search"
    if (search / "index.json").exists():
        (out_dir / "data" / "search").mkdir(parents=True, exist_ok=True)
        for f in ("index.json", "vectors.bin"):
            shutil.copy(search / f, out_dir / "data" / "search" / f)
        shutil.copy(DATA / "problem_phrases.json", out_dir / "data" / "problem_phrases.json")
        print("  search index copied")
    else:
        print("  WARNING: no data/search/ index; run .venv/bin/python embed_index.py")


if __name__ == "__main__":
    main()
