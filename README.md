# ঠাকুরের কথা · What Thakur Said

What Sri Ramakrishna said about the problems of life, from the *Sri Sri Ramakrishna Kathamrita*
by Mahendranath Gupta (Sri M). Thirty problems (grief, anger, fear of death, money worries,
doubt, …), each with Thakur's own words in Bengali, plus a question box: describe what you're
going through and the site finds the passages that speak to it. No API key, no server — the
question is understood by a small open multilingual model running in your browser.

Live site: https://smaju78.github.io/ramakrishna/

## Sources
See [source-register.md](source-register.md). Nothing is published unless its row says **Safe**.
The English translation of passages (Sri Ma Trust) is used only in a private local build until
permission is granted; this repository contains no part of it.

## Rebuild
```
python3 fetch_kathamrita.py        # cached download of the Bengali text
python3 build_song_index.py        # songs
python3 extract_passages.py        # Thakur's spoken passages
.venv/bin/python embed_index.py    # search index (model: Xenova/multilingual-e5-small)
python3 build_site.py              # public site -> site/
```
