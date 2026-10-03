"""Build the meaning-based search index for the site (no API key, no server).

Model: Xenova/multilingual-e5-small, quantized ONNX (models/multilingual-e5-small), the same file
the browser runs through transformers.js, so offline and in-browser vectors are comparable.
e5 convention: passages are embedded as "passage: …", questions as "query: …"; mean pooling, L2-normalised.

Outputs in data/search/ (build_site.py copies them into each site build):
  vectors.bin   int8 [N x 384] — rows: every Thakur passage, then each problem page described in
                Bengali, then each again in English (same order as "problems")
  index.json    {"dim", "scale", "passages": [{id, f, p, ch, s, d, t}], "problems": [ids in row order]}
Run with the project venv:  .venv/bin/python embed_index.py
"""
import json
import time
from pathlib import Path

import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer

ROOT = Path(__file__).parent
MODEL = ROOT / "models" / "multilingual-e5-small"
DATA = ROOT / "data"
MAX_TOKENS = 512
SCALE = 127.0


class Embedder:
    def __init__(self):
        self.tok = Tokenizer.from_file(str(MODEL / "tokenizer.json"))
        self.tok.enable_truncation(MAX_TOKENS)
        self.tok.enable_padding(pad_id=self.tok.token_to_id("<pad>") or 1, pad_token="<pad>")
        self.sess = ort.InferenceSession(str(MODEL / "onnx" / "model_quantized.onnx"),
                                         providers=["CPUExecutionProvider"])
        self.inputs = {i.name for i in self.sess.get_inputs()}

    def __call__(self, texts):
        enc = self.tok.encode_batch(texts)
        ids = np.array([e.ids for e in enc], dtype=np.int64)
        mask = np.array([e.attention_mask for e in enc], dtype=np.int64)
        feed = {"input_ids": ids, "attention_mask": mask}
        if "token_type_ids" in self.inputs:
            feed["token_type_ids"] = np.zeros_like(ids)
        hidden = self.sess.run(None, feed)[0]                      # [B, T, 384]
        m = mask[..., None].astype(np.float32)
        vec = (hidden * m).sum(1) / np.clip(m.sum(1), 1e-9, None)   # mean pooling
        return vec / np.linalg.norm(vec, axis=1, keepdims=True)


def problem_text(p):
    """What a problem page is about (Bengali), for routing a question to it."""
    heads = "; ".join(it["head"] for it in p["passages"])
    return f"{p['title']} — {p['subtitle']}. {', '.join(p.get('keywords', []))}. {heads}"


def problem_text_en(p):
    """The same in English (our own titles and headlines), so English questions route well."""
    heads = "; ".join(it.get("head_en", "") for it in p["passages"])
    return f"{p.get('title_en', '')} — {p.get('subtitle_en', '')}. {heads}"


def main():
    passages = json.loads((DATA / "passages.json").read_text(encoding="utf-8"))
    problems = json.loads((DATA / "problems.json").read_text(encoding="utf-8"))
    texts = (["passage: " + p["text"] for p in passages] + ["passage: " + problem_text(p) for p in problems]
             + ["passage: " + problem_text_en(p) for p in problems])
    emb = Embedder()
    order = sorted(range(len(texts)), key=lambda i: len(texts[i]))  # similar lengths per batch: less padding
    vecs = np.zeros((len(texts), 384), dtype=np.float32)
    t0 = time.time()
    for b in range(0, len(order), 32):
        idx = order[b:b + 32]
        vecs[idx] = emb([texts[i] for i in idx])
        if b % 640 == 0:
            print(f"  {b}/{len(texts)}  {time.time() - t0:.0f}s", flush=True)
    q = np.clip(np.round(vecs * SCALE), -127, 127).astype(np.int8)
    index = {
        "model": "Xenova/multilingual-e5-small", "dim": 384, "scale": SCALE,
        "passages": [{"id": p["id"], "f": p["file"], "p": p["para"], "ch": p["chapter"], "s": p["section"],
                      "d": p["date_bn"], "t": p["text"]} for p in passages],
        "problems": [p["id"] for p in problems],
    }
    out = DATA / "search"  # build_site.py copies this into each site build
    out.mkdir(parents=True, exist_ok=True)
    (out / "vectors.bin").write_bytes(q.tobytes())
    (out / "index.json").write_text(json.dumps(index, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    np.save(DATA / "search_vectors.npy", vecs)  # full precision, for offline evaluation
    print(f"{len(texts)} vectors in {time.time() - t0:.0f}s; vectors.bin {q.nbytes / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
