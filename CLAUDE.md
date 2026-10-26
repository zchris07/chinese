# CLAUDE.md — PROTOTYPE BUILD

> **STATUS: PROTOTYPE.** This is a proof-of-concept, not production software.
> Optimize for speed of learning and a working demo. Do not over-engineer,
> add abstractions "for later", or build features outside the prototype scope below.
> Anything marked *Post-prototype* is deliberately out of scope.

## Project

A minimal web app for learning Mandarin Chinese. A jade-green full-screen
backdrop shows one Mandarin sentence in white, centered. The learner explores
the sentence by hovering and clicking, zooming from sentence → word → character.
Other languages may come later, so keep the data model language-agnostic
(see Architecture), but do not build multi-language support now.

## Prototype scope

**In scope**
- Jade-green backdrop, white centered sentence, nothing else cluttering the screen.
- New random sentence on **Space** or a button click.
- Difficulty selector mapped to HSK level (simple → conversational → difficult).
- Toggles: pinyin, simplified/traditional, English translation.
- Hover a word/character → its text changes shade. Multi-character words highlight
  as one unit; standalone single-character morphemes highlight alone.
- Click a highlighted word → the rest of the sentence fades out, the word moves to
  the foreground, and its definition(s) appear.
- Hover a character inside the isolated word → highlight; click → isolate with an
  animation, showing the character's general meaning/connotation and a list of
  other words containing it.
- Click-away / Escape steps back out one level.
- A small, hand-curated or pipeline-built sentence set is enough (a few hundred is fine).

**Out of scope (post-prototype)**
- Accounts, login, server-side persistence, spaced repetition, quizzes, Anki export.
- Audio/TTS, stroke-order animation, grammar-pattern callouts.
- Other languages, native mobile apps, analytics, monetization.
- Live runtime translation or sentence generation (see Data rules).

## Architecture (keep it simple)

- **Static front end**, no backend required for the core experience.
  Plain HTML/CSS/JS or a small Vite app. Pick one and stay with it.
- **All linguistic data is precomputed offline** and shipped as static JSON.
  The browser never segments, translates, or generates at runtime.
- Each sentence record carries everything the UI needs:
  - simplified text and traditional text
  - English translation
  - pinyin per token
  - segmentation into tokens (word-level), each token marked as a multi-character
    word or a single character
  - difficulty level (highest HSK level among its words) and optional grammar-pattern tag
- Word and character data live in separate lookup tables keyed by the token/character:
  - words: definitions (cleaned), pinyin with tone marks, HSK level
  - characters: general meaning, plus a reverse index of words that contain it
- Model the zoom as **levels**: sentence → word → component. Do not hardcode
  "Chinese character" assumptions into UI logic beyond the data fields.

## Data sources

| Need | Source |
|---|---|
| HSK vocab + definitions | The provided HSK Vocab sheet (CC-CEDICT-style definitions) |
| Grammar patterns + example sentences | The provided Language Player grammar chart |
| Extra sentences | Tatoeba (CC-BY), filtered by difficulty score |
| Dictionary backfill | CC-CEDICT (CC BY-SA) |
| Character meanings | Wiktionary extracts, or LLM-written and cached |
| Segmentation (offline) | jieba, pkuseg, or HanLP |
| Pinyin / script conversion (offline) | pinyin-pro, OpenCC |

Raw source files go in `data/raw/`. Generated output goes in `data/build/`.
Never hand-edit generated files; fix the pipeline or the raw data instead.

### Data rules
- Translation is **precomputed once and cached** in the sentence record. The
  translation toggle only shows/hides stored text.
- Any LLM or translation API call happens only in offline scripts under `scripts/`.
  API keys come from environment variables and are never committed or shipped to the browser.
- Sentence difficulty = highest HSK level of any word in it. A generated or imported
  sentence whose words are not all found in the vocab data must be rejected or flagged.
