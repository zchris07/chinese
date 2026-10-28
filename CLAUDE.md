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
- Difficulty selector with five tiers: **Simple, Ordinary, Complex, Advanced, Scholar** (see Sentence pool).
- Toggles: pinyin, simplified/traditional, English translation.
- Hover a word/character → its text changes shade. Multi-character words highlight
  as one unit; standalone single-character morphemes highlight alone.
- Click a highlighted word → the rest of the sentence fades out, the word moves to
  the foreground, and its definition(s) appear.
- Hover a character inside the isolated word → highlight; click → isolate with an
  animation, showing the character's general meaning/connotation and a list of
  other words containing it.
- Click-away / Escape steps back out one level.
- A pipeline-built sentence pool of a few thousand sentences is enough.

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
  - tier (simple / ordinary / complex / advanced / scholar) and a source record (type, title, link, license)
- Word and character data live in separate lookup tables keyed by the token/character:
  - words: definitions (cleaned), pinyin with tone marks, HSK 3.0 level, part of speech
  - characters: general meaning, plus a reverse index of words that contain it
- Model the zoom as **levels**: sentence → word → component. Do not hardcode
  "Chinese character" assumptions into UI logic beyond the data fields.

## Data sources

| Need | Source | License |
|---|---|---|
| Levels, part of speech, traditional forms, grammar outline | **ivankra/hsk30** — official HSK 3.0, `data/raw/hsk30/` (primary reference) | MIT |
| HSK 2.0 level per word, grammar examples + translations, lesson links | The two Google Sheets, `data/raw/hsk_vocab.xlsx`, `hsk_grammar.xlsx` | third-party; rights unconfirmed |
| Definitions, classifiers, character meanings | CC-CEDICT | CC BY-SA 4.0 |
| Word frequency | drkameleon/complete-hsk-vocabulary | MIT |
| Everyday sentences + human English | Tatoeba | CC BY 2.0 FR |
| Real-world sentences | zh.wikipedia.org featured articles (典范条目) | CC BY-SA 4.0 |
| Segmentation / pinyin / script (offline) | jieba, pypinyin, OpenCC | |

Raw source files go in `data/raw/`. Generated output goes in `data/merged/` (committed) and
`data/build/` (git-ignored). Never hand-edit generated files; fix the pipeline, the raw data, or
`data/raw/corrections.csv` instead.

### Data rules
- Translation is **precomputed once and cached** in the sentence record. The
  translation toggle only shows/hides stored text.
- Any LLM or translation call happens only in offline scripts under `scripts/`.
  API keys come from environment variables and are never committed or shipped to the browser.
- **HSK version: resolved.** The vocab sheet is **HSK 2.0** (levels 1–6, 5,003 words). The grammar
  sheet's levels 1–6 follow the HSK 2.0 Standard Course textbooks and its `7-9` block follows HSK 3.0.
  The project uses **HSK 3.0 (hsk30) as the reference level**; HSK 2.0 is kept as a second column.
  Findings and itemized errors are in `docs/audit/`.
- Sheet cells that were corrupted by the spreadsheet (auto-converted dates/times, typos, mistranslations)
  are fixed through `data/raw/corrections.csv`; each fix is noted in the merged CSV's `notes` column.
- The 7–9 band of the grammar sheet has machine-translated glosses; its rows are flagged
  `sheet-machine` in `translation_source` and the app labels them "Machine translation (unreviewed)".

## Merged CSV

`python scripts/merge/build_merged.py` → `data/merged/hsk_merged.csv` (+ `merge_report.md`).
One row per word form (`type=word`, 11.6k), per HSK 3.0 grammar point (`type=grammar`, 573) and per
grammar-sheet example (`type=example`, 1,016). Columns include `hsk3_level`, `hsk2_level`, `pos`,
`definition` (senses joined by ` | `), `classifiers`, `frequency_rank`, `textbook_code`, `example_zh/en`,
`translation_source`, `lesson_url`, `source`, `license`, `notes`.
Sheet words that hsk30 lacks are kept with an empty `hsk3_level`. Examples link to an hsk30 grammar point
by a conservative heuristic (`grammar_no`, flagged in `notes`); usage-only rows stay unlinked.

## Sentence pool (what the app draws from)

`python scripts/pool/build_pool.py` → `data/build/pool/index.json` + `<tier>-NNN.json` shards
(150 sentences each, with their own `words`/`chars` tables, merged into the app's lookup on load).
Each sentence is analysed the same way whatever its source: jieba segmentation (HSK words added to the
dictionary), contextual pinyin, traditional via OpenCC, word data from the merged CSV (CC-CEDICT fallback).

Sources:
1. **Grammar examples** — the sheet's 971 sentences that are full sentences (fragments like 五个学生 are skipped),
   with the sheet's translations. A sentence is never placed below its textbook level (1–2 simple, 3–4 ordinary,
   5–6 complex, 7–9 advanced).
2. **Tatoeba** — 60k Mandarin sentences with a human English translation; a random sample of
   `--tatoeba-cap` (700) per tier, so it fills the everyday tiers without drowning the other sources.
