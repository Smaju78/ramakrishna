"""Print a keyword shortlist of Thakur's passages for one problem, for hand-picking.

Usage: python3 shortlist.py <problem_id> [top_n]
Scores each passage in data/passages.json by keyword hits (keywords from data/problems.json),
favouring passages of readable length. Writes data/shortlists/<problem_id>.json.
"""
import json
import re
import sys
import unicodedata
from pathlib import Path

DATA = Path(__file__).parent / "data"
NFC = lambda s: unicodedata.normalize("NFC", s)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--kw=")]
    pid, top = args[0], int(args[1]) if len(args) > 1 else 40
    kw_arg = next((a[5:] for a in sys.argv[1:] if a.startswith("--kw=")), None)
    if kw_arg:  # --kw=শোক,দুঃখ  (comma-separated), instead of the keywords in problems.json
        kws = [NFC(k.strip()) for k in kw_arg.split(",") if k.strip()]
    else:
        problem = next(p for p in json.loads((DATA / "problems.json").read_text(encoding="utf-8")) if p["id"] == pid)
        kws = [NFC(k) for k in problem["keywords"]]
    scored = []
    for p in json.loads((DATA / "passages.json").read_text(encoding="utf-8")):
        hits = {k: len(re.findall(re.escape(k), p["text"])) for k in kws}
        distinct = sum(1 for v in hits.values() if v)
        if not distinct:
            continue
        length_ok = 1.0 if 120 <= len(p["text"]) <= 1500 else 0.6
        scored.append((round((distinct * 2 + sum(hits.values())) * length_ok, 1), p, [k for k, v in hits.items() if v]))
    scored.sort(key=lambda x: -x[0])
    out = [{"score": s, "id": p["id"], "date": p["date_bn"], "where": f"{p['chapter']}.{p['section']}",
            "hits": h, "text": p["text"]} for s, p, h in scored[:top]]
    (DATA / "shortlists").mkdir(exist_ok=True)
    (DATA / "shortlists" / f"{pid}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{pid}: {len(scored)} passages with hits; top {len(out)} -> data/shortlists/{pid}.json")


if __name__ == "__main__":
    main()
