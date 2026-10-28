(() => {
  const words = {};
  const chars = {};
  const TIERS = ['simple', 'ordinary', 'complex', 'advanced', 'scholar'];
  const POOL_BASE = window.POOL_BASE || '../data/build/pool/';

  const $ = (id) => document.getElementById(id);
  const stage = $('stage');
  const sentenceEl = $('sentence');
  const translationEl = $('translation');
  const sourceEl = $('source');
  const nextBtn = $('next');
  const focus = $('focus');

  const settings = load();
  let current = null; // { raw, sentences: [{ tokens, en }], source }
  let stack = []; // zoom levels: {type:'word', w, syl?, ref?} | {type:'char', w, ci, syl?}
  let renderId = 0;

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

  const show = (simp, trad) => (settings.trad ? trad ?? simp : simp);
  const wordText = (w) => show(w, words[w]?.t);
  const charText = (w, ci) => [...wordText(w)][ci];
  const sylOf = (e) => e.syl || words[e.w].py;
  const hskLabel = (w) => {
    const level = words[w]?.hsk;
    return level ? `HSK ${level === 7 ? '7–9' : level}` : 'Not in HSK 3.0';
  };
  const esc = (s) => s.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

  // ---------- content ----------
  const pool = { index: null, shards: {} };
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
    pool.index ??= await fetch(POOL_BASE + 'index.json').then((r) => r.json());
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
        el.innerHTML = `<span class="py">${py || '&nbsp;'}</span><span class="hz">${esc(show(tok.w, tok.t))}</span>`;
        sentenceEl.appendChild(el);
      });
    });
    const en = current.sentences.map((s) => s.en).filter(Boolean).join(' ');
    translationEl.textContent = en || 'No English translation yet for this sentence.';
    translationEl.classList.toggle('missing', !en);
    sourceEl.innerHTML = sourceHtml(current.source);
    stage.scrollTop = 0;
  }

  function sourceHtml(src) {
    if (!src) return '';
    const link = (text) => (src.url ? `<a href="${esc(src.url)}" target="_blank" rel="noopener">${esc(text)}</a>` : esc(text));
    const from = src.type === 'wikipedia' ? `From Wikipedia: ${link(src.title)} · ${esc(src.license)}`
      : src.type === 'tatoeba' ? `From Tatoeba: ${link(src.title)} · ${esc(src.license)}`
      : `Grammar example: ${esc(src.title)} · lesson ${link(src.code)}`;
    return from + (src.translation && settings.english ? `<br>English: ${esc(src.translation)}` : '');
  }

  async function nextSentence() {
    if (stack.length) closeFocus(false);
    const id = ++renderId;
    stage.classList.add('swap');
    let next;
    try {
      next = await pickSentence();
    } catch {
      sentenceEl.innerHTML = '<span class="error">Couldn’t load sentences. Build the pool and open the app from a web server (see CLAUDE.md), not as a file.</span>';
      stage.classList.remove('swap');
      return;
    }
    setTimeout(() => {
      if (id !== renderId) return;
      current = next;
      renderContent();
      stage.classList.remove('swap');
    }, 180);
  }

  // ---------- focus levels ----------
  function crumbs() {
    if (stack.length < 2) return '';
    const parts = stack.map((e) => (e.type === 'word' ? wordText(e.w) : charText(e.w, e.ci)));
    return `<div class="crumbs">${parts.join(' › ')}</div>`;
  }

  function wordView(e) {
    const w = words[e.w];
    const single = [...e.w].length === 1;
    const chs = [...wordText(e.w)]
      .map((c, i) => `<span class="ch" data-ci="${i}" role="button" tabindex="0">${c}</span>`).join('');
    const defs = w.defs.length ? w.defs : ['Not in the dictionary (often a name or a rare term)'];
    return `<div class="fview word-view">
      ${crumbs()}
      <div class="py">${sylOf(e).join('')}</div>
      <div class="big" lang="zh">${chs}</div>
      <div class="meta">${hskLabel(e.w)} · ${w.pos || (single ? 'single character' : 'word')}</div>
      <ul class="defs">${defs.map((d) => `<li>${esc(d)}</li>`).join('')}</ul>
    </div>`;
  }

  function charView(e) {
    const c = [...e.w][e.ci];
    const info = chars[c] || { m: '', words: [] };
    const related = info.words.filter((rw) => words[rw]).map((rw) => `<li><button data-w="${rw}" class="${rw === e.w ? 'current' : ''}">
        <span class="rw" lang="zh">${wordText(rw)}</span>
        <span class="rp">${words[rw].py.join('')} · ${hskLabel(rw)}</span>
        <span class="rd">${esc(words[rw].defs[0] || '')}</span>
      </button></li>`).join('');
    const meaning = info.m ? info.m.split(';').map((d) => `<li>${esc(d.trim())}</li>`).join('') : '<li>No meaning on file</li>';
    return `<div class="fview char-view">
      ${crumbs()}
      <div class="py">${sylOf(e)[e.ci] || ''}</div>
      <div class="big" lang="zh"><span>${charText(e.w, e.ci)}</span></div>
      <div class="meta">from ${wordText(e.w)}</div>
      <ul class="defs">${meaning}</ul>
      ${related ? `<section class="related"><h2>Words with ${charText(e.w, e.ci)}</h2><ul>${related}</ul></section>` : ''}
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

  function pop() {
    if (!stack.length) return;
    const left = stack.pop();
    if (stack.length) { renderId++; renderFocus(null); return; }
    closeFocus(true, left.ref);
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
    if (ch) {
      push({ type: 'char', w: top.w, ci: Number(ch.dataset.ci), syl: top.syl }, ch.getBoundingClientRect());
    } else if (rel) {
      if (rel.dataset.w === top.w) { pop(); return; }
      push({ type: 'word', w: rel.dataset.w }, rel.querySelector('.rw').getBoundingClientRect());
    } else if (!e.target.closest('a')) {
      pop();
    }
  });

  function toggle(key) {
    settings[key] = !settings[key];
    save();
    applySettings();
    if ((key === 'trad' || key === 'english') && current) {
      renderContent();
      if (stack.length) renderFocus(null);
    }
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
  document.querySelectorAll('.controls button, #next').forEach((b) => b.addEventListener('click', () => b.blur()));

  window.addEventListener('keydown', (e) => {
    if (e.target.tagName === 'SELECT' && e.code !== 'Space') return;
    if (e.code === 'Space') {
      e.preventDefault();
      if (!e.repeat) nextSentence();
    } else if (e.key === 'Escape') {
      pop();
    } else if (e.key === 'Enter' && e.target.matches('.tok, .ch')) {
      e.preventDefault();
      e.target.click();
    } else if (!e.ctrlKey && !e.metaKey && !e.altKey) {
      const k = { p: 'pinyin', s: 'trad', e: 'english' }[e.key.toLowerCase()];
      if (k) toggle(k);
    }
  }, true);
  window.addEventListener('keyup', (e) => { if (e.code === 'Space') e.preventDefault(); }, true);

  // ---------- start ----------
  applySettings();
  nextSentence();
})();
