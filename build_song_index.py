"""Build the Kathamrita song index from cached section pages.

Reads cache/sections.json + cache/*.html (run fetch_kathamrita.py first).
Writes data/songs.json, data/songs.csv (UTF-8 with BOM) and data/parse_report.json.

How songs are found:
  * The site marks verse with <p class="song">. A block counts as a SONG when the
    text around it mentions singing (গান, গাহিতেছেন, গাইলেন, কীর্তন, ...).
    Other verse blocks (Sanskrit slokas, quotations, syllogisms) are kept as
    kind="verse" so nothing is silently dropped.
  * Numbered lists "(১) —", "(২) —" inside paragraphs are split into separate songs.
  * Unmarked verse: a "beng" paragraph right after a singing cue with 2+ lines
    ending in ॥ or ৷ is also treated as a song.
  * A block introduced by "গান চলিতেছে" (the song continues) is merged into the
    previous song.
"""
import csv
import difflib
import html
import json
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).parent
CACHE = ROOT / "cache"
DATA = ROOT / "data"

BN_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")
MONTHS = {
    "জানুয়ারি": 1, "জানুয়ারী": 1, "জানুআরি": 1,
    "ফেব্রুয়ারি": 2, "ফেব্রুয়ারী": 2, "ফেব্রুআরি": 2,
    "মার্চ": 3, "এপ্রিল": 4, "মে": 5, "জুন": 6, "জুলাই": 7,
    "আগস্ট": 8, "অগস্ট": 8, "আগষ্ট": 8,
    "সেপ্টেম্বর": 9, "সেপ্টম্বর": 9, "অক্টোবর": 10, "নভেম্বর": 11, "ডিসেম্বর": 12,
}
# Precomposed/decomposed য় differ between pages; normalise before lookup.
MONTHS = {unicodedata.normalize("NFC", k): v for k, v in MONTHS.items()}


def nfc_re(pattern):
    """Compile a Bengali regex in NFC (য় is decomposed by NFC, so literals must match)."""
    return re.compile(unicodedata.normalize("NFC", pattern))

SING_CUE = nfc_re(
    r"গান|গাহি|গাই|গাইলেন|গাহিলেন|গাইতে|গাহিতে|গেয়ে|গাওয়া|গাওয়া|গাইছেন|"
    r"কীর্তন|সঙ্গীত|সংগীত|ভজন|ধরিলেন|সুর করিয়া|আলাপ|আখর|আরাত্রিক|গীতচ্ছলে|বাউল")
CONTINUE_CUE = nfc_re(r"গান\s*(?:আবার\s*)?চলিতেছে|গান চলিল|গাহিয়া চলিলেন|আবার গাহিতেছেন\s*[—–-]\s*$")
RECITE = nfc_re(r"আবৃত্তি|পাঠ|শ্লোক|স্তব|স্তোত্র|পড়িতেছেন|পড়িতেছেন|বলিতেছেন|বললেন|বলছেন|বলিলেন|প্রার্থনা|গীতা থেকে")
NAMED_SINGER = nfc_re(r"নরেন্দ্র|গায়ক|কীর্তনিয়া|কীর্তনীয়া|ভক্তেরা|ভক্তগণ|রামলাল|ত্রৈলোক্য|বিজয়|গিরিশ|তারক|রাখাল|মণি|ভবনাথ|বৈষ্ণবচরণ|গোস্বামী|ব্রাহ্মণী|নীলকণ্ঠ|মহিমা|কেদার|সকলে|তাঁহারা|ছোকরা|ছেলেরা|মেয়েরা")
DESCRIPTIVE = nfc_re(r"^(ভাব|নৃত্য|প্রেম|নিজে|উন্মত্ত|মধুর|সমাধি)")
THAKUR = nfc_re(r"ঠাকুর|শ্রীরামকৃষ্ণ|পরমহংসদেব")
# Words that end a singer's name in "X গাহিতেছেন" style sentences.
SING_VERB = nfc_re(
    r"(গান\s+)?(গাহিতেছেন|গাইতেছেন|গাহিলেন|গাইলেন|গান ধরিলেন|গাহিতে লাগিলেন|গাইতে লাগিলেন|"
    r"গাহিয়াছিলেন|গাইছেন|গাহিবেন|কীর্তন করিতেছেন|গাহিতেছে|গাইতেছে|ধরিলেন)")
