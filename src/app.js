(() => {
  const { sentences, words, chars } = window.APP_DATA;
  const BUCKETS = { simple: [1, 2], conversational: [3, 4], difficult: [5, 6] };

  const $ = (id) => document.getElementById(id);
  const stage = $('stage');
  const sentenceEl = $('sentence');
  const translationEl = $('translation');
  const focus = $('focus');

  const settings = load();
  let current = null;
  let stack = []; // zoom levels above the sentence: {type:'word', w, tokenIndex?} | {type:'char', w, ci}
  let renderId = 0;

  // ---------- settings ----------
  function load() {
    const defaults = { difficulty: 'simple', pinyin: true, trad: false, english: false };
    try { return { ...defaults, ...JSON.parse(localStorage.getItem('jade-settings-v2') || '{}') }; }
    catch { return defaults; }
  }
  function save() {
    try { localStorage.setItem('jade-settings-v2', JSON.stringify(settings)); } catch {}
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

  const show = (simp, trad) => (settings.trad ? trad : simp);
  const wordText = (w) => show(w, words[w].t);
  const charText = (w, ci) => [...wordText(w)][ci];

  // ---------- sentence level ----------
  function pickSentence() {
    const [lo, hi] = BUCKETS[settings.difficulty];
    const pool = sentences.filter((s) => s.level >= lo && s.level <= hi && s !== current);
    return pool[Math.floor(Math.random() * pool.length)] || current;
  }

  function renderSentence() {
    sentenceEl.innerHTML = '';
    current.tokens.forEach((tok, i) => {
      const el = document.createElement('span');
      el.className = `tok ${tok.kind}`;
      el.dataset.i = i;
      if (tok.kind !== 'punct') {
        el.tabIndex = 0;
        el.setAttribute('role', 'button');
        el.setAttribute('aria-label', `${tok.w} ${tok.py}`);
      }
      el.innerHTML = `<span class="py">${tok.py || '&nbsp;'}</span><span class="hz">${show(tok.w, tok.t)}</span>`;
      sentenceEl.appendChild(el);
    });
    translationEl.textContent = current.en;
  }

  function nextSentence() {
    if (stack.length) closeFocus(false);
    current = pickSentence();
    stage.classList.add('swap');
    setTimeout(() => { renderSentence(); stage.classList.remove('swap'); }, 180);
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
    return `<div class="fview word-view">
      ${crumbs()}
      <div class="py">${w.py.join('')}</div>
      <div class="big" lang="zh">${chs}</div>
      <div class="meta">HSK ${w.hsk} · ${single ? 'single character' : 'word'}</div>
      <ul class="defs">${w.defs.map((d) => `<li>${d}</li>`).join('')}</ul>
    </div>`;
  }

  function charView(e) {
    const c = [...e.w][e.ci];
    const info = chars[c];
    const related = info.words.map((rw) => `<li><button data-w="${rw}" class="${rw === e.w ? 'current' : ''}">
        <span class="rw" lang="zh">${wordText(rw)}</span>
        <span class="rp">${words[rw].py.join('')} · HSK ${words[rw].hsk}</span>
        <span class="rd">${words[rw].defs[0]}</span>
      </button></li>`).join('');
    return `<div class="fview char-view">
      ${crumbs()}
      <div class="py">${words[e.w].py[e.ci]}</div>
      <div class="big" lang="zh"><span>${charText(e.w, e.ci)}</span></div>
      <div class="meta">from ${wordText(e.w)}</div>
      <ul class="defs">${info.m.split(';').map((d) => `<li>${d.trim()}</li>`).join('')}</ul>
      <section class="related">
        <h2>Words with ${charText(e.w, e.ci)}</h2>
        <ul>${related}</ul>
      </section>
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
    stage.classList.add('away');
    flyFrom(focus.querySelector('.big'), fromRect);
  }

  function push(entry, fromRect) {
    disarm();
    stack.push(entry);
    renderId++;
    renderFocus(fromRect);
  }

  function pop() {
    if (!stack.length) return;
    disarm();
    const left = stack.pop();
    if (stack.length) { renderId++; renderFocus(null); return; }
    closeFocus(true, left.tokenIndex);
  }

  function closeFocus(animate, tokenIndex) {
    const id = ++renderId;
    stack = [];
    const big = focus.querySelector('.big');
    const target = tokenIndex != null && sentenceEl.querySelector(`.tok[data-i="${tokenIndex}"] .hz`);
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

  function disarm() {
    document.querySelectorAll('.armed').forEach((el) => el.classList.remove('armed'));
  }

  // ---------- events ----------
  sentenceEl.addEventListener('click', (e) => {
    const tok = e.target.closest('.tok.word, .tok.char');
    if (!tok) return;
    const t = current.tokens[tok.dataset.i];
    push({ type: 'word', w: t.w, tokenIndex: Number(tok.dataset.i) }, tok.querySelector('.hz').getBoundingClientRect());
  });

  focus.addEventListener('click', (e) => {
    const top = stack[stack.length - 1];
    const ch = e.target.closest('.word-view .ch');
    const rel = e.target.closest('.related button');
    if (ch) {
      push({ type: 'char', w: top.w, ci: Number(ch.dataset.ci) }, ch.getBoundingClientRect());
    } else if (rel) {
      if (rel.dataset.w === top.w) { pop(); return; }
      push({ type: 'word', w: rel.dataset.w }, rel.querySelector('.rw').getBoundingClientRect());
    } else {
      pop();
    }
  });

  function toggle(key) {
    settings[key] = !settings[key];
    save();
    applySettings();
    if (key === 'trad') {
      renderSentence();
      if (stack.length) renderFocus(null);
    }
  }

  $('t-pinyin').addEventListener('click', () => toggle('pinyin'));
  $('t-script').addEventListener('click', () => toggle('trad'));
  $('t-english').addEventListener('click', () => toggle('english'));
  $('next').addEventListener('click', nextSentence);
  $('difficulty').addEventListener('change', (e) => {
    settings.difficulty = e.target.value;
    save();
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
  current = pickSentence();
  renderSentence();
})();
