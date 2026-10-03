"""Apply quality-check results (data/qc/*.json) to data/problems.json and the English anchors.

Each QC problem's "passages" (final list, in order) and "songs" replace the current ones.
New anchors (cache/srimatrust/qc/*_anchors.json) are added to cache/srimatrust/anchors.json.
Writes data/qc_report.csv with every verdict and reason, for review.
"""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).parent
DATA = ROOT / "data"
SM = ROOT / "cache" / "srimatrust"


def main():
    problems = json.loads((DATA / "problems.json").read_text(encoding="utf-8"))
    by_id = {p["id"]: p for p in problems}
    passages = {p["id"] for p in json.loads((DATA / "passages.json").read_text(encoding="utf-8"))}
    sections = json.loads((DATA / "sections_text.json").read_text(encoding="utf-8"))
    songs = {s["normalized_first_line"] for s in json.loads((DATA / "catalog.json").read_text(encoding="utf-8"))
             if s["kind"] == "song"}
    rows, changed = [], 0
    for f in sorted((DATA / "qc").glob("*.json")):
        for q in json.loads(f.read_text(encoding="utf-8"))["problems"]:
            p = by_id[q["id"]]
            bad = [it["ref"] for it in q["passages"] if it["ref"] not in passages and not any(
                b["i"] == int(it["ref"].split("#p")[1]) for b in sections.get(it["ref"].split("#p")[0], {}).get("blocks", []))]
            bad += [k for k in q["songs"] if k not in songs]
            if bad:
                print(f"  SKIP {q['id']}: unknown refs/songs {bad}")
                continue
            before = [it["ref"] for it in p["passages"]]
            p["passages"], p["songs"] = q["passages"], q["songs"]
            changed += before != [it["ref"] for it in q["passages"]]
            for r in q.get("review", []):
                rows.append([f.stem, q["id"], r["verdict"], r["ref"], r.get("reason", "")])
            print(f"  {f.stem}: {q['id']:10} {len(before)} -> {len(q['passages'])} passages; {q.get('notes', '')[:90]}")
    (DATA / "problems.json").write_text(json.dumps(problems, ensure_ascii=False, indent=1), encoding="utf-8")

    anchors = {a["ref"]: a for a in json.loads((SM / "anchors.json").read_text(encoding="utf-8"))}
    for f in sorted((SM / "qc").glob("*_anchors.json")):
        for a in json.loads(f.read_text(encoding="utf-8")):
            anchors[a["ref"]] = a
    wanted = {it["ref"] for p in problems for it in p["passages"]}
    kept = [a for r, a in anchors.items() if r in wanted]
    (SM / "anchors.json").write_text(json.dumps(kept, ensure_ascii=False, indent=1), encoding="utf-8")

    with open(DATA / "qc_report.csv", "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["batch", "problem", "verdict", "ref", "reason"])
        w.writerows(rows)
    total = sum(len(p["passages"]) for p in problems)
    counts = {v: sum(1 for r in rows if r[2] == v) for v in ("keep", "replace", "drop", "new")}
    print(f"{changed} problems changed; {total} passages; {len(kept)} with English anchors; verdicts {counts}")


if __name__ == "__main__":
    main()
