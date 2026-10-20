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

## Suggested layout

```
CLAUDE.md
README.md
data/raw/        # original sheets and downloaded corpora
data/build/      # generated JSON consumed by the app
scripts/         # offline pipeline: clean, segment, score, translate, export
src/             # front end
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
