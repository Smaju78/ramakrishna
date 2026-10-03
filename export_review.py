"""Write data/review.csv (UTF-8 with BOM, opens in Excel): every pick on every problem page,
so the curation can be reviewed in one sheet."""
import csv
import json
from pathlib import Path

DATA = Path(__file__).parent / "data"


def main():
    problems = json.loads((DATA / "problems.json").read_text(encoding="utf-8"))
    sections = json.loads((DATA / "sections_text.json").read_text(encoding="utf-8"))
    english = json.loads((DATA / "english_srimatrust.json").read_text(encoding="utf-8"))
    songs = {s["normalized_first_line"]: s for s in json.loads((DATA / "catalog.json").read_text(encoding="utf-8"))}
    rows = 0
    with open(DATA / "review.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["group", "problem", "problem_en", "kind", "headline_bn", "headline_en", "ref",
                    "date", "chapter", "has_english", "bengali_start"])
        for p in problems:
            for it in p["passages"]:
                file, para = it["ref"].split("#p")
                sec = sections[file]
                block = next(b for b in sec["blocks"] if b["i"] == int(para))
                w.writerow([p["group"], p["title"], p["title_en"], it.get("type", "saying"), it["head"],
                            it["head_en"], it["ref"], sec["date_bn"], f"{sec['chapter']}.{sec['section']}",
                            "yes" if it["ref"] in english else "no", block["text"][:140]])
                rows += 1
            for k in p["songs"]:
                w.writerow([p["group"], p["title"], p["title_en"], "song", songs[k]["first_line"], "", "", "", "", "", ""])
                rows += 1
    print(f"{rows} rows -> data/review.csv")


if __name__ == "__main__":
    main()