STOP_WORDS = {"এই", "আবার", "তখন", "এবার", "এইবার", "পরে", "আর", "বলিয়া", "করিয়া", "গান",
              "তিনি", "তাঁহারা", "ভক্তেরা", "সকলে", "হইয়া", "সঙ্গে", "সহিত", "মধুর", "স্বরে",
              "সুরে", "একটি", "আরও", "আর", "ও", "উঠিয়া", "নিজে", "নিজেই", "প্রেমে", "মত্ত",
              "যখন", "পর", "নাম", "বিলাপ", "সম্বোধন", "দিকে", "তাঁহার", "তাঁহাদের"}
STOP_WORDS = {unicodedata.normalize("NFC", w) for w in STOP_WORDS}


def bn_int(s):
    return int(s.translate(BN_DIGITS))


def strip_tags(s):
    s = unicodedata.normalize("NFC", s)
    s = re.sub(r"<sup>.*?</sup>", "", s, flags=re.S)  # footnote markers
    s = re.sub(r"\s+", " ", s)  # source wraps every word; only <br> is a real line break
    s = re.sub(r"<br\s*/?>", "\n", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = s.replace("\xa0", " ")
    lines = [re.sub(r"[ \t\r]+", " ", ln).strip() for ln in s.split("\n")]
    return "\n".join(ln for ln in lines if ln)


def one_line(s):
    return re.sub(r"\s+", " ", s).strip()


def normalize_first_line(s):
    s = unicodedata.normalize("NFC", s)
    s = re.sub(r"\([^)]*\)", "", s)  # drop parenthetical refrains like (মা)
    s = re.sub(r"[“”‘’\"'।॥৷,;:!?—–\-\.‌‍]", " ", s)
    s = re.sub(r"^\s*[০-৯0-9]+\s*", "", s)
    return re.sub(r"\s+", " ", s).strip()


def parse_date(text):
    """Find the visit date in the page's heading lines. Returns (bn, iso, precision) or Nones."""
    for raw in re.findall(r'<p class="chaphead">(.*?)</p>', text, re.S)[:4]:
        t = unicodedata.normalize("NFC", one_line(strip_tags(raw)))
        y = re.search(r"(১৮[৭৮৯][০-৯])", t)
        if not y:
            continue
        if re.search(r"\(\s*১৮[৭৮৯][০-৯]\s*\)?", t[max(0, y.start() - 2):y.end() + 2]) and "(" in t[:y.start()]:
            continue  # "শ্রীযুক্ত কেশব সেন (১৮৮১)": a year beside a name, not a visit date
        year = bn_int(y.group(1))
        month = day = None
        mm = re.search("|".join(sorted(MONTHS, key=len, reverse=True)), t)
        if mm:
            month = MONTHS[mm.group(0)]
            # first day number between the year and the month ("৯ই - ১০ই নভেম্বর" -> 9)
            d = re.search(r"(?<![০-৯])([০-৯]{1,2})\s*(?:ই|শে|লা|রা|ঠা|এ)?(?![০-৯])", t[:mm.start()])
            if d:
                day = bn_int(d.group(1))
        # keep only the date part of the heading line, not the title that may follow it
        t = t[:max(y.end(), mm.end() if mm else 0)].strip(" ,")
        if month and day:
            return t, f"{year:04d}-{month:02d}-{day:02d}", "day"
        if month:
            return t, f"{year:04d}-{month:02d}", "month"
        return t, f"{year:04d}", "year"
    # Fallback: a full date written in the opening prose, e.g. "১৫ই জুন ১৮৮৪" or "(১৫ই জুলাই) ১৮৮৫".
    body = unicodedata.normalize("NFC", one_line(strip_tags(text[text.find("<body"):])))[:1200]
    months = "|".join(MONTHS)
    m = re.search(r"(?<![০-৯])([০-৯]{1,2})\s*(?:ই|শে|লা|রা|ঠা|এ)?\s*(" + months + r")\)?\s*,?\s*(১৮[৭৮৯][০-৯])", body)
    if m:
        day, month, year = bn_int(m.group(1)), MONTHS[m.group(2)], bn_int(m.group(3))
        return m.group(0).strip(), f"{year:04d}-{month:02d}-{day:02d}", "day (from text)"
    return None, None, None


def last_sentence(s):
    parts = [p for p in re.split(r"[।!?\n]", s) if p.strip()]
    return parts[-1].strip() if parts else ""


def singer_hint(intro):
    """Name in the sentence just before the song, e.g. 'রামলাল গাহিতেছেন' -> 'রামলাল'."""
    sent = last_sentence(intro.rstrip(" :—–-"))
    m = SING_VERB.search(sent)
    if not m:
        return ""
    before = sent[:m.start()].strip(" ,—–-:")
    # take the clause right before the verb
    before = re.split(r"[,;—–]", before)[-1].strip()
    words = before.split()
    th = next((w for w in words if THAKUR.search(w)), None)
    if th:
        return th
    # Split on participles ("হইয়া", "তাকাইয়া") and descriptive words ("কণ্ঠে", "স্বরে");
    # the singer is usually the words after the last such break, else the clause's first words.
    participle = nfc_re(r"(িয়া|ইয়া|য়া|িতে|ইতে|কণ্ঠে|কন্ঠে|স্বরে|সুরে|রে|ের|দের)$")
    segs, cur = [], []
    for w in words:
        if w in STOP_WORDS or participle.search(w):
            segs.append(cur)
            cur = []
        else:
            cur.append(w)
    segs.append(cur)
    segs = [s for s in segs if s]
    if not segs:
        return ""
    return " ".join(segs[-1][-3:])


def thakur_sang(intro, after, hint):
    if hint and THAKUR.search(hint):
        return True
    sent = last_sentence(intro.rstrip(" :—–-"))
    if THAKUR.search(sent) and SING_VERB.search(sent):
        return True
    # "ঠাকুর এই গান গাহিতেছেন" right after the song
    first_after = re.split(r"[।!?]", after, maxsplit=1)[0]
    if THAKUR.search(first_after) and re.search(r"(এই|এ) গান", first_after) and SING_VERB.search(first_after):
        return True
    return False


NUMBERED = re.compile(r"^\s*[“\"]?\s*\(([০-৯]+)\)\s*[—–।৷\-]*\s*")
GAAN_LABEL = nfc_re(r"^\s*[“\"]?\s*গান\s*[—–:\-]+\s*")


def split_numbered(lyrics):
    """Split '(১) — ... (২) — ...' lists that sit inside one block into separate songs."""
    parts = re.split(r"(?:^|\n)\s*\(([০-৯]+)\)\s*[—–।৷\-]*\s*", lyrics)
    if len(parts) < 3:
        return [lyrics]
    return [p.strip() for p in parts[2::2] if p.strip()]


def verse_like(text):
    lines = [ln for ln in text.split("\n") if ln.strip()]
    ending = sum(1 for ln in lines if re.search(r"[॥৷]\s*[”’]?\s*$", ln))
    return len(lines) >= 2 and ending >= 2


def page_blocks(text):
    """Yield (class, raw_html) for each <p> in the body, in order."""
    body = text[text.find("<body"):]
    body = body.split('<hr align="left"')[0]  # drop footnotes
    for m in re.finditer(r'<p class="([^"]+)"[^>]*>(.*?)</p>', body, re.S):
        yield m.group(1), m.group(2)


def extract_songs(text):
    blocks = list(page_blocks(text))
    songs, prose = [], []  # prose: running plain text before current block
    for i, (cls, raw) in enumerate(blocks):
        txt = strip_tags(raw)
        intro = " ".join(prose)[-600:]
        is_song_block = cls == "song"
        prev_line = one_line(strip_tags(blocks[i - 1][1])) if i and blocks[i - 1][0] == "beng" else ""
        is_unmarked = cls == "beng" and (
            (SING_CUE.search(last_sentence(intro)) and verse_like(txt) and len(txt) < 1500)
            # one-line song after "ঠাকুর গাহিতেছেন —" / "গাইলেন:"
            or (re.search(r"[:—–]\s*$", prev_line) and SING_VERB.search(last_sentence(prev_line))
                and len(txt) < 250))
        if not (is_song_block or is_unmarked):
            if cls in ("beng", "chaphead"):
                prose.append(one_line(txt))
            continue
        # text right after the block, for context and "ঠাকুর এই গান গাহিতেছেন"
        after = " ".join(one_line(strip_tags(r)) for c, r in blocks[i + 1:i + 3] if c != "song")[:300]
        # previous block, ignoring bracketed chaphead subtitles
        prev_i = next((j for j in range(i - 1, -1, -1) if blocks[j][0] in ("beng", "song")), -1)
        prev_cls, prev_raw = blocks[prev_i] if prev_i >= 0 else ("", "")
        prev_txt = one_line(strip_tags(prev_raw))
        cue_text = last_sentence(prev_txt.rstrip(" :—–-"))
        labelled = bool(GAAN_LABEL.match(txt))
        numbered = NUMBERED.match(txt)

        # Inherit from the previous song on this page when this block is:
        #  - introduced by "গান চলিতেছে" (the song continues), or
        #  - a song block straight after another song block (next stanza), or
        #  - item (n>1) of a numbered list.
        prev_song = songs[-1] if songs and prev_i >= 0 and songs[-1]["_block"] == prev_i else None
        if prev_song and not labelled and not numbered and (
                CONTINUE_CUE.search(cue_text) or (prev_cls == "song" and is_song_block)):
            prev_song["full_lyrics"] += "\n" + txt
            prev_song["_block"] = i
            continue
        if songs and not labelled and not numbered and CONTINUE_CUE.search(cue_text) \
                and songs[-1]["kind"] == "song":
            songs[-1]["full_lyrics"] += "\n" + txt
            songs[-1]["_block"] = i
            continue
        if prev_song and (
                (numbered and bn_int(numbered.group(1)) > 1 and prev_song.get("_numbered"))
                # "গান — ..." straight after another song: same singer goes on to the next song
                or (labelled and prev_cls == "song" and prev_song["kind"] == "song")):
            kind, hint, thakur = prev_song["kind"], prev_song["singer_hint"], prev_song["sung_by_thakur"]
        else:
            # The cue can sit a sentence or two back ("X গাহিতেছেন। সঙ্গতের মধ্যে ... —"),
            # unless the block is introduced as a recitation (sloka, stotra, reading).
            wide_cue = SING_CUE.search(intro[-250:]) and not RECITE.search(cue_text)
            has_cue = bool(SING_CUE.search(cue_text) or SING_CUE.search(after[:120]) or labelled or wide_cue)
            kind = "song" if (has_cue or is_unmarked) else "verse"
            hint = singer_hint(cue_text) if kind == "song" else ""
            thakur = thakur_sang(cue_text, after, hint) if kind == "song" else False
            # Implied subject: "ভাবোন্মত্ত হইয়া গান ধরিলেন" / "তিনি ... গাহিতেছেন" with Thakur
            # named in the sentence before. Kathamrita drops the subject when it is Thakur.
            if kind == "song" and not thakur and SING_VERB.search(cue_text) \
                    and (hint in ("", "তিনি") or DESCRIPTIVE.search(hint)) \
                    and not NAMED_SINGER.search(cue_text):
                sents = [p for p in re.split(r"[।!?]", prev_txt.rstrip(" :—–-")) if p.strip()]
                for prev_sent in reversed(sents[-4:-1]):  # up to 3 sentences back
                    if NAMED_SINGER.search(prev_sent):
                        break
                    if THAKUR.search(prev_sent):
                        thakur, hint = True, "ঠাকুর (implied)"
                        break
                if not thakur and DESCRIPTIVE.search(hint):
                    hint = ""

        for lyr in split_numbered(txt):
            lyr = GAAN_LABEL.sub("", NUMBERED.sub("", lyr, count=1), count=1)
            first = lyr.split("\n")[0].strip(" “”\"'")
            songs.append({
                "kind": kind,
                "first_line": first,
                "full_lyrics": lyr.strip(),
                "singer_hint": hint,
                "sung_by_thakur": thakur,
                "context_before": intro[-200:].strip(),
                "unmarked": bool(is_unmarked and not is_song_block),
                "_block": i,
                "_numbered": bool(numbered),
            })
        prose.append("")  # song breaks the prose run a little
    return songs


MIN_PREFIX = 10  # letters; shorter first lines ("আমি", "মা") are too generic to merge on


def merge_shortened(songs):
    """Merge songs whose first line is a shortened form of another song's first line.

    A later mention often prints only the opening words ("কে জানে কালী কেমন, ষড়দর্শনে")
    of a song given in full elsewhere ("কে জানে কালী কেমন, ষড় দর্শনে না পায় দরশন").
    Merge when the short line (spaces ignored) is a prefix of the longer ones and those
    longer ones are themselves one chain; if it prefixes two different songs, leave it.
    """
    tight = {k: k.replace(" ", "") for k in songs}
    merged, ambiguous = [], []
    for short in sorted(songs, key=lambda k: len(tight[k])):
        if len(tight[short]) < MIN_PREFIX or short not in songs:
            continue
        longer = [k for k in songs if k != short and len(tight[k]) > len(tight[short])
                  and tight[k].startswith(tight[short])]
        if not longer:
            continue
        target = max(longer, key=lambda k: len(tight[k]))
        if not all(tight[target].startswith(tight[k]) for k in longer):
            ambiguous.append(f"{songs[short]['first_line']} -> {[songs[k]['first_line'] for k in longer]}")
            continue
        src, dst = songs.pop(short), songs[target]
        dst["occurrences"].extend(src["occurrences"])
        dst["occurrences"].sort(key=lambda o: (o["chapter"], o["section"] or 0, o["order_on_page"]))
        dst["sung_by_thakur"] |= src["sung_by_thakur"]
        if src["kind"] == "song":
            dst["kind"] = "song"
        if len(src["full_lyrics"]) > len(dst["full_lyrics"]):
            dst["full_lyrics"] = src["full_lyrics"]
        merged.append(f"{src['first_line']}  =>  {dst['first_line']}")
    return merged, ambiguous


def main():
    DATA.mkdir(exist_ok=True)
    sections = json.loads((CACHE / "sections.json").read_text(encoding="utf-8"))
    report = {"pages_listed": len(sections), "pages_parsed": 0, "missing_pages": [],
              "date_failed": [], "date_month_only": [], "no_songs": [], "errors": []}
    occurrences = []
    last_date = {}  # chapter -> (bn, iso, precision) of the latest dated section
    for sec in sections:
        path = CACHE / sec["file"]
        if not path.exists():
            report["missing_pages"].append(sec["file"])
            continue
        text = html.unescape(path.read_bytes().decode("latin-1"))
        report["pages_parsed"] += 1
        date_bn, date_iso, prec = parse_date(text)
        if date_bn:
            last_date[sec["chapter"]] = (date_bn, date_iso, prec)
        elif sec["chapter"] in last_date:
            # Later sections of a chapter often continue the same visit without repeating the date.
            date_bn, date_iso, prec = last_date[sec["chapter"]]
            prec = prec.split(" (")[0] + " (from previous section)"
            report.setdefault("date_inherited", []).append(sec["file"])
        if not date_bn:
            report["date_failed"].append(sec["file"])
        elif not prec.startswith("day"):
            report["date_month_only"].append(f"{sec['file']} ({date_bn})")
        try:
            songs = extract_songs(text)
        except Exception as e:  # noqa: BLE001
            report["errors"].append(f"{sec['file']}: {e}")
            continue
        if not any(s["kind"] == "song" for s in songs):
            report["no_songs"].append(sec["file"])
        for n, s in enumerate(songs, 1):
            s.pop("_block")
            s.pop("_numbered")
            occurrences.append({
                **s,
                "page_url": sec["url"],
                "chapter": sec["chapter"],
                "chapter_title": sec["chapter_title"],
                "section": sec["section"],
                "section_title": sec["section_title"],
                "date_bn": date_bn or "",
                "date_iso": date_iso or "",
                "date_precision": prec or "",
                "order_on_page": n,
            })

    # Dedupe on normalized first line. Spaces are ignored ("মন-ভ্রমরা" == "মনভ্রমরা") and
    # near-identical lines (one-letter typos in the source) are matched within a prefix bucket.
    songs, buckets = {}, {}
    for o in occurrences:
        key = normalize_first_line(o["first_line"])
        if not key:
            continue
        tight = key.replace(" ", "")
        bucket = buckets.setdefault(tight[:4], [])
        match = next((k for k in bucket if k.replace(" ", "") == tight), None) or next(
            (k for k in bucket if difflib.SequenceMatcher(None, k.replace(" ", ""), tight).ratio() >= 0.9), None)
        if match:
            key = match
        else:
            bucket.append(key)
        if key not in songs:
            songs[key] = {
                "id": f"s{len(songs) + 1:04d}",
                "kind": o["kind"],
                "first_line": o["first_line"],
                "normalized_first_line": key,
                "full_lyrics": o["full_lyrics"],
                "composer": "",
                "sung_by_thakur": False,
                "occurrences": [],
            }
        song = songs[key]
        if o["kind"] == "song":
            song["kind"] = "song"
        if len(o["full_lyrics"]) > len(song["full_lyrics"]):
            song["full_lyrics"] = o["full_lyrics"]  # keep the fullest text
        song["sung_by_thakur"] |= o["sung_by_thakur"]
        song["occurrences"].append({k: o[k] for k in (
            "page_url", "chapter", "chapter_title", "section", "section_title",
            "date_bn", "date_iso", "date_precision", "singer_hint", "sung_by_thakur",
            "context_before", "unmarked", "order_on_page")})

    report["prefix_merged"], report["prefix_ambiguous"] = merge_shortened(songs)
    out = list(songs.values())
    for n, s in enumerate(out, 1):  # renumber after merging
        s["id"] = f"s{n:04d}"
    (DATA / "songs.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    cols = ["id", "kind", "first_line", "composer", "sung_by_thakur", "occurrence_count",
            "singer_hint", "chapter", "section", "section_title", "date_bn", "date_iso",
            "page_url", "context_before", "full_lyrics"]
    with open(DATA / "songs.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for s in out:
            first = s["occurrences"][0]
            w.writerow({
                "id": s["id"], "kind": s["kind"], "first_line": s["first_line"],
                "composer": "", "sung_by_thakur": s["sung_by_thakur"],
                "occurrence_count": len(s["occurrences"]),
                "singer_hint": " | ".join(dict.fromkeys(o["singer_hint"] for o in s["occurrences"] if o["singer_hint"])),
                "chapter": first["chapter"], "section": first["section"],
                "section_title": first["section_title"], "date_bn": first["date_bn"],
                "date_iso": first["date_iso"], "page_url": first["page_url"],
                "context_before": first["context_before"], "full_lyrics": s["full_lyrics"],
            })

    sung = [s for s in out if s["kind"] == "song"]
    report["occurrences_total"] = len(occurrences)
    report["song_occurrences"] = sum(1 for o in occurrences if o["kind"] == "song")
    report["unique_songs"] = len(sung)
    report["unique_verses_not_songs"] = len(out) - len(sung)
    report["songs_sung_by_thakur"] = sum(1 for s in sung if s["sung_by_thakur"])
    (DATA / "parse_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    for k in ("pages_listed", "pages_parsed", "occurrences_total", "song_occurrences", "unique_songs",
              "unique_verses_not_songs", "songs_sung_by_thakur"):
        print(f"{k}: {report[k]}")
    for k in ("missing_pages", "date_failed", "date_month_only", "no_songs", "errors"):
        print(f"{k}: {len(report[k])}")


if __name__ == "__main__":
    main()
