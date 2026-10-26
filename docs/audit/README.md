# Data audit: HSK Vocab sheet + Language Player grammar chart

Source files: `data/raw/hsk_vocab_sheet1.pdf`, `data/raw/hsk_grammar_language_player_chinese_grammar_chart.pdf`.
Both were audited from PDF exports. Itemized findings (one row per issue):

- `vocab_issues.csv`: word-level problems with sheet value vs. reference value
- `grammar_issues.csv`: row-level problems keyed by grammar `id`

## Headline findings

1. **The two sheets use different HSK systems.** The vocab sheet is **HSK 2.0** (levels 1–6, 5,003 words).
   The grammar sheet's levels 1–6 follow the **HSK 2.0 Standard Course textbooks** (codes are
   `level.lesson.item`, e.g. `5.35.3`, `6.40.2`). Its `7-9.*` block follows the **HSK 3.0** advanced
   grammar list. The merged file needs both an `hsk2_level` and an `hsk3_level` column.
2. **The vocab sheet covers HSK 2.0 well but not HSK 3.0.** 4,489 of its 5,003 words are in HSK 3.0.
   It is missing **2,453 HSK 3.0 level 1–6 words** and **4,073 level 7–9 words**.
3. **The HSK 7–9 grammar section is unusable as-is.** All 324 rows have `#NAME?` pinyin (a broken formula).
   Six have `#VALUE!` English glosses. The English glosses and example translations are raw machine
   translation, often wrong or missing the grammar point.

## Vocab sheet (HSK 2.0)

| Check | Result |
|---|---|
| Rows | 5,003 (L1 148, L2 147, L3 298, L4 586, L5 1,311, L6 2,513) |
| Blank cells | none |
| Duplicate words | 8, all legitimate multi-reading entries (过, 长, 只, 还, 得, 等, 对, 尽量) |
| vs. complete-hsk-vocabulary HSK 2.0 | 19 missing, 23 extra/variant, 46 level mismatches |
| vs. hskhsk 2012 revision | 191 missing / 191 extra (the sheet follows the earlier list) |
| Pinyin vs. CC-CEDICT | 70 differ: 7 real errors, about 33 written with tone sandhi, about 30 neutral-tone choices |
| Definitions | 6 words have a wrong sense; all defs are older CC-CEDICT text needing cleanup |

**Level errors worth fixing first** (sheet → HSK 2.0): 上 5→1, 后面 6→1, 看 3→1, 几 3→1, 水果 2→1,
知道 5→2, 从 5→2, 事情 5→2, 累 5→2, 元 4→2, 别人 6→3, 故事 5→3, 更 5→3, 像 5→3. Full list in CSV.

**Missing HSK 2.0 words:** 一路, 休养, 倘若, 分之, 刮, 刷, 名胜, 团圆, 弹, 散布, 涮, 烟花, 片断, 电子, 素食,
花瓣, 踢, 通货, 高速. Most are replaced by collocations (刮→刮风, 踢→踢足球, 电子→电子邮件,
高速→高速公路). Collocations such as 踢足球 and 弹钢琴 are not dictionary entries, which breaks word lookup.

**Pinyin errors:** 动画片 pian1→pian4, 兴高采烈 xing1→xing4, 抢劫 qiang1→qiang3, 光滑 hua5→hua2,
巴不得 / 恨不得 de2→de5, 嗯 `ńg` (non-standard, only non-numbered entry).
Tone sandhi is applied inconsistently: 一 appears as yi1/yi2/yi4 and 不 as bu4/bu2/bu5. Store
citation tones and compute sandhi at display time.

**Wrong definitions:** 馋 ("slander", which is 谗), 兴隆 (Xinglong County instead of "prosperous"),
振兴 (Zhenxing District instead of "to revitalize"), 惯例 ("conventional" instead of "convention"),
团结 ("a rally"), 理发 ("a barber" instead of "to get a haircut").

**Missing columns:** traditional, tone-mark pinyin, part of speech, HSK 3.0 level, frequency.

## Grammar sheet

