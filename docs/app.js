(() => {
  const words = {};
  const chars = {};
  const TIERS = ['simple', 'ordinary', 'complex', 'advanced', 'scholar'];
  const POOL_BASE = window.POOL_BASE || '../data/build/pool/';
  const MARKS_KEY = 'jade-bookmarks-v1';
  const NS = 'http://www.w3.org/2000/svg';
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)');

  const $ = (id) => document.getElementById(id);
  const stage = $('stage');
  const sentenceEl = $('sentence');
  const translationEl = $('translation');
  const nextBtn = $('next');
  const focus = $('focus');
  const panel = $('panel');
  const input = $('q');
  const resultsEl = $('results');

  const settings = load();
  let current = null; // { raw, sentences: [{ tokens, en }], source }
  let stack = []; // zoom levels: {type:'word', w, syl?, ref?, entry?, from?} | {type:'char', w, ci, syl?, entry?, from?}
  let renderId = 0;
  let marks = loadMarks();

  // ---------- settings ----------
  function load() {
    const defaults = { difficulty: 'simple', pinyin: true, trad: false, english: false };
    try {
      const saved = { ...defaults, ...JSON.parse(localStorage.getItem('jade-settings-v3') || '{}') };
      return TIERS.includes(saved.difficulty) ? saved : { ...saved, difficulty: defaults.difficulty };
    } catch { return defaults; }
  }
  function save() {
    try { localStorage.setItem('jade-settings-v3', JSON.stringify(settings)); } catch {}
  }
  function applySettings() {
    document.body.classList.toggle('pinyin', settings.pinyin);
    document.body.classList.toggle('trad', settings.trad);
    document.body.classList.toggle('english', settings.english);
    document.documentElement.lang = settings.trad ? 'zh-Hant' : 'zh-Hans';
    $('t-pinyin').setAttribute('aria-pressed', settings.pinyin);
    $('t-script').setAttribute('aria-pressed', settings.trad);
    $('t-script').textContent = settings.trad ? '繁' : '简';
    $('t-english').setAttribute('aria-pressed', settings.english);
    $('difficulty').value = settings.difficulty;
  }

  const show = (simp, trad) => (settings.trad ? trad || simp : simp);
  const entryOf = (e) => e.entry || words[e.w];
  const wordText = (w, entry = words[w]) => show(w, entry?.t);
  const charText = (e) => [...wordText(e.w, entryOf(e))][e.ci];
  const sylOf = (e) => e.syl || entryOf(e).py;
  const hskLabel = (entry) => {
    const level = entry?.hsk;
    return level ? `HSK ${level === 7 ? '7–9' : level}` : 'Not in HSK 3.0';
  };
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

  // ---------- content ----------
  const pool = { index: null, shards: {} };
  const loadIndex = async () => (pool.index ??= await fetch(POOL_BASE + 'index.json').then((r) => r.json()));
  async function loadShard(file) {
    if (!pool.shards[file]) {
      const shard = await fetch(POOL_BASE + file).then((r) => r.json());
      for (const [k, v] of Object.entries(shard.words)) words[k] ??= v;
      for (const [k, v] of Object.entries(shard.chars)) {
        chars[k] = chars[k]
          ? { m: chars[k].m || v.m, words: [...new Set([...chars[k].words, ...v.words])] }
          : v;
      }
      pool.shards[file] = shard.sentences;
    }
    return pool.shards[file];
  }
  // Uniform over the whole tier: pick a position, find the shard that holds it.
  async function pickSentence() {
    await loadIndex();
    const tier = pool.index.tiers[settings.difficulty];
    if (!tier?.count) throw new Error('empty tier');
    let s;
    for (let tries = 0; tries < 5; tries++) {
      const n = Math.floor(Math.random() * tier.count);
      s = (await loadShard(tier.files[Math.floor(n / pool.index.shardSize)]))[n % pool.index.shardSize];
      if (s !== current?.raw || tier.count === 1) break;
    }
    return { raw: s, sentences: [s], source: s.source };
  }

  // Wait (briefly) for the glyphs a sentence needs, so it is drawn in its real font.
  async function fontsFor(text) {
    if (!document.fonts?.load) return;
    const family = settings.trad ? 'Noto Sans TC' : 'Noto Sans SC';
    await Promise.race([document.fonts.load(`700 48px "${family}"`, text), new Promise((r) => setTimeout(r, 1500))]).catch(() => {});
  }

  // ---------- sentence level ----------
  function renderContent() {
    sentenceEl.innerHTML = '';
    current.sentences.forEach((s, si) => {
      s.tokens.forEach((tok, ti) => {
        const el = document.createElement('span');
        const live = tok.kind === 'word' || tok.kind === 'char';
        el.className = `tok ${tok.kind}`;
        el.dataset.ref = `${si}:${ti}`;
        const py = (tok.py || '').replace(/ /g, '');
        if (live) {
          el.tabIndex = 0;
          el.setAttribute('role', 'button');
          el.setAttribute('aria-label', `${tok.w} ${py}`);
        }
        // .wr runs are what the writing animation draws; .wt holds the real text underneath
        const glyphs = [...show(tok.w, tok.t)].map((c) => `<span class="c wr"><span class="wt">${esc(c)}</span></span>`).join('');
        const pinyin = py ? `<span class="py wr"><span class="wt">${esc(py)}</span></span>` : '<span class="py">&nbsp;</span>';
        el.innerHTML = `${pinyin}<span class="hz">${glyphs}</span>`;
        sentenceEl.appendChild(el);
      });
    });
    const en = current.sentences.map((s) => s.en).filter(Boolean).join(' ');
    translationEl.textContent = en || 'No English translation yet for this sentence.';
    translationEl.classList.toggle('missing', !en);
    stage.scrollTop = 0;
    updateMarkUI();
  }

  // Show a sentence: fade the old one out, then write the new one in.
  async function present(next) {
    if (stack.length) closeFocus(false);
    const id = ++renderId;
    stage.classList.add('swap');
    await Promise.all([fontsFor(next.raw.s + (next.raw.t || '')), new Promise((r) => setTimeout(r, 120))]);
    if (id !== renderId) return;
    current = next;
    renderContent();
    writeSentence();
    stage.classList.remove('swap');
  }

  async function nextSentence() {
    let next;
    try {
      next = await pickSentence();
    } catch {
      sentenceEl.innerHTML = '<span class="error">Couldn’t load sentences. Build the pool and open the app from a web server (see CLAUDE.md), not as a file.</span>';
      stage.classList.remove('swap');
      return;
    }
    present(next);
  }

  // ---------- writing in ----------
  // The stroop writing, as in football explained and freestyle: an SVG copy of each run (a character, or a token's
  // pinyin) is laid exactly over it, one <text> per letter. Each letter's outline is stroked on (one dash and an
  // endless gap, so no part of it can vanish and come back), then inked. Tokens start 1/60 s apart, letters 14 ms.
  // The written copy stays on screen (handing back to the plain text would change the weight at the last moment)
  // and takes the element's colour, so hovers still work. A re-render or a resize clears it.
  const WORD_MS = 1000 / 60;
  const LETTER_MS = 14;

  function clearInk() {
    sentenceEl.querySelectorAll('.wr.writing').forEach((w) => { w.classList.remove('writing'); w.querySelector('svg')?.remove(); });
  }

  function writeRun(w, d0) {
    const box = w.getBoundingClientRect();
    if (!box.width) return;
    // The run's baseline, read from the page's own layout (an empty inline box sits on it).
    const probe = document.createElement('span');
    probe.style.cssText = 'display:inline-block;width:0;height:0;vertical-align:baseline';
    w.firstChild.append(probe);
    const base = probe.getBoundingClientRect().top - box.top;
    probe.remove();
    const cs = getComputedStyle(w);
    const size = parseFloat(cs.fontSize);
    const text = w.firstChild.textContent;
    const g = document.createElementNS(NS, 'svg');
    g.setAttribute('width', box.width);
    g.setAttribute('height', box.height);
    g.setAttribute('aria-hidden', 'true');
    Object.assign(g.style, { fontFamily: cs.fontFamily, fontWeight: cs.fontWeight, fontSize: cs.fontSize, letterSpacing: cs.letterSpacing });
    w.append(g);
    // Each letter goes exactly where the whole run would put it, so spacing is kept.
    const whole = document.createElementNS(NS, 'text');
    whole.setAttribute('x', 0);
    whole.setAttribute('y', base);
    whole.textContent = text;
    g.append(whole);
    let at = 0;
    const letters = [...text].map((ch) => {
      const l = { ch, x: whole.getStartPositionOfChar(at).x, wd: whole.getExtentOfChar(at).width };
      at += ch.length;
      return l;
    });
    whole.remove();
    letters.forEach((l, j) => {
      if (!/\S/.test(l.ch)) return;
      const t = document.createElementNS(NS, 'text');
      t.setAttribute('x', l.x);
      t.setAttribute('y', base);
      t.textContent = l.ch;
      // A generous guess at the outline's length: an overestimate only shifts the timing a little.
      t.style.setProperty('--len', Math.ceil(4 * (l.wd + size * 0.8) + 10));
      t.style.setProperty('--d', `${Math.round(d0 + j * LETTER_MS)}ms`);
      g.append(t);
    });
    w.classList.add('writing');
  }

  function writeSentence() {
    clearInk();
    if (reduceMotion.matches) return;
    sentenceEl.querySelectorAll('.tok').forEach((tok, i) => {
      const d0 = i * WORD_MS;
      const py = tok.querySelector('.py.wr');
      if (py) writeRun(py, d0);
      tok.querySelectorAll('.hz .wr').forEach((c, j) => writeRun(c, d0 + j * LETTER_MS));
    });
  }
  // If the window is resized the text reflows, so the plain text (which moves with it) takes over from the copies.
  addEventListener('resize', clearInk);

  // ---------- focus levels ----------
  function crumbs() {
    if (stack.length < 2) return '';
    const parts = stack.map((e) => (e.type === 'word' ? wordText(e.w, entryOf(e)) : charText(e)));
    return `<div class="crumbs">${parts.join(' › ')}</div>`;
  }

  const starButton = () => {
    const on = isMarked(target()?.key);
    return `<button class="save" aria-pressed="${on}" title="Save (B)">${on ? '★ Saved' : '☆ Save'}</button>`;
  };

  function wordView(e) {
    const w = entryOf(e);
    const single = [...e.w].length === 1;
    const chs = [...wordText(e.w, w)]
      .map((c, i) => `<span class="ch" data-ci="${i}" role="button" tabindex="0">${c}</span>`).join('');
    const defs = w.defs.length ? w.defs : ['Not in the dictionary (often a name or a rare term)'];
    return `<div class="fview word-view">
      ${crumbs()}
      <div class="py">${sylOf(e).join('')}</div>
      <div class="big" lang="zh">${chs}</div>
      <div class="meta">${hskLabel(w)} · ${w.pos || (single ? 'single character' : 'word')}</div>
      ${starButton()}
      <ul class="defs">${defs.map((d) => `<li>${esc(d)}</li>`).join('')}</ul>
    </div>`;
  }

  function charView(e) {
    const c = [...e.w][e.ci];
    ensureChar(c);
    const info = chars[c] || { m: '', words: [] };
    const related = info.words.filter((rw) => words[rw]).map((rw) => `<li><button data-w="${rw}" class="${rw === e.w ? 'current' : ''}">
        <span class="rw" lang="zh">${wordText(rw)}</span>
        <span class="rp">${words[rw].py.join('')} · ${hskLabel(words[rw])}</span>
        <span class="rd">${esc(words[rw].defs[0] || '')}</span>
      </button></li>`).join('');
    const meaning = info.m ? info.m.split(';').map((d) => `<li>${esc(d.trim())}</li>`).join('') : '<li>No meaning on file</li>';
    return `<div class="fview char-view">
      ${crumbs()}
      <div class="py">${sylOf(e)[e.ci] || ''}</div>
      <div class="big" lang="zh"><span>${charText(e)}</span></div>
      <div class="meta">from ${wordText(e.w, entryOf(e))}</div>
      ${starButton()}
      <ul class="defs">${meaning}</ul>
      ${related ? `<section class="related"><h2>Words with ${charText(e)}</h2><ul>${related}</ul></section>` : ''}
    </div>`;
  }

  // Animate the big glyph from where it was clicked (FLIP).
  function flyFrom(el, rect) {
    if (!rect) return;
    const to = el.getBoundingClientRect();
    const s = rect.width / to.width;
    el.style.transition = 'none';
    el.style.transform = `translate(${rect.left - to.left}px, ${rect.top - to.top}px) scale(${s})`;
    el.getBoundingClientRect();
    el.style.transition = 'transform var(--t)';
    el.style.transform = '';
  }

  function renderFocus(fromRect) {
    const top = stack[stack.length - 1];
    focus.innerHTML = top.type === 'word' ? wordView(top) : charView(top);
    focus.classList.add('on');
    focus.scrollTop = 0;
    stage.classList.add('away');
    flyFrom(focus.querySelector('.big'), fromRect);
  }

  function push(entry, fromRect) {
    stack.push(entry);
    renderId++;
    renderFocus(fromRect);
  }

  // Back out one level. Something opened from the lookup or the saved list goes back there.
  function pop() {
    if (!stack.length) return;
    const left = stack.pop();
    if (stack.length) { renderId++; renderFocus(null); return; }
    closeFocus(!left.from, left.ref);
    if (left.from) openPanel(left.from);
  }

  function closeFocus(animate, ref) {
    const id = ++renderId;
    stack = [];
    const big = focus.querySelector('.big');
    const target = ref && sentenceEl.querySelector(`.tok[data-ref="${ref}"] .hz`);
    if (animate && big && target) {
      const from = big.getBoundingClientRect();
      const to = target.getBoundingClientRect();
      big.style.transition = 'transform var(--t)';
      big.style.transform = `translate(${to.left - from.left}px, ${to.top - from.top}px) scale(${to.width / from.width})`;
    }
    focus.classList.remove('on');
    stage.classList.remove('away');
    setTimeout(() => { if (id === renderId) focus.innerHTML = ''; }, animate ? 340 : 0);
  }

  // ---------- English lookup ----------
  // Search data is built offline (lookup.json: HSK words + every word the pool uses). It loads the first time the
  // panel opens; a token index over the English senses gives as-you-type suggestions.
  const look = { ready: null, entries: null, chars: null, tokens: null, sorted: null, byChar: null };
  const TOKEN = /[a-z0-9']+/g;
  const FILLER = new Set(['to', 'a', 'an', 'the']); // senses are stored without them ("to eat" -> "eat")

  function loadLookup() {
    look.ready ??= (async () => {
      await loadIndex();
      const data = await fetch(POOL_BASE + (pool.index.lookup || 'lookup.json')).then((r) => r.json());
      const tokens = new Map();
      const byChar = new Map();
      const add = (map, key, i) => { const list = map.get(key); if (list) { if (list[list.length - 1] !== i) list.push(i); } else map.set(key, [i]); };
      data.entries.forEach((e, i) => {
        e[5].forEach((sense) => (sense.toLowerCase().match(TOKEN) || []).forEach((t) => add(tokens, t, i)));
        for (const c of e[0]) add(byChar, c, i);
      });
      Object.assign(look, { entries: data.entries, chars: data.chars, tokens, byChar, sorted: [...tokens.keys()].sort() });
    })();
    return look.ready;
  }

  const entryWord = (e) => ({ py: e[2].split(' '), defs: e[5], t: e[1] || undefined, hsk: e[3] || undefined, pos: e[4] || undefined });

  // Give a looked-up word's characters a meaning and a related-words list when the pool has none for them.
  function ensureChar(c) {
    if (chars[c]?.words.length || !look.entries) return;
    const ids = (look.byChar.get(c) || []).filter((i) => look.entries[i][0].length > 1)
      .sort((a, b) => (look.entries[a][3] || 9) - (look.entries[b][3] || 9) || look.entries[a][6] - look.entries[b][6]).slice(0, 6);
    ids.forEach((i) => { words[look.entries[i][0]] ??= entryWord(look.entries[i]); });
    chars[c] = { m: chars[c]?.m || look.chars[c] || '', words: ids.map((i) => look.entries[i][0]) };
  }

  function idsWithPrefix(p) {
    const s = look.sorted;
    let lo = 0;
    let hi = s.length;
    while (lo < hi) { const mid = (lo + hi) >> 1; if (s[mid] < p) lo = mid + 1; else hi = mid; }
    const out = new Set();
    for (let i = lo; i < s.length && s[i].startsWith(p) && out.size < 5000; i++) look.tokens.get(s[i]).forEach((x) => out.add(x));
    return out;
  }

  function search(raw, limit = 8) {
    const q = raw.trim().toLowerCase();
    const E = look.entries;
    if (!q || !E) return [];
    const rank = (e) => (e[3] || 8) * 12 + Math.log10(e[6] + 1) * 8;
    if (/[㐀-鿿]/.test(q)) { // Chinese typed: match the word itself
      const out = [];
      E.forEach((e, i) => {
        if (e[0].startsWith(q) || e[1].startsWith(q)) out.push({ i, k: 0, score: (e[0] === q || e[1] === q ? 1000 : 600) - rank(e) - e[0].length * 10 });
      });
      return out.sort((a, b) => b.score - a.score).slice(0, limit);
    }
    const terms = q.match(TOKEN) || [];
    const open = /[a-z0-9']$/.test(q); // still typing the last word: treat it as a prefix
    let prefix = open ? terms.pop() : null;
    const whole = terms.filter((t) => !FILLER.has(t));
    if (prefix && FILLER.has(prefix) && whole.length) prefix = null;
    if (!whole.length && !prefix) return [];
    let ids = null;
    for (const t of whole) {
      const hit = new Set(look.tokens.get(t) || []);
      ids = ids ? new Set([...ids].filter((x) => hit.has(x))) : hit;
    }
    if (prefix) {
      const hit = idsWithPrefix(prefix);
      ids = ids ? new Set([...ids].filter((x) => hit.has(x))) : hit;
    }
    const phrase = [...whole, ...(prefix ? [prefix] : [])].join(' ');
    const out = [];
    for (const i of ids) {
      const e = E[i];
      let best = null;
      e[5].forEach((sense, k) => sense.split(/[;,]\s*/).forEach((part) => { // "to eat; to consume": score each part
        const core = part.toLowerCase().replace(/\([^)]*\)/g, ' ').replace(/\s+/g, ' ').trim().replace(/^(to|a|an|the) /, '');
        const cw = core.match(TOKEN) || [];
        if (!whole.every((t) => cw.includes(t)) || (prefix && !cw.some((x) => x.startsWith(prefix)))) return;
        let score = core === phrase ? 1000 : core.startsWith(phrase) ? 800 : ` ${core}`.includes(` ${phrase}`) ? 600 : 400;
        if (prefix && cw.includes(prefix)) score += 120; // "like" itself, not just "likely"
        score -= k * 25 + core.length * 1.5;
        if (!best || score > best.score) best = { i, k, score };
      }));
      if (best) { best.score -= rank(e); out.push(best); }
    }
    return out.sort((a, b) => b.score - a.score).slice(0, limit);
  }

  let results = [];
  let selected = 0;
  function renderResults() {
    const q = input.value.trim();
    results = search(q);
    selected = Math.min(selected, Math.max(0, results.length - 1));
    const terms = q.toLowerCase().match(TOKEN) || [];
    const mark = (s) => (terms.length ? esc(s).replace(new RegExp(`\\b(${terms.join('|')})`, 'gi'), '<mark>$1</mark>') : esc(s));
    resultsEl.innerHTML = results.map((r, n) => {
      const e = look.entries[r.i];
      return `<li role="option" id="opt-${n}" data-n="${n}" aria-selected="${n === selected}">
        <span class="rw" lang="zh">${esc(show(e[0], e[1]))}</span>
        <span class="rp">${esc(e[2].replace(/ /g, ''))} · ${hskLabel({ hsk: e[3] })}</span>
        <span class="rd">${mark(e[5][r.k])}</span>
      </li>`;
    }).join('');
    input.setAttribute('aria-expanded', results.length > 0);
    input.setAttribute('aria-activedescendant', results.length ? `opt-${selected}` : '');
    $('lookup-hint').textContent = !look.entries ? 'Loading the dictionary…'
      : !q ? 'Try “thank you”, “computer” or “to remember”. Chinese characters work too.'
      : results.length ? '' : 'No match. Try a simpler word.';
  }

  function openResult(n) {
    const r = results[n];
    if (!r) return;
    const e = look.entries[r.i];
    const entry = entryWord(e);
    words[e[0]] ??= entry;
    const rect = resultsEl.querySelector(`[data-n="${n}"] .rw`)?.getBoundingClientRect();
    closePanel();
    if (stack.length) closeFocus(false);
    push({ type: 'word', w: e[0], syl: entry.py, entry, from: 'lookup' }, rect);
  }

  // ---------- bookmarks ----------
  function loadMarks() {
    try { return JSON.parse(localStorage.getItem(MARKS_KEY) || '[]'); } catch { return []; }
  }
  function saveMarks() {
    try { localStorage.setItem(MARKS_KEY, JSON.stringify(marks)); } catch {}
    updateMarkUI();
  }
  // A bookmark carries the word and character data it needs, so it still opens after the pool is rebuilt.
  function pack(list) {
    const p = { words: {}, chars: {} };
    const addWord = (w) => { if (words[w] && !p.words[w]) p.words[w] = words[w]; };
    list.forEach((w) => {
      addWord(w);
      for (const c of w) {
        ensureChar(c);
        if (chars[c] && !p.chars[c]) { p.chars[c] = chars[c]; chars[c].words.forEach(addWord); }
      }
    });
    return p;
  }
  function unpack(p) {
    for (const [k, v] of Object.entries(p?.words || {})) words[k] ??= v;
    for (const [k, v] of Object.entries(p?.chars || {})) chars[k] ??= v;
  }
  // What B / the star saves: the open character or word, else the sentence.
  function target() {
    const top = stack[stack.length - 1];
    if (top) {
      const entry = entryOf(top);
      const base = () => ({ w: top.w, syl: sylOf(top), entry, pack: pack([top.w]) });
      return top.type === 'word'
        ? { key: `w:${top.w}:${entry.py.join('')}`, make: () => ({ kind: 'word', ...base() }) }
        : { key: `c:${[...top.w][top.ci]}`, make: () => ({ kind: 'char', ci: top.ci, ...base() }) };
    }
    if (!current?.raw) return null;
    const s = current.raw;
    return { key: `s:${s.id}`, make: () => ({ kind: 'sentence', s, pack: pack(s.tokens.filter((t) => t.kind === 'word' || t.kind === 'char').map((t) => t.w)) }) };
  }
  const isMarked = (key) => !!key && marks.some((m) => m.key === key);
  function toggleMark() {
    const t = target();
    if (!t) return;
    const i = marks.findIndex((m) => m.key === t.key);
    if (i >= 0) marks.splice(i, 1);
    else marks.unshift({ key: t.key, at: Date.now(), ...t.make() });
    saveMarks();
  }
  function updateMarkUI() {
    $('saved-count').textContent = marks.length || '';
    const on = !!current?.raw && isMarked(`s:${current.raw.id}`);
    const star = $('save-sentence');
    star.setAttribute('aria-pressed', on);
    star.textContent = on ? '★' : '☆';
    star.title = on ? 'Saved (B to remove)' : 'Save this sentence (B)';
    const btn = focus.querySelector('.save');
    if (btn && stack.length) {
      const f = isMarked(target().key);
      btn.setAttribute('aria-pressed', f);
      btn.textContent = f ? '★ Saved' : '☆ Save';
    }
    if (!panel.hidden && panel.dataset.mode === 'saved') renderSaved();
  }

  function renderSaved() {
    const groups = { sentence: [], word: [], char: [] };
    marks.forEach((m, i) => groups[m.kind]?.push([m, i]));
    const row = (i, main, sub) => `<li><button class="open" data-i="${i}">${main}${sub}</button>
      <button class="del" data-del="${i}" aria-label="Remove">×</button></li>`;
    const section = (title, items) => (items.length ? `<h3>${title} <span>${items.length}</span></h3><ul>${items.join('')}</ul>` : '');
    $('saved').innerHTML = marks.length ? [
      section('Sentences', groups.sentence.map(([m, i]) => row(i, `<span class="zh" lang="zh">${esc(show(m.s.s, m.s.t))}</span>`, `<span class="sub">${esc(m.s.en || '')}</span>`))),
      section('Words', groups.word.map(([m, i]) => row(i, `<span class="zh" lang="zh">${esc(show(m.w, m.entry.t))}</span>`,
        `<span class="sub">${esc(m.syl.join(''))} · ${esc(m.entry.defs[0] || '')}</span>`))),
      section('Characters', groups.char.map(([m, i]) => {
        const c = [...m.w][m.ci];
        const meaning = (m.pack.chars[c]?.m || '').split(';')[0];
        return row(i, `<span class="zh" lang="zh">${esc([...show(m.w, m.entry.t)][m.ci])}</span>`,
          `<span class="sub">${esc(m.syl[m.ci] || '')} · ${esc(meaning)} · from ${esc(show(m.w, m.entry.t))}</span>`);
      })),
    ].join('') : '<p class="empty">Nothing saved yet. Press <kbd>B</kbd> or tap ☆ to save the sentence, word or character you are looking at.</p>';
  }

  function openMark(i, rect) {
    const m = marks[i];
    if (!m) return;
    unpack(m.pack);
    closePanel();
    if (m.kind === 'sentence') {
      present({ raw: m.s, sentences: [m.s], source: m.s.source });
      return;
    }
    if (stack.length) closeFocus(false);
    words[m.w] ??= m.entry;
    push(m.kind === 'word'
      ? { type: 'word', w: m.w, syl: m.syl, entry: m.entry, from: 'saved' }
      : { type: 'char', w: m.w, ci: m.ci, syl: m.syl, entry: m.entry, from: 'saved' }, rect);
  }

  // ---------- panel (lookup / saved) ----------
  function openPanel(mode) {
    panel.dataset.mode = mode;
    $('panel-title').textContent = mode === 'lookup' ? 'Look up' : 'Saved';
    $('lookup').hidden = mode !== 'lookup';
    $('saved').hidden = mode !== 'saved';
    panel.hidden = false;
    requestAnimationFrame(() => panel.classList.add('on'));
    if (mode === 'saved') {
      renderSaved();
      $('panel-close').focus();
      return;
    }
    input.focus();
    input.select();
    renderResults();
    loadLookup().then(renderResults).catch(() => { $('lookup-hint').textContent = 'Couldn’t load the dictionary.'; });
  }
  function closePanel() {
    panel.classList.remove('on');
    panel.hidden = true;
    if (document.activeElement && panel.contains(document.activeElement)) document.activeElement.blur();
  }

  // ---------- events ----------
  sentenceEl.addEventListener('click', (e) => {
    const el = e.target.closest('.tok.word, .tok.char');
    if (!el) return;
    const [si, ti] = el.dataset.ref.split(':').map(Number);
    const t = current.sentences[si].tokens[ti];
    const syl = t.py && t.py.includes(' ') ? t.py.split(' ') : null;
    push({ type: 'word', w: t.w, syl, ref: el.dataset.ref }, el.querySelector('.hz').getBoundingClientRect());
  });

  focus.addEventListener('click', (e) => {
    const top = stack[stack.length - 1];
    const ch = e.target.closest('.word-view .ch');
    const rel = e.target.closest('.related button');
    if (e.target.closest('.save')) {
      toggleMark();
    } else if (ch) {
      push({ type: 'char', w: top.w, ci: Number(ch.dataset.ci), syl: top.syl, entry: top.entry, from: top.from }, ch.getBoundingClientRect());
    } else if (rel) {
      if (rel.dataset.w === top.w) { pop(); return; }
      push({ type: 'word', w: rel.dataset.w, from: top.from }, rel.querySelector('.rw').getBoundingClientRect());
    } else if (!e.target.closest('a')) {
      pop();
    }
  });

  input.addEventListener('input', () => { selected = 0; renderResults(); });
  resultsEl.addEventListener('click', (e) => { const li = e.target.closest('li[data-n]'); if (li) openResult(Number(li.dataset.n)); });
  resultsEl.addEventListener('mousemove', (e) => {
    const li = e.target.closest('li[data-n]');
    if (li && Number(li.dataset.n) !== selected) { selected = Number(li.dataset.n); renderResults(); }
  });
  $('saved').addEventListener('click', (e) => {
    const del = e.target.closest('[data-del]');
    const open = e.target.closest('.open');
    if (del) { marks.splice(Number(del.dataset.del), 1); saveMarks(); }
    else if (open) openMark(Number(open.dataset.i), open.querySelector('.zh')?.getBoundingClientRect());
  });
  panel.addEventListener('click', (e) => { if (e.target === panel) closePanel(); });
  $('panel-close').addEventListener('click', closePanel);
  $('b-lookup').addEventListener('click', () => openPanel('lookup'));
  $('b-saved').addEventListener('click', () => openPanel('saved'));
  $('save-sentence').addEventListener('click', () => { if (!stack.length) toggleMark(); });

  function toggle(key) {
    settings[key] = !settings[key];
    save();
    applySettings();
    if (key === 'trad' && current) {
      renderContent();
      if (stack.length) renderFocus(null);
    }
    if (key === 'trad' && !panel.hidden) panel.dataset.mode === 'saved' ? renderSaved() : renderResults();
  }

  $('t-pinyin').addEventListener('click', () => toggle('pinyin'));
  $('t-script').addEventListener('click', () => toggle('trad'));
  $('t-english').addEventListener('click', () => toggle('english'));
  nextBtn.addEventListener('click', nextSentence);
  $('difficulty').addEventListener('change', (e) => {
    settings.difficulty = e.target.value;
    save();
    applySettings();
    e.target.blur();
    nextSentence();
  });
  // Buttons should never keep focus, so Space can't re-trigger them.
  document.querySelectorAll('.controls button, #next, #save-sentence').forEach((b) => b.addEventListener('click', () => b.blur()));

  window.addEventListener('keydown', (e) => {
    if (!panel.hidden) {
      if (e.key === 'Escape') { e.preventDefault(); closePanel(); return; }
      if (e.target !== input) return;
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault();
        if (results.length) { selected = (selected + (e.key === 'ArrowDown' ? 1 : results.length - 1)) % results.length; renderResults(); }
      } else if (e.key === 'Enter') {
        e.preventDefault();
        openResult(selected);
      }
      return; // typing: no global shortcuts
    }
    if (e.target.tagName === 'SELECT' && e.code !== 'Space') return;
    if (e.code === 'Space') {
      e.preventDefault();
      if (!e.repeat) nextSentence();
    } else if (e.key === 'Escape') {
      pop();
    } else if (e.key === 'Enter' && e.target.matches('.tok, .ch')) {
      e.preventDefault();
      e.target.click();
    } else if (e.key === '/' && !e.ctrlKey && !e.metaKey) {
      e.preventDefault();
      openPanel('lookup');
    } else if (!e.ctrlKey && !e.metaKey && !e.altKey) {
      const key = e.key.toLowerCase();
      if (key === 'b') toggleMark();
      const k = { p: 'pinyin', s: 'trad', e: 'english' }[key];
      if (k) toggle(k);
    }
  }, true);
  window.addEventListener('keyup', (e) => { if (e.code === 'Space' && e.target !== input) e.preventDefault(); }, true);

  // ---------- start ----------
  applySettings();
  updateMarkUI();
  nextSentence();
})();
