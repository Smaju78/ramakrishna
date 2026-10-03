"""Find where a chosen Bengali passage sits in the Sri Ma Trust English (private reading only).

Usage: python3 english_find.py data/english_queries.json
Each query: {"ref": "<file>#p<n>", "terms": ["dream", "eight sons"]}. Searches only English
pages with the same visit date as the passage (falls back to all pages if none), and
prints each hit with context so the start/end words of the matching English can be chosen.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent


def main():
    queries = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    pages = json.loads((ROOT / "cache" / "srimatrust" / "english_pages.json").read_text(encoding="utf-8"))
    passages = {p["id"]: p for p in json.loads((ROOT / "data" / "passages.json").read_text(encoding="utf-8"))}
    sections = json.loads((ROOT / "data" / "sections_text.json").read_text(encoding="utf-8"))
    for q in queries:
        file = q["ref"].split("#")[0]
        p = passages.get(q["ref"])
        date = p["date_iso"] if p else ""
        if not date:  # event paragraphs are not in passages.json; use the section's date
            import build_song_index as b  # noqa: F401  (only for parity; date is in sections_text)
            date = ""
        pool = [pg for pg in pages if date and pg["date_iso"] == date] or pages
        print(f"\n##### {q['ref']}  date={date or '?'}  pages={len(pool)}")
        shown = 0
        for pg in pool:
            flat = re.sub(r"\s+", " ", pg["text"])
            hits = [t for t in q["terms"] if re.search(re.escape(t), flat, re.I)]
            if len(hits) < q.get("min", 1):
                continue
            m = re.search(re.escape(hits[0]), flat, re.I)
            print(f"  [vol {pg['vol']} p {pg['page']}] hits={hits}")
            print("   ", flat[max(0, m.start() - 350):m.start() + 650])
            shown += 1
            if shown >= q.get("max", 3):
                break


if __name__ == "__main__":
    main()
