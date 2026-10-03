"""Link indexed songs to Bengali Wikisource and apply source-register.md rules.

Inputs:  data/songs.json (from build_song_index.py), cache/wikisource/part*.json (fetch_wikisource.py),
         data/attributions.csv (yours to edit; created on first run, never overwritten).
Outputs: data/catalog.json, data/catalog.csv (UTF-8 with BOM), data/enrich_report.json.

Wikisource text is mostly unproofread OCR in the 1912-era spelling, so matching is fuzzy:
both sides are reduced to bare Bengali letters (no spaces, virama, nukta, doubled consonants),
candidate spots are found by shared 3-letter shingles, then checked with difflib.
"""
import csv
import difflib
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).parent
DATA = ROOT / "data"
WS = ROOT / "cache" / "wikisource"
PART_FILES = {
    1: "শ্রীশ্রীরামকৃষ্ণ কথামৃত প্রথম ভাগ.djvu",
    3: "শ্রীশ্রীরামকৃষ্ণ কথামৃত তৃতীয় ভাগ.djvu",
    4: "শ্রীশ্রীরামকৃষ্ণ কথামৃত চতুর্থ ভাগ.djvu",
    5: "শ্রীশ্রীরামকৃষ্ণ কথামৃত পঞ্চম ভাগ.djvu",
}
EN_TO_BN = str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯")
MATCH_THRESHOLD = 0.62  # difflib ratio on normalized letters; OCR noise keeps true matches ~0.65-0.95
STRONG_MATCH = 0.75     # below this, also require a song marker in the scan text
SONG_MARK = re.compile("গীত|গান")

# Composer as named by the Kathamrita itself: the song's own ভণিতা (signature in the last lines)
# or the narration just before it ("রামপ্রসাদের গান ধরিলেন"). Patterns are checked in order.
BHANITA = [
    ("Ramprasad Sen", r"প্রসাদ\s*(?:বলে|ভাষে|কয়|বলিছে|ভনে)|রামপ্রসাদ|দ্বিজ রামপ্রসাদ"),
    ("Kamalakanta Bhattacharya", r"কমলাকান্ত"),
    ("Dasarathi Ray", r"দাশরথি"),
    ("Kubir Goswami", r"কুবীর"),
    ("Nilkantha Mukhopadhyay", r"নীলকণ্ঠ"),
    ("Premik", r"প্রেমিক\s*(?:বলে|কয়)"),
    ("Chandidas", r"চণ্ডীদাস"),
    ("Vidyapati", r"বিদ্যাপতি"),
    ("Govindadas", r"গোবিন্দদাস"),
]
# "X-এর গান" only, and not "...গানের বই" (a songbook mention, not this song).
NARRATION = [
    ("Ramprasad Sen", r"(?:রাম)?প্রসাদের (?:\S+ )?গান(?!ের)"),
    ("Kamalakanta Bhattacharya", r"কমলাকান্তের (?:\S+ )?গান(?!ের)"),
    ("Trailokyanath Sanyal", r"ত্রৈলোক্যের (?:রচিত )?গান(?!ের)"),
    ("Swami Vivekananda", r"স্বামীজী রচিত|বিবেকানন্দ রচিত"),
    ("Dasarathi Ray", r"দাশরথির (?:\S+ )?গান(?!ের)"),
    ("Kubir Goswami", r"কুবীরের (?:\S+ )?গান(?!ের)"),
]


def letters(s):
    """Bare Bengali letters for fuzzy matching across OCR noise and old spelling."""
    s = unicodedata.normalize("NFD", s)
    s = s.replace("ৰ", "র").replace("়", "")  # Assamese ra (OCR), nukta
    s = re.sub(r"[^অ-হড়-য়া-ৌৗ]", "", s)  # drop virama, signs, punct
    s = re.sub(r"(.)\1+", r"\1", s)  # কর্ম্ম -> কর্ম after virama removal
    return s


def clean_page(text):
    text = re.sub(r"<noinclude>.*?</noinclude>", "", text, flags=re.S)
    text = re.sub(r"<[^>]+>", "", text)
    return text.replace("﻿", "")


def load_parts():
    """Per part: concatenated letters + a map from letter index to (page, raw index)."""
    parts = {}
    for part, fname in PART_FILES.items():
        path = WS / f"part{part}.json"
        if not path.exists():
            continue
        pages = json.loads(path.read_text(encoding="utf-8"))
        tight, where, raw_pages = [], [], {}
        for n in sorted(pages, key=int):
            raw = clean_page(pages[n]["text"])
            raw_pages[n] = raw
            for i, ch in enumerate(raw):
                for c in letters(ch):
                    tight.append(c)
                    where.append((n, i))
        s = "".join(tight)
        grams = defaultdict(list)
        for i in range(len(s) - 2):
            grams[s[i:i + 3]].append(i)
        parts[part] = {"s": s, "where": where, "grams": grams, "pages": pages, "raw": raw_pages}
    return parts