| Check | Result |
|---|---|
| Rows | 1,016 (ids 1–1018; 851, 852 absent; one row has a blank id, presumably 717) |
| Unique points | L1 45, L2 44, L3 47, L4 100, L5 126, L6 100, 7–9 145 (+15 appendix `5.A*`) |
| Column I | header and every cell is `#NAME?` (broken formula). Drop it. |
| `pattern` column | filled only in 7–9 |
| `url` | missing for all 7–9 and appendix rows (341) |
| vs. official HSK 3.0 7–9 list (148 points) | essentially complete |
| vs. official HSK 3.0 L1–6 (425 points) | many uncovered, mostly function words and measure words that live in the vocab list |

**Levels 1–6** (human translations): 星期四 translated as "Monday" (id 17); missing structure (18);
examples are "-" (232, 469); 可以可以 (565); 像册→相册 (649); 554 example lacks 肯定; translation
errors at 500 and 619; typos at 375, 523, 612.

**7–9** (machine translation): glosses like "Huh_huh_" (忽A忽B), "since_since_" (自A自B), "Ah" (矣),
"Unavoidable" (未免). Translations are wrong at 889 (把丈夫死了 → "She killed her husband"), 847, 1017,
1018, 899 and others. The whole band should be re-translated, not patched row by row.

**PDF artifacts, not sheet errors:** overflowing long cells merge text (e.g. 867, 907, 940), and 462 examples
contain line-wrap spaces. A CSV export of the original Google Sheets would remove both.

## Supplementary public datasets

| Dataset | What it adds | License |
|---|---|---|
| [ivankra/hsk30](https://github.com/ivankra/hsk30) | Official HSK 3.0: 11,092 words (traditional, pinyin, POS) + 573 grammar points | MIT |
| [drkameleon/complete-hsk-vocabulary](https://github.com/drkameleon/complete-hsk-vocabulary) | HSK 2.0 + 3.0 levels, frequency, POS, radicals, transcriptions | MIT |
| [CC-CEDICT](https://www.mdbg.net/chinese/dictionary?page=cc-cedict) | Current definitions, traditional forms | CC BY-SA 4.0 |
| [Tatoeba](https://tatoeba.org/downloads) | Mandarin–English sentence pairs, some audio | CC BY 2.0 FR |
| [makemeahanzi](https://github.com/skishore/makemeahanzi) | Character decomposition, etymology hints, radicals, strokes | Arphic / LGPL (see COPYING) |
| [Unihan](https://www.unicode.org/charts/unihan.html) | Character readings, definitions, variants | Unicode license |
| [Destaq/chinese-sentence-miner](https://github.com/Destaq/chinese-sentence-miner) | About 18k Tatoeba sentences tagged with HSK difficulty | check repo |
| [HF 20k-en-zh-translation-pinyin-hsk](https://huggingface.co/datasets/swaption2009/20k-en-zh-translation-pinyin-hsk) | About 20k graded sentences, HSK 1–4 | none stated; avoid until clarified |
| [Chinese Grammar Wiki (AllSet)](https://resources.allsetlearning.com/chinese/grammar/) | Best grammar explanations by level | CC BY-NC-SA (non-commercial) |
| Curated lists | [awesome-hackchinese](https://github.com/jay-pee/awesome-hackchinese), [Awesome-Chinese-NLP](https://github.com/crownpku/Awesome-Chinese-NLP) | n/a |

No useful Kaggle dataset turned up; the maintained sources are on GitHub and Hugging Face.

## Proposed single CSV

One row per **word sense**, with grammar points as rows of `type=grammar`:

`id, type(word|char|grammar), simplified, traditional, pinyin_marks, pinyin_numbered, pos, definition,
classifiers, hsk2_level, hsk3_level, frequency_rank, grammar_code, grammar_structure, example_zh,
example_en, example_source, source, license, notes`

Rules: HSK 3.0 is the primary level (it covers both sheets), with HSK 2.0 kept as a secondary column.
Citation-tone pinyin only. Every row carries its source and license, so share-alike and non-commercial
material can be filtered out before any public release.