3. **Wikipedia** — individual sentences from featured-article lead sections (`fetch.py --lead`, 20 articles per
   request; full-text `fetch.py --count` is much slower under Wikimedia rate limits). Only sentences with an
   English translation ship; the rest are queued in `data/raw/wiki/pending.jsonl` for
   `translate_local.py` (free, offline Argos; machine translation, labelled in the app) or `translate.py` (Claude).
   **Every Wikipedia sentence is Scholar**, whatever its vocabulary: encyclopedia prose is hard, and a few easy
   sentences would not make it a different kind of text.

**Tiers** (`tier_of` in `build_pool.py`): each word gets its HSK 3.0 level; a sentence from the grammar sheet or
Tatoeba belongs to the smallest tier that holds at least 90% of its words. Simple = levels 1–2, Ordinary = 3–4,
Complex = 5–6, Advanced = 7–9 or unlisted. **Scholar** is not a vocabulary band: it holds all Wikipedia sentences. Rules that keep this fair: an unlisted compound (这个, 不是) takes the level of its parts, and proper nouns
(CC-CEDICT capitalised readings, surnames) do not count.

Run order: `pip install jieba pypinyin opencc-python-reimplemented openpyxl requests` (+ `argostranslate` for
local translation) → `python scripts/wiki/download.py` → `python scripts/merge/build_merged.py` →
`python scripts/wiki/fetch.py --lead` → `python scripts/pool/build_pool.py` → `python scripts/wiki/translate_local.py`
→ `python scripts/pool/build_pool.py` again to merge the new translations.
(`pip install jieba` can fail on new setuptools: install `setuptools<70` first, or copy the package.)

## Current state

- **Stack:** plain HTML/CSS/JS, no framework, no bundler. Stay with it.
- **Run it:** build the pool (above), then `python -m http.server 5173` from the repo root and open
  `http://localhost:5173/src/`. It must be served over http: the app `fetch()`es the pool shards.
- **Hosting (static site in `docs/`):** `node scripts/build_site.mjs` (after the pool build) writes the whole site to
  `docs/` — page, script, styles, credits, favicon and the pool shards (about 20 MB) — which GitHub Pages serves
  ("Deploy from a branch", folder `/docs`). Any static host works the same way (Cloudflare Pages: no build command,
  output directory `docs`). Everything uses relative URLs, so it works under a sub-path like `/chinese/`. Rebuild and
  commit `docs/` whenever the pool or the UI changes. `docs/audit/` is served too. `node scripts/bundle.mjs`
  still makes the single-file `dist/jade.html` for a claude.ai artifact (publish the pool beside it as `pool/*`);
  the old artifact (https://claude.ai/artifact/NBDUjVAAHj41nSNnLkBdVd) predates the pool and is out of date.
- **Look:** bold sans (Noto Sans SC/TC 700, subway-sign style), pinyin on by default, flat, fully opaque jade
  (`--jade: #2b9b70`), hovered words turn deep jade (`--hover`).
- **Build output shape** (`data/build/pool/<tier>-NNN.json`):
  - `sentences[]`: `{ id, s, t, en, source: { type: 'grammar'|'tatoeba'|'wikipedia', title, url?, license, translation? }, tokens: [{ w, t?, py ('mì shū chù'), kind: 'word'|'char'|'punct'|'other' }] }`
  - `words{simplified}`: `{ py: [syllable…], defs: [...], t?, hsk?, pos? }` — `hsk` is HSK 3.0 (7 = 7–9; absent = unlisted)
  - `chars{simplified}`: `{ m, words: [simplified…] }` — reverse index, sorted by HSK 3.0 level then frequency
- **UI:** the zoom is a stack (`word` → `char` → related `word` → …). Esc or click-away pops one level; Space or the
  big button gives a new sentence. A single click/tap on a word opens it. Glyphs fly between levels with a FLIP
  transform. Keys: P pinyin, S script, E English. The source line shows the Wikipedia article / Tatoeba sentence /
  grammar lesson the sentence came from.
- **Not yet handled:** tone sandhi (一/不) in displayed pinyin; homographs share one word entry (还 hái/huán show
  the first reading's definitions first); the grammar link on examples is a heuristic.

## Layout

```
CLAUDE.md
data/raw/        # sheets (xlsx), hsk30/, corrections.csv, translation cache; downloads are git-ignored
data/merged/     # hsk_merged.csv + merge_report.md (committed)
data/build/pool/ # generated sentence shards consumed by the app (git-ignored)
docs/            # the hosted static site (built by scripts/build_site.mjs); docs/audit/ = data audit
scripts/merge/   # build_merged.py
scripts/pool/    # build_pool.py
scripts/wiki/    # download, fetch, translate, shared text helpers (process.py)
src/             # front end: index.html, style.css, app.js, credits.html, favicon.svg
.claude/         # launch.json for the local preview server
```

## Working conventions

- **Order of work:** data first (merge → pool), then the UI against the pool JSON.
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

CC-CEDICT and Wikipedia text are CC BY-SA (share-alike), Tatoeba is CC BY 2.0 FR, hsk30 is MIT, and the grammar
chart examples come from a third-party course. The app's source line credits each sentence. Confirm rights on the
grammar sheet before any public release; the `license` column of the merged CSV lets restricted rows be filtered out.

## Definition of done for the prototype

A user can open the page, press Space for new sentences at a chosen difficulty,
toggle pinyin/script/translation, hover and click down from sentence to word to
character, see definitions and related words, and step back out. Everything works
from static files with no backend.