def find(query, part):
    """Best (score, start, end) of query in a part's letter string, or None."""
    s, grams = part["s"], part["grams"]
    if len(query) < 8:
        return None
    votes = defaultdict(int)
    for j in range(len(query) - 2):
        hits = grams.get(query[j:j + 3], ())
        if len(hits) > 400:  # very common shingle, no signal
            continue
        for p in hits:
            votes[(p - j) // 8] += 1
    best = None
    for bucket, _ in sorted(votes.items(), key=lambda kv: -kv[1])[:8]:
        for start in range(max(0, bucket * 8 - 8), bucket * 8 + 16, 2):
            window = s[start:start + len(query)]
            r = difflib.SequenceMatcher(None, query, window, autojunk=False).ratio()
            if not best or r > best[0]:
                best = (r, start, start + len(query))
    return best


def page_url(part, n):
    title = f"পাতা:{PART_FILES[part]}/{n.translate(EN_TO_BN)}"
    return "https://bn.wikisource.org/wiki/" + quote(title.replace(" ", "_"))


def ocr_excerpt(part, start_letter, n_letters):
    """Raw OCR text covering n_letters from start_letter, possibly across a page break."""
    where = part["where"]
    end_letter = min(start_letter + n_letters, len(where) - 1)
    (p0, i0), (p1, i1) = where[start_letter], where[end_letter]
    # back up to the start of the word (the match can begin a letter or two in)
    raw0 = part["raw"][p0]
    while i0 > 0 and not raw0[i0 - 1].isspace() and raw0[i0 - 1] not in "—।॥-" and i0 > where[start_letter][1] - 12:
        i0 -= 1
    if p0 == p1:
        return part["raw"][p0][i0:i1 + 1].strip()
    return (part["raw"][p0][i0:].strip() + "\n[পৃষ্ঠা পরিবর্তন]\n" + part["raw"][p1][:i1 + 1].strip())


def composer_from_text(song):
    """(composer, evidence) as named in the Kathamrita, or ("", "")."""
    nfc = lambda x: unicodedata.normalize("NFC", x)
    tail = nfc(song["full_lyrics"])[-200:]
    for name, pat in BHANITA:
        m = re.search(nfc(pat), tail)
        if m:
            return name, f"ভণিতা: “{m.group(0)}”"
    for o in song["occurrences"]:
        lead = nfc(o["context_before"])[-160:]
        for name, pat in NARRATION:
            m = re.search(nfc(pat), lead)
            if m:
                return name, f"কথামৃতের বর্ণনা: “{m.group(0)}”"
    return "", ""


def load_attributions(songs):
    """Your composer overrides, keyed by normalized first line.

    Optional: a composer typed here wins over the one the Kathamrita names. The file is only
    rewritten when new songs need rows, and existing rows are never changed.
    """
    path = DATA / "attributions.csv"
    cols = ["normalized_first_line", "first_line", "composer_candidate", "composer", "composer_source", "notes"]
    rows = {}
    if path.exists():
        with open(path, encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                rows[r["normalized_first_line"]] = r
    added = 0
    for s in songs:
        k = s["normalized_first_line"]
        if k not in rows:
            rows[k] = {"normalized_first_line": k, "first_line": s["first_line"],
                       "composer_candidate": s["composer_candidate"], "composer": "",
                       "composer_source": "", "notes": ""}
            added += 1
    if added:
        try:
            with open(path, "w", encoding="utf-8-sig", newline="") as f:
                w = csv.DictWriter(f, fieldnames=cols)
                w.writeheader()
                w.writerows(rows.values())
        except PermissionError:
            print(f"WARNING: {path.name} is open elsewhere (Excel?); {added} new rows not saved this run.")
    return rows, added


def main():
    songs = json.loads((DATA / "songs.json").read_text(encoding="utf-8"))
    parts = load_parts()
    report = {"parts_loaded": sorted(parts), "page_quality": {}}
    for p, part in parts.items():
        q = defaultdict(int)
        for pg in part["pages"].values():
            q[str(pg["quality"])] += 1
        report["page_quality"][p] = dict(q)

    for s in songs:
        s["composer_candidate"], s["composer_evidence"] = (
            composer_from_text(s) if s["kind"] == "song" else ("", ""))
        for o in s["occurrences"]:
            o["wikisource"] = None
        lines = [ln for ln in s["full_lyrics"].split("\n") if ln.strip()]
        query = letters(" ".join(lines[:2]))[:70]
        lyr_len = len(letters(s["full_lyrics"]))
        hits = []
        for p, part in parts.items():
            m = find(query, part)
            if not m or m[0] < MATCH_THRESHOLD:
                continue
            n, i = part["where"][m[1]]
            # Weak matches count only if the scan marks a song (গীত / গান) just before the spot;
            # without that, short first lines match ordinary prose.
            if m[0] < STRONG_MATCH and not SONG_MARK.search(part["raw"][n][max(0, i - 120):i]):
                continue
            hits.append({
                "part": p, "page": int(n), "score": round(m[0], 3),
                "url": page_url(p, n),
                "quality": part["pages"][n]["quality"],
                "ocr_text": ocr_excerpt(part, m[1], int(lyr_len * 1.15) + 10),
            })
        hits.sort(key=lambda h: -h["score"])
        s["wikisource"] = hits

    attributions, added = load_attributions(songs)
    for s in songs:
        a = attributions[s["normalized_first_line"]]
        # Your entry in attributions.csv wins; otherwise the composer the Kathamrita names.
        if a["composer"].strip():
            s["composer"], s["composer_source"] = a["composer"].strip(), a["composer_source"].strip() or "attributions.csv"
        else:
            s["composer"], s["composer_source"] = s["composer_candidate"], s["composer_evidence"]
        # Text: our copy of the Unicode edition (register: Safe, main text only; footnotes are
        # already dropped by build_song_index.py). Wikisource scan is the cross-check.
        best = s["wikisource"][0] if s["wikisource"] else None
        s["text_source"] = "Kathamrita Unicode edition (own copy)"
        if not best:
            s["crosscheck"] = "not found on Wikisource (Part 2, or scan text too noisy)"
        elif best["quality"] in (3, 4):
            s["crosscheck"] = "Wikisource scan, proofread"
        else:
            s["crosscheck"] = "Wikisource scan, unproofread"
        # Register (2026-10-03): any song printed in the Kathamrita is Safe, composer known or not
        # (sung 1881-1887; no plausible composer died 1966 or later). Text source is Safe too.
        reasons = []
        if s["kind"] != "song":
            reasons.append("not a song")
        s["status"] = "Safe" if not reasons else "Check"
        s["status_reasons"] = reasons

    (DATA / "catalog.json").write_text(json.dumps(songs, ensure_ascii=False, indent=1), encoding="utf-8")
    cols = ["id", "kind", "first_line", "status", "status_reasons", "composer", "composer_source",
            "sung_by_thakur", "occurrence_count", "first_date_iso", "first_chapter_section",
            "text_source", "crosscheck", "wikisource_part", "wikisource_page", "wikisource_score", "wikisource_url",
            "index_page_url"]
    with open(DATA / "catalog.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for s in songs:
            o, b = s["occurrences"][0], (s["wikisource"][0] if s["wikisource"] else {})
            w.writerow({
                "id": s["id"], "kind": s["kind"], "first_line": s["first_line"], "status": s["status"],
                "status_reasons": "; ".join(s["status_reasons"]), "composer": s["composer"],
                "composer_source": s["composer_source"], "sung_by_thakur": s["sung_by_thakur"],
                "occurrence_count": len(s["occurrences"]), "first_date_iso": o["date_iso"],
                "first_chapter_section": f"{o['chapter']}.{o['section']}",
                "text_source": s["text_source"], "crosscheck": s["crosscheck"], "wikisource_part": b.get("part", ""),
                "wikisource_page": b.get("page", ""), "wikisource_score": b.get("score", ""),
                "wikisource_url": b.get("url", ""), "index_page_url": o["page_url"],
            })

    sung = [s for s in songs if s["kind"] == "song"]
    report.update({
        "songs": len(sung),
        "matched_on_wikisource": sum(1 for s in sung if s["wikisource"]),
        "matched_by_part": {p: sum(1 for s in sung if s["wikisource"] and s["wikisource"][0]["part"] == p)
                            for p in parts},
        "not_matched": sum(1 for s in sung if not s["wikisource"]),
        "with_composer_candidate": sum(1 for s in sung if s["composer_candidate"]),
        "composer_named": sum(1 for s in sung if s["composer"]),
        "status_safe": sum(1 for s in sung if s["status"] == "Safe"),
        "attribution_rows_added": added,
    })
    (DATA / "enrich_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    for k, v in report.items():
        print(f"{k}: {v}")


if __name__ == "__main__":
    main()
