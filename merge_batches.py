"""Merge curated batches into data/problems.json and the English anchors.

Inputs: data/problems.json (existing), data/batches/*.json (one per curator),
cache/srimatrust/anchors.json + cache/srimatrust/batches/*_anchors.json.
A batch problem replaces the problem with the same id. Problems are ordered by GROUPS.
Checks every passage ref and song key, and reports refs used by more than one problem.
"""
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).parent
DATA = ROOT / "data"
SM = ROOT / "cache" / "srimatrust"

# Home-page groups, in order, with every problem id in display order.
GROUPS = [
    ("mind", "মন ও অনুভূতি", "Mind and emotions",
     ["grief", "death", "fear", "anger", "jealousy", "loneliness", "hopeless", "restless"]),
    ("character", "স্বভাব", "Character",
     ["ego", "desire", "lust", "guilt", "hypocrisy", "laziness", "insult"]),
    ("family", "সংসার ও কাজ", "Family and work",
     ["family", "marriage", "children", "money", "work", "oldage", "illness", "badpeople"]),
    ("spiritual", "আধ্যাত্মিক জীবন", "Spiritual life",
     ["doubt", "whichpath", "prayer", "despair", "notime", "attachment", "purpose"]),
]


def main():
    existing = {p["id"]: p for p in json.loads((DATA / "problems.json").read_text(encoding="utf-8"))}
    for f in sorted((DATA / "batches").glob("*.json")):
        for p in json.loads(f.read_text(encoding="utf-8"))["problems"]:
            existing[p["id"]] = p
            print(f"  {f.stem}: {p['id']} ({len(p['passages'])} passages, {len(p['songs'])} songs)")

    ordered = []
    for gid, _, _, ids in GROUPS:
        for pid in ids:
            p = existing.pop(pid, None)
            if p is None:
                print(f"  MISSING problem: {pid}")
                continue
            p["group"] = gid
            ordered.append(p)
    for pid in existing:  # anything not in GROUPS (old ids) is dropped, but say so
        print(f"  DROPPED (not in GROUPS): {pid}")

    passages = {p["id"] for p in json.loads((DATA / "passages.json").read_text(encoding="utf-8"))}
    sections = json.loads((DATA / "sections_text.json").read_text(encoding="utf-8"))
    songs = {s["normalized_first_line"] for s in json.loads((DATA / "catalog.json").read_text(encoding="utf-8"))
             if s["kind"] == "song"}
    used = defaultdict(list)
    for p in ordered:
        for it in p["passages"]:
            file, para = it["ref"].split("#p")
            ok = it["ref"] in passages or any(b["i"] == int(para) for b in sections.get(file, {}).get("blocks", []))
            if not ok:
                print(f"  BAD REF {p['id']}: {it['ref']}")
            used[it["ref"]].append(p["id"])
        for k in p["songs"]:
            if k not in songs:
                print(f"  BAD SONG {p['id']}: {k}")
    for ref, ids in used.items():
        if len(ids) > 1:
            print(f"  SHARED {ref}: {', '.join(ids)}")

    (DATA / "problems.json").write_text(json.dumps(ordered, ensure_ascii=False, indent=1), encoding="utf-8")
    (DATA / "groups.json").write_text(json.dumps([{"id": g, "title": bn, "title_en": en, "problems": ids}
                                                  for g, bn, en, ids in GROUPS], ensure_ascii=False, indent=1),
                                      encoding="utf-8")

    anchors = {a["ref"]: a for a in json.loads((SM / "anchors.json").read_text(encoding="utf-8"))}
    for f in sorted((SM / "batches").glob("*_anchors.json")):
        for a in json.loads(f.read_text(encoding="utf-8")):
            anchors[a["ref"]] = a
    wanted = {it["ref"] for p in ordered for it in p["passages"]}
    kept = [a for r, a in anchors.items() if r in wanted]
    (SM / "anchors.json").write_text(json.dumps(kept, ensure_ascii=False, indent=1), encoding="utf-8")
    total = sum(len(p["passages"]) for p in ordered)
    print(f"{len(ordered)} problems, {total} passages, {len(kept)} with English anchors")


if __name__ == "__main__":
    main()