- Known data issues to clean before use: numbered pinyin (`xiu1 ci3`) must be
  converted to tone marks; vocab definitions lump senses with semicolons and include
  `CL:` classifier notes; the grammar sheet has corrupted cells (`#NAME?`,
  auto-converted dates) and an empty `pattern` column.
- Open question to resolve first: whether the vocab sheet follows HSK 2.0 (levels 1–6)
  or HSK 3.0 (levels 1–9). Do not assume; check and record the answer here.

## Current state (first prototype build)

- **Stack chosen:** plain HTML/CSS/JS, no framework, no bundler. Stay with it.
- **Run it:** `node scripts/build.mjs` (rebuilds data), then serve the repo root
  (`python -m http.server 5173`) and open `http://localhost:5173/src/`.
  Opening `src/index.html` directly from disk also works, because the build emits
  `data/build/data.js` (`window.APP_DATA = …`) alongside `data.json`.
- **Phone / shareable build:** `node scripts/bundle.mjs` inlines everything into
  `dist/jade.html` (gitignored), which is published as a private claude.ai artifact:
  https://claude.ai/artifact/NBDUjVAAHj41nSNnLkBdVd. Re-bundle and republish after UI changes.
- **Look:** bold sans (Noto Sans SC/TC 700, subway-sign style), pinyin on by default, flat, fully opaque jade (`--jade: #2b9b70`) with no gradient or shading;
  hovered words turn deep jade (`--hover`).
- **Data is hand-curated for now:** `data/raw/sentences.txt` (34 pre-segmented
  sentences + English), `words.tsv`, `chars.tsv`. The HSK Vocab sheet and grammar
  chart have **not** been added yet. When they arrive, replace the curated TSVs
  with a cleaning step in `scripts/` that produces the same shape.
- **HSK version:** the curated levels approximate **HSK 2.0 (1–6)** and were
  hand-assigned. The open question about the real vocab sheet is still unresolved.
- **Difficulty buckets:** simple = HSK 1–2, conversational = 3–4, difficult = 5–6.
- **Build output shape** (`data/build/data.json`):
  - `sentences[]`: `{ id, s, t, en, level, tokens: [{ w, t, py, kind: 'word'|'char'|'punct' }] }`
  - `words{simplified}`: `{ t, py: [syllable…], hsk, defs: [...] }` — one syllable per character
  - `chars{simplified}`: `{ m, words: [simplified…] }` — reverse index, sorted by HSK
- The build fails on any token missing from `words.tsv` or any character missing from `chars.tsv`.
- **UI:** the zoom is a stack (`word` → `char` → related `word` → …). Esc or
  click-away pops one level; Space or the big button under the sentence gives a new one.
  A single click/tap on a word opens it (no tap-to-arm step). Glyphs fly between
  levels with a FLIP transform. Keys: P pinyin, S script, E English.
- **Not yet handled (curated set):** contextual pinyin (tone sandhi such as 一/不, and polyphonic
  characters come from the word entry, not the sentence context).

## Real-world passages (Wikipedia pilot)

Goal: a **huge** pool of real paragraphs, fully analyzable like the curated
sentences. Sources are limited to text we can legally ship. The pilot is
**Wikipedia only**. Poetry, literature, news, lyrics and social media are out for now.

- **Difficulty option:** "Real-world · Wikipedia" (`difficulty: 'wiki'`) shows a
  random multi-sentence passage with a source/license line. Word and character
  drill-down work the same as for sentences.
