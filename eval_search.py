"""Try questions against the search and print what a reader would see; score page routing.

Usage: .venv/bin/python eval_search.py ["your own question" ...]
The ranking here is the reference for the in-browser version in site/index.html (rank()).
"""
import json
import re
import sys
import unicodedata
from pathlib import Path

import numpy as np

from embed_index import Embedder

ROOT = Path(__file__).parent
DATA = ROOT / "data"
MIN_LEN = 150          # shorter passages are rarely a useful answer on their own
W_DESC, W_PICKS, W_PHRASE = 0.4, 0.6, 0.02
W_THEME = 0.5          # "more from the Kathamrita": closeness to the top page's theme
W_HUB = 1.0            # penalty for passages that are close to every topic ("hubs")

SAMPLES = [  # (question, expected page)
    ("আমার মা মারা গেছেন, কিছুতেই মন মানছে না", "grief"),
    ("অফিসে খুব রাগ হয়ে যায়, সামলাতে পারি না", "anger"),
    ("টাকার চিন্তায় রাতে ঘুম আসে না", "money"),
    ("ছেলে কথা শোনে না, কী করব", "children"),
    ("ঈশ্বর বলে কি সত্যিই কেউ আছেন?", "doubt"),
    ("জপ করতে বসলে মন অন্য দিকে চলে যায়", "restless"),
    ("বয়স হয়ে গেছে, এখন কী করা উচিত", "oldage"),
    ("I can't control my anger at work", "anger"),
    ("My father passed away and I feel lost", "grief"),
    ("I feel very lonely, nobody cares about me", "loneliness"),
    ("Which religion is the true one?", "whichpath"),
    ("I've been meditating for years and nothing happens", "despair"),
    ("My colleague insults me in front of everyone", "insult"),
    ("I am too busy with job and family to pray", "notime"),
    ("স্বামীর সঙ্গে রোজ ঝগড়া হয়", "marriage"),
    ("I keep comparing myself to my friends who earn more", "jealousy"),
    ("আমি অনেক পাপ করেছি, ঈশ্বর কি ক্ষমা করবেন?", "guilt"),
    ("What is the point of living?", "purpose"),
]


def phrase_hits(q, phrases):
    qb = unicodedata.normalize("NFC", q)
    ql = " " + re.sub(r"[^a-z' ]", " ", q.lower()) + " "
    hits = sum(1 for ph in phrases.get("bn", []) if unicodedata.normalize("NFC", ph) in qb)
    # English: whole phrase at a word start; long phrases also match word forms ("compare" ~ "comparing")
    hits += sum(1 for ph in phrases.get("en", [])
                if f" {ph}" in ql and (len(ph) >= 5 or f" {ph} " in ql)
                or (len(ph) >= 6 and f" {ph[:-1]}" in ql))
    return hits


def main():
    args = sys.argv[1:]
    samples = [(a, None) for a in args] or SAMPLES
    vecs = np.load(DATA / "search_vectors.npy")
    index = json.loads((ROOT / "data" / "search" / "index.json").read_text(encoding="utf-8"))
    problems = json.loads((DATA / "problems.json").read_text(encoding="utf-8"))
    phrases = json.loads((DATA / "problem_phrases.json").read_text(encoding="utf-8"))
    n = len(index["passages"])
    row = {p["id"]: i for i, p in enumerate(index["passages"])}
    long_ok = np.array([len(p["t"]) >= MIN_LEN for p in index["passages"]])
    picks = {p["id"]: [row[it["ref"]] for it in p["passages"] if it["ref"] in row] for p in problems}
    centroid = {}
    for pid, rows in picks.items():
        c = vecs[rows].mean(0)
        centroid[pid] = c / np.linalg.norm(c)
    # hubness: a passage's average closeness to all 30 page themes; "close to everything" scores high
    cents = np.stack([centroid[p["id"]] for p in problems])
    hub = (vecs[:n] @ cents.T).mean(1)
    emb = Embedder()
    right = 0
    for q, expected in samples:
        v = emb(["query: " + q])[0]
        sims = vecs @ v
        scores = {}
        for k, p in enumerate(problems):
            pick_sims = np.sort(sims[picks[p["id"]]])[::-1][:3]
            desc = max(sims[n + k], sims[n + len(problems) + k])  # Bengali or English description
            scores[p["id"]] = (W_DESC * desc + W_PICKS * pick_sims.mean()
                               + W_PHRASE * min(3, phrase_hits(q, phrases.get(p["id"], {}))))
        top = sorted(scores, key=lambda x: -scores[x])[:3]
        ok = expected is None or top[0] == expected
        right += ok
        theme = vecs[:n] @ centroid[top[0]]
        more = sims[:n] + W_THEME * theme - W_HUB * hub
        more[~long_ok] = -9
        shown = set(picks[top[0]])
        more_rows = [i for i in np.argsort(-more) if i not in shown][:5]
        print(f"\n### {q}   [{'OK' if ok else 'expected ' + expected}]")
        print("  pages:", " | ".join(f"{t} {scores[t]:.3f}" for t in top))
        for i in more_rows:
            print(f"    more: {index['passages'][i]['id'][:24]:24} {index['passages'][i]['t'][:100]}")
    if not args:
        print(f"\nrouting: {right}/{len(samples)} top-1 correct")


if __name__ == "__main__":
    main()
