"""Cut the Sri Ma Trust English for each chosen passage, using start/end anchors.

PRIVATE READING ONLY (source-register.md). Inputs: cache/srimatrust/english_pages.json,
cache/srimatrust/anchors.json [{ref, vol, page, start, end}]. The text is taken verbatim from
the PDF text; the span is widened to whole sentences (and closing quotes) at both ends.
Output: data/english_srimatrust.json {ref: {"text", "vol", "page"}} (gitignored).
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).parent
DIR = ROOT / "cache" / "srimatrust"
SENT_END = re.compile(r"[.!?](?:\s*[’”'\"])*(?:\s*[’”])?")


def volume_text(pages, vol):
    """One flat string per volume plus the character offset where each page starts."""
    parts, offsets, pos = [], {}, 0
    for p in sorted((p for p in pages if p["vol"] == vol), key=lambda p: p["page"]):
        t = re.sub(r"-\n(?=[a-z])", "-", p["text"])  # line-end hyphens in compounds
        t = re.sub(r"\s+", " ", t).strip() + " "
        offsets[p["page"]] = pos
        parts.append(t)
        pos += len(t)
    return "".join(parts), offsets


def main():
    import sys
    anchors_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DIR / "anchors.json"
    out_path = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "data" / "english_srimatrust.json"
    pages = json.loads((DIR / "english_pages.json").read_text(encoding="utf-8"))
    anchors = json.loads(anchors_path.read_text(encoding="utf-8"))
    vols = {v: volume_text(pages, v) for v in {a["vol"] for a in anchors}}
    out, problems = {}, []
    for a in anchors:
        text, offsets = vols[a["vol"]]
        s = text.find(a["start"], max(0, offsets[a["page"]] - 2000))
        if s < 0:
            problems.append(f"{a['ref']}: start not found")
            continue
        if a.get("widen"):  # anchor starts mid-sentence: back up to the sentence start
            back = max(text.rfind(c, 0, s) for c in ".!?”’")
            s = back + 1 if back >= 0 and s - back < 300 else s
        elif text[max(0, s - 2):s].strip() == "“":  # keep an opening quote right before the anchor
            s = text.rfind("“", 0, s)
        e = text.find(a["end"], s)
        if e < 0 or e - s > 4000:
            problems.append(f"{a['ref']}: end not found near start")
            continue
        m = SENT_END.search(text, e + len(a["end"]) - 1)
        e = m.end() if m and m.start() - e < 400 else e + len(a["end"])
        span = text[s:e].strip().lstrip("’”) ")
        if span.count("“") > span.count("”") and not span.startswith("“"):
            span = span  # leave quotes exactly as printed
        out[a["ref"]] = {"text": span, "vol": a["vol"], "page": a["page"]}
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(out)} of {len(anchors)} extracted")
    for p in problems:
        print("  PROBLEM:", p)


if __name__ == "__main__":
    main()