- **Pipeline** (Python, in `scripts/wiki/`; `pip install jieba pypinyin opencc-python-reimplemented requests anthropic`):
  1. `download.py`: CC-CEDICT + the MIT `complete-hsk-vocabulary` list into `data/raw/`.
  2. `fetch.py --count 350`: random featured articles (典范条目) via the MediaWiki API
     → `data/raw/wiki/articles.jsonl`. Random articles are mostly stubs, so we sample featured ones.
  3. `process.py`: clean (to simplified, strip romanized parentheticals and refs),
     pick paragraphs of 2–6 sentences / 50–360 chars, split words with jieba (unknown
     compounds split greedily into CC-CEDICT words), add citation-tone pinyin (pypinyin,
     no sandhi), traditional via OpenCC, definitions from CC-CEDICT (matching reading
     first), levels from HSK 2.0 (`old-N`; 7 = HSK 3.0 7–9 only; missing = beyond HSK).
     Rejects passages where >2% of characters are missing from CC-CEDICT.
  4. `translate.py`: English per sentence via the Message Batches API (one request
     per passage, structured JSON output), cached in `data/raw/wiki/translations.jsonl`
     (committed, keyed by sha1 of the sentence). Re-run `process.py` to merge.
     Needs Anthropic credentials; prints tokens, cost and a full-pool projection. Not run yet.
  4b. `translate_local.py`: **free** offline alternative with Argos Translate (`pip install
     argostranslate`, about 1 s per sentence on CPU), written to the same cache with
     `engine: 'argos'`. This is what the pilot uses. Names are often wrong and clauses are
     sometimes dropped, so the app labels it as machine translation.
- **Output:** `data/build/wiki/index.json` + `shard-NNN.json` (50 passages each, with
  their own `words`/`chars` tables, merged into the app's lookup on load). Passage:
  `{ id, source: { type, title, url, license }, stats: { tokens, beyondHsk, hsk5plus },
  sentences: [{ s, t, en, tokens: [{ w, t?, py ('mì shū chù'), kind }] }] }`.
  `t` is omitted when equal to the simplified text; `kind` adds `other` (Latin/digits).
- **Not committed:** raw dictionaries, fetched articles and `data/build/wiki/`
  (regenerate with the steps above). The translation cache is committed because it costs money to rebuild.
- **Hosting:** the app `fetch()`es shards, so it must be served over http. The phone
  artifact publishes `data/build/wiki/*` as `wiki/*` next to the page (`window.WIKI_BASE`).
  At full scale move to GitHub Pages or Cloudflare Pages, since the artifact has a size cap.
- **Attribution:** Wikipedia text is CC BY-SA 4.0 and each passage links to its
  article. CC-CEDICT is CC BY-SA 4.0. The HSK list is MIT.

## Layout

```
CLAUDE.md
data/raw/        # curated TSV/TXT now; original sheets and corpora later
data/build/      # generated JSON (+ data.js) consumed by the app — do not hand-edit
scripts/         # offline pipeline (build.mjs: validate + export)
src/             # front end: index.html, style.css, app.js
.claude/         # launch.json for the local preview server
```

## Working conventions

- **Order of work:** (1) clean the two sheets into structured data, (2) prototype the
  sentence pipeline, (3) lock the JSON shape, (4) build the UI against that JSON.
- Prefer the simplest thing that demonstrates the interaction. Hard-code before configuring.
- Keep functions small and comments sparse; match surrounding style.
- Interaction details that matter:
  - Space generates a new sentence but must not scroll the page or re-trigger a
    focused button.
  - Hover does not exist on touch devices. Design the tap model (tap = highlight,
    tap again = open) even if the prototype ships desktop-first.
  - Isolation animations should be CSS transitions, short and interruptible.
- Test the data pipeline with small fixtures; for the UI, verify manually in a browser
  and note what was checked.
- Do not commit secrets, API keys, or large raw corpora without asking.

## Licensing notes

CC-CEDICT is CC BY-SA, Tatoeba is CC-BY, and the grammar chart examples come from a
third-party course. Keep attribution in the README. Confirm rights on the grammar
sheet before any public release.

## Definition of done for the prototype

A user can open the page, press Space for new sentences at a chosen difficulty,
toggle pinyin/script/translation, hover and click down from sentence to word to
character, see definitions and related words, and step back out. Everything works
from static files with no backend.
