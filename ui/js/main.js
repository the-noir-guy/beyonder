(function () {
  'use strict';
  var BYD = window.BYD, h = BYD.h;
  var $ = function (s) { return document.querySelector(s); };
  var stage = $('#stage'), elBrowsers = $('#browsers'), elViews = $('#views');
  var S = { browsers: [], stats: { browsers: 0, profiles: 0, launches: 0 }, current: null };
  var ST = { theme: 'system', autostart: true, minimize_after_launch: true, close_action: 'tray', sort: 'manual',
             hotkey_enabled: false, hotkey: 'Ctrl+Alt+B', hotkey_status: 'off' };

  function pad2(n) { return String(n).padStart(2, '0'); }
  function cur() { return S.browsers.find(function (b) { return b.name === S.current; }) || null; }
  function idxOf(name) { return S.browsers.findIndex(function (b) { return b.name === name; }); }
  function letter(name) { return BYD.firstLetter(name); }

  // ───────── stats ─────────
  function renderStats() {
    $('#st-browsers').textContent = pad2(S.stats.browsers);
    $('#st-profiles').textContent = pad2(S.stats.profiles);
    $('#st-launches').textContent = pad2(S.stats.launches);
    $('#add-profile').disabled = !cur();
  }

  // ───────── browser row ─────────
  function renderBrowsers() {
    elBrowsers.replaceChildren();
    S.browsers.forEach(function (b) {
      var sel = b.name === S.current;
      var inner = b.icon_url ? h('img', { src: b.icon_url, alt: '', draggable: 'false' }) : letter(b.name);
      var ti = h('span', { class: 'ti ch' }, inner);
      if (b.icon_url) inner.addEventListener('error', function () { ti.textContent = letter(b.name); });
      var btn = h('button', { class: 'tc tc-b' + (sel ? ' sel' : ''), type: 'button', role: 'tab', 'aria-selected': sel ? 'true' : 'false', 'aria-label': b.name },
        h('span', { class: 'tw ch ' + (sel ? 'rb' : 'rbp') }, ti),
        h('span', { class: 'mono', text: b.name }));
      btn._name = b.name;
      btn.addEventListener('click', function () { selectBrowser(b.name); });
      btn.addEventListener('contextmenu', function (e) {
        e.preventDefault();
        var items = [
          { label: 'Open', run: function () { openBrowser(b); } },
          { label: 'Remove', run: function () { removeBrowser(b); } }
        ];
        // the Default profile (it only starts the browser) can be brought back from here when it was removed
        if (!b.has_default) items.push({ label: 'Add to Profiles', run: function () { addDefaultProfile(b); } });
        openMenu(e.clientX, e.clientY, items);
      });
      elBrowsers.append(btn);
    });
    var add = h('button', { class: 'tc tc-add', type: 'button', 'aria-label': 'Add browser' },
      h('span', { class: 'tw ch rbp' }, h('span', { class: 'ti plus ch', text: '+' })),
      h('span', { class: 'mono', text: 'New' }));
    add.addEventListener('click', addBrowser);
    elBrowsers.append(add);
    updateExtra();
  }

  // extra browser rows push the profile panel down so nothing overlaps
  function updateExtra() {
    var kids = Array.prototype.slice.call(elBrowsers.children);
    if (!kids.length) return;
    var tops = {};
    kids.forEach(function (k) { tops[k.offsetTop] = 1; });
    var rows = Object.keys(tops).length;
    var extra = Math.min((rows - 1) * (kids[0].offsetHeight + 16), 214);
    stage.style.setProperty('--extra', extra + 'px');
  }

  // ───────── profile panel ─────────
  var io = null;

  // the display order follows the default sort; b.profiles itself always stays in manual order
  function sortedProfiles(b) {
    var list = b.profiles.map(function (p, i) { return { p: p, i: i }; });
    if (ST.sort === 'most_used') {
      list.sort(function (a, c) { return ((c.p.uses || 0) - (a.p.uses || 0)) || (a.i - c.i); });
    } else if (ST.sort === 'recent') {
      list.sort(function (a, c) { return ((c.p.last || 0) - (a.p.last || 0)) || (a.i - c.i); });
    }
    return list.map(function (x) { return x.p; });
  }

  function buildView(b) {
    var view = h('div', { class: 'view' });
    if (!b) {
      view.append(h('div', { class: 'empty', text: 'Add a browser to get started.' }));
    } else if (!b.profiles.length) {
      view.append(h('div', { class: 'empty', text: 'Add a profile to get started.' }));
    } else {
      var grid = h('div', { class: 'grid' });
      sortedProfiles(b).forEach(function (p) { grid.append(card(b, p)); });
      view.append(grid);
    }
    return view;
  }

  // the round picture of a card: the saved picture, or a tile in the profile's colour with its first letter
  function avatarEl(p) {
    var av = h('span', { class: 'av' }, h('span', { class: 'ring' }));
    function fallback() {
      var c = BYD.tileColors(p.key, p.color);
      av.style.background = c.bg;
      av.insertBefore(BYD.initialSvg(letter(p.name), c.fg), av.firstChild);   // the same helper as the Edit Profile popup
    }
    if (p.avatar_url) {
      var img = h('img', { src: p.avatar_url, alt: '', draggable: 'false' });
      img.addEventListener('error', function () { img.remove(); fallback(); });
      av.insertBefore(img, av.firstChild);
    } else {
      fallback();
    }
    return av;
  }

  function card(b, p) {
    var av = avatarEl(p);
    var btn = h('button', { class: 'cw rbp', type: 'button', 'aria-label': 'Launch ' + p.name },
      h('span', { class: 'c' }, av, h('span', { class: 'nm', text: p.name })),
      h('span', { class: 'dtag', 'aria-hidden': 'true', text: '[ LINK LOST ]' }));
    btn.addEventListener('click', function () { launch(b, p); });
    btn.addEventListener('contextmenu', function (e) {
      e.preventDefault();
      openMenu(e.clientX, e.clientY, [
        { label: 'Edit', run: function () { editProfile(b, p); } },
        { label: 'Remove', run: function () { removeProfile(b, p); } }
      ]);
    });
    var wrap = h('div', { class: 'cwrap' }, btn);
    wrap._p = p;
    wrap.style.setProperty('--dd', '-' + (Math.random() * 6).toFixed(2) + 's');   // so the infected cards do not flicker in sync
    setDead(wrap, !!p.dead);
    return wrap;
  }

  // a card whose linked shortcut is gone: red border and the infected look (see .cwrap.dead in style.css)
  function setDead(wrap, dead) {
    wrap.classList.toggle('dead', !!dead);
    var btn = wrap.querySelector('.cw');
    if (btn && wrap._p) btn.setAttribute('aria-label', 'Launch ' + wrap._p.name + (dead ? ' (link lost)' : ''));
  }

  var deadBusy = false, deadLast = 0;
  async function refreshDead(force) {
    var now = Date.now();
    if (deadBusy || (!force && now - deadLast < 1500)) return;
    deadBusy = true;
    deadLast = now;
    try {
      var r = await BYD.call('check_links');
      if (!r || !r.ok || !r.dead) return;
      var dead = {};
      r.dead.forEach(function (d) { dead[d[0] + '\u0000' + d[1]] = true; });
      S.browsers.forEach(function (b) {
        b.profiles.forEach(function (p) { p.dead = !!dead[b.name + '\u0000' + p.key]; });
      });
      elViews.querySelectorAll('.cwrap').forEach(function (w) { if (w._p) setDead(w, w._p.dead); });
    } finally { deadBusy = false; }
  }

  function watchCards(view) {
    if (view._io) view._io.disconnect();
    if (!('IntersectionObserver' in window)) return;
    var obs = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) { en.target.classList.toggle('off', !en.isIntersecting); });
    }, { root: view, rootMargin: '60px' });
    view.querySelectorAll('.cwrap').forEach(function (c) { obs.observe(c); });
    view._io = obs;
  }

  // the previous browser's view is replaced at once: no transition, so nothing can overlap
  function showPanel(o) {
    o = o || {};
    var b = cur();
    $('#panel-title').textContent = (b ? b.name : 'No browser') + ' // ' + pad2(b ? b.profiles.length : 0) + ' profiles';

    var prevScroll = 0;
    elViews.querySelectorAll('.view').forEach(function (v) {
      if (o.keepScroll) prevScroll = v.scrollTop;
      if (v._io) v._io.disconnect();
      v.remove();
    });

    var view = buildView(b);
    elViews.append(view);
    scroller.suppress();
    if (prevScroll) view.scrollTop = prevScroll;
    watchCards(view);
    scroller.attach(view);
  }

  function renderAll(o) {
    renderBrowsers();
    renderStats();
    showPanel(o);
  }

  // ───────── glitch on browser switch (Medium): stepped band shift, colour split, thick bars ─────────
  var GL = { scale: 55, split: 6, steps: 9, ms: 400, lines: 7 };
  var RAINBOW = 'linear-gradient(90deg,#ff6b9d,#ff5fe0,#8a7dff,#3df0ff,#ffb28a)';
  function rnd(a, b) { return a + Math.random() * (b - a); }
  function pick(a) { return a[Math.floor(Math.random() * a.length)]; }

  function fxParts(id) {
    var f = document.getElementById(id);
    if (!f) return null;
    return { id: id, tok: 0, turb: f.querySelector('.turb'), disp: f.querySelector('.disp'),
             offR: f.querySelector('.offR'), offGB: f.querySelector('.offGB') };
  }
  var FX = { view: fxParts('fxView'), tile: fxParts('fxTile') };

  // bends the real content with a filter that is re-rolled every step; the filter is removed when it ends
  function distort(target, fx, shake) {
    if (!target || !fx) return;
    var tok = ++fx.tok, t0 = performance.now(), last = -1, raf = 0, dead = false;
    target.style.filter = 'url(#' + fx.id + ')';
    function finish() {
      if (dead) return;
      dead = true;
      cancelAnimationFrame(raf);
      target.style.filter = '';
      target.style.transform = '';
    }
    function tick(now) {
      if (dead) return;
      if (fx.tok !== tok) { finish(); return; }          // a newer glitch took over this filter
      var p = (now - t0) / GL.ms;
      if (p >= 1) { finish(); return; }
      var step = Math.min(GL.steps - 1, Math.floor(p * GL.steps));
      if (step !== last) {
        last = step;
        var env = Math.pow(1 - p, 0.6) * rnd(0.55, 1.15);
        fx.turb.setAttribute('seed', String(Math.floor(rnd(1, 999))));
        fx.turb.setAttribute('baseFrequency', '0.0008 ' + rnd(0.015, 0.11).toFixed(4));
        fx.disp.setAttribute('scale', (GL.scale * env).toFixed(1));
        var sp = GL.split * env * rnd(0.4, 1.2);
        fx.offR.setAttribute('dx', sp.toFixed(1));
        fx.offGB.setAttribute('dx', (-sp).toFixed(1));
        if (shake) target.style.transform = 'translateX(' + (rnd(-1, 1) * GL.split * env).toFixed(1) + 'px)';
      }
      raf = requestAnimationFrame(tick);
    }
    raf = requestAnimationFrame(tick);
  }

  function barHeight() {
    var r = Math.random();
    if (r < 0.15) return rnd(2, 3.5);
    if (r < 0.75) return rnd(6, 16);
    return rnd(16, 28);
  }
  function makeBar(box, x, y, w, h) {
    var d = document.createElement('i'), r = Math.random();
    d.style.left = x.toFixed(1) + 'px';
    d.style.top = y.toFixed(1) + 'px';
    d.style.width = w.toFixed(1) + 'px';
    d.style.height = h.toFixed(1) + 'px';
    if (r < 0.62) {
      d.style.background = 'var(--ink)';
      if (Math.random() < 0.5) d.style.boxShadow = '-4px 0 0 #ff3d8b, 4px 0 0 #3df0ff';
    } else if (r < 0.82) {
      d.style.background = pick(['#ff3d8b', '#3df0ff', '#8a7dff']);
    } else {
      d.style.background = RAINBOW;
    }
    d.style.opacity = rnd(0.8, 1).toFixed(2);
    box.appendChild(d);
  }

  // thick white and colored bars on the card borders, across the cards and as long streaks
  var barsTok = 0;
  function bars() {
    var box = $('#fxlines'), panel = $('#panel-in');
    if (!box || !panel) return;
    var tok = ++barsTok, t0 = performance.now(), last = -1;
    function tick(now) {
      if (tok !== barsTok) return;
      var p = (now - t0) / GL.ms;
      if (p >= 1) { box.replaceChildren(); return; }
      var step = Math.min(GL.steps - 1, Math.floor(p * GL.steps));
      if (step !== last) {
        last = step;
        box.replaceChildren();
        var sc = BYD.scale || 1, pr = panel.getBoundingClientRect(), pw = pr.width / sc, ph = pr.height / sc;
        var cards = Array.prototype.map.call(elViews.querySelectorAll('.cw'), function (c) {
          var r = c.getBoundingClientRect();
          return { x: (r.left - pr.left) / sc, y: (r.top - pr.top) / sc, w: r.width / sc, h: r.height / sc };
        }).filter(function (c) { return c.y > 20 && c.y + c.h < ph + 30; });
        var n = Math.round(GL.lines * (1 - p * 0.65) * rnd(0.7, 1.25));
        for (var i = 0; i < n; i++) {
          var h = barHeight(), kind = Math.random(), c = cards.length ? pick(cards) : null;
          if (c && kind < 0.5) {
            var edge = Math.random() < 0.5 ? c.y : c.y + c.h;
            makeBar(box, c.x + rnd(-24, 12), edge - h / 2 + rnd(-3, 3), c.w * rnd(0.5, 1.4), h);
          } else if (c && kind < 0.8) {
            makeBar(box, c.x + rnd(-10, c.w * 0.5), c.y + rnd(0, c.h - h), c.w * rnd(0.4, 1.2), h);
          } else {
            makeBar(box, rnd(0, pw * 0.4), rnd(30, Math.max(31, ph - h)), pw * rnd(0.3, 0.9), h);
          }
        }
      }
      requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
  }

  function glitch() {
    if (BYD.REDUCED) return;
    distort(elViews.querySelector('.view'), FX.view, true);
    distort(elBrowsers.querySelector('.tc.sel'), FX.tile, false);
    bars();
  }

  function selectBrowser(name) {
    if (name === S.current) return;
    var prev = idxOf(S.current);
    S.current = name;
    renderBrowsers();
    renderStats();
    showPanel({ animate: true, dir: idxOf(name) >= prev ? 1 : -1, keepScroll: false });
    glitch();
  }

  // new state from Python
  function applyState(res, o) {
    o = o || {};
    if (!res || !res.ok || !res.state) return false;
    var prevCur = S.current, prevIdx = idxOf(prevCur);
    S.browsers = res.state.browsers;
    S.stats = res.state.stats;
    var target = prevCur;
    var renamed = !!(o.renamed && o.renamed.from === prevCur);
    if (renamed) target = o.renamed.to;
    if (o.select && idxOf(o.select) >= 0) target = o.select;
    if (idxOf(target) < 0) {
      target = S.browsers.length ? S.browsers[Math.min(Math.max(prevIdx, 0), S.browsers.length - 1)].name : null;
    }
    var changed = target !== prevCur && !renamed;
    S.current = target;
    var newIdx = idxOf(target);
    renderAll({ animate: changed, dir: newIdx >= prevIdx ? 1 : -1, keepScroll: !changed });
    return true;
  }

  // ───────── scroll indicator (overlay, draggable, fades after 5 s) ─────────
  var scroller = (function () {
    var bar = $('#sbar'), thumb = $('#sthumb');
    var view = null, hideTimer = null, dragging = false, hovering = false, quietUntil = 0, grab = 0;
    var thumbH = 30, maxTop = 0, maxScroll = 0;

    function measure() {
      if (!view) return false;
      maxScroll = view.scrollHeight - view.clientHeight;
      if (maxScroll <= 1) return false;
      var trackH = bar.clientHeight;
      thumbH = Math.max(28, Math.round(trackH * (view.clientHeight / view.scrollHeight)));
      thumbH = Math.min(thumbH, trackH);
      maxTop = Math.max(1, trackH - thumbH);
      return true;
    }
    function place() {
      if (!measure()) return false;
      thumb.style.height = thumbH + 'px';
      thumb.style.transform = 'translateY(' + (view.scrollTop / maxScroll) * maxTop + 'px)';
      return true;
    }
    function arm() {
      clearTimeout(hideTimer);
      if (dragging || hovering) return;
      hideTimer = setTimeout(function () { bar.classList.remove('on'); }, 5000);
    }
    function show() { bar.classList.add('on'); arm(); }
    function onScroll() {
      if (performance.now() < quietUntil) return;
      if (place()) show();
    }
    function scrollFromPointer(clientY) {
      if (!measure()) return;
      var y = (clientY - bar.getBoundingClientRect().top) / BYD.scale;
      var top = Math.min(maxTop, Math.max(0, y - grab));
      view.scrollTop = (top / maxTop) * maxScroll;
      place();
    }

    bar.addEventListener('pointerdown', function (e) {
      if (e.button !== 0 || !measure()) return;
      e.preventDefault();
      var y = (e.clientY - bar.getBoundingClientRect().top) / BYD.scale;
      var cur = (view.scrollTop / maxScroll) * maxTop;
      grab = (e.target === thumb || thumb.contains(e.target)) ? y - cur : thumbH / 2;
      bar.setPointerCapture(e.pointerId);
      dragging = true;
      bar.classList.add('drag');
      clearTimeout(hideTimer);
      scrollFromPointer(e.clientY);
    });
    bar.addEventListener('pointermove', function (e) { if (dragging) scrollFromPointer(e.clientY); });
    var end = function () {
      if (!dragging) return;
      dragging = false;
      bar.classList.remove('drag');
      arm();
    };
    bar.addEventListener('pointerup', end);
    bar.addEventListener('pointercancel', end);
    bar.addEventListener('pointerenter', function () { hovering = true; clearTimeout(hideTimer); });
    bar.addEventListener('pointerleave', function () { hovering = false; arm(); });

    if ('ResizeObserver' in window) new ResizeObserver(function () { if (view) place(); }).observe(elViews);

    return {
      attach: function (v) {
        if (view) view.removeEventListener('scroll', onScroll);
        view = v;
        view.addEventListener('scroll', onScroll, { passive: true });
        clearTimeout(hideTimer);
        bar.classList.remove('on', 'drag');
        dragging = false;
        place();
      },
      suppress: function () { quietUntil = performance.now() + 200; }
    };
  })();

  // ───────── right-click menu ─────────
  var menuEl = null, swallow = false;
  function openMenu(cx, cy, items) {
    closeMenu();
    var m = h('div', { id: 'menu', role: 'menu' }, h('div', { class: 'mborder' }, h('div', { class: 'mclip' },
      items.map(function (it) {
        var b = h('button', { class: 'mi' + (it.danger ? ' danger' : '') + (it.active ? ' active' : ''), type: 'button', role: 'menuitem', text: it.label });
        b.addEventListener('click', function () { closeMenu(); it.run(); });
        return b;
      }))));
    $('#menu-layer').append(m);
    var p = BYD.stagePoint(cx, cy);
    var w = 172, hgt = items.length * 34 + 16;
    m.style.left = Math.max(6, Math.min(p.x, BYD.W - w - 6)) + 'px';
    m.style.top = Math.max(6, Math.min(p.y, BYD.H - hgt - 6)) + 'px';
    menuEl = m;
    var first = m.querySelector('.mi');
    if (first && !(cx || cy)) first.focus();
  }
  function closeMenu() {
    if (menuEl) { menuEl.remove(); menuEl = null; }
  }
  document.addEventListener('pointerdown', function (e) {
    if (menuEl && !menuEl.contains(e.target)) {
      closeMenu();
      if (e.button === 0) { swallow = true; e.preventDefault(); }
    }
  }, true);
  document.addEventListener('click', function (e) {
    if (swallow) { swallow = false; e.stopPropagation(); e.preventDefault(); }
  }, true);
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && menuEl) closeMenu(); });
  window.addEventListener('resize', closeMenu);
  window.addEventListener('wheel', closeMenu, { passive: true });

  // ───────── actions ─────────
  // the Add button: scans this PC for browsers and lets you pick which ones to add
  function addBrowser() {
    BYD.dialogs.browsers({ onSaved: function (res) { applyState(res, { select: res.added && res.added[0] }); } });
  }
  function failedRestore(r) {
    if (r && !r.internal && r.error) BYD.dialogs.notice('Couldn\'t restore it', r.error);
  }
  // Remove happens at once and a small toast offers Undo for 5 seconds (the folder is kept, so Undo is lossless)
  async function removeBrowser(b) {
    var snap = { name: b.name, index: idxOf(b.name) };
    if (!applyState(await BYD.call('remove_browser', b.name))) return;
    BYD.toast({
      text: 'Browser removed // ' + snap.name,
      onUndo: async function () {
        var r = await BYD.call('restore_browser', snap.name, snap.index);
        if (!applyState(r, { select: snap.name })) failedRestore(r);
      }
    });
  }
  // Add Profiles is the import button of the selected browser (its popup is the next step)
  async function addProfiles() {
    var b = cur();
    if (!b) return;
    if (b.supported === false) {                        // a browser without profiles (Opera, Tor...): the notice opens at once
      BYD.dialogs.notice('Not supported yet', b.unsupported_text || 'Profile import isn\'t supported for this browser yet.');
      return;
    }
    BYD.dialogs.profiles({ browser: b, onSaved: function (res) { applyState(res, { select: b.name }); } });
  }
  async function addDefaultProfile(b) {
    var r = await BYD.call('add_default_profile', b.name);
    if (!applyState(r, { select: b.name }) && r && !r.internal && r.error) BYD.dialogs.notice('Couldn\'t add it', r.error);
  }
  function editProfile(b, p) {
    BYD.dialogs.profile({ browser: b, profile: p, onSaved: function (res) { applyState(res, { select: b.name }); } });
  }
  async function openBrowser(b) {
    var r = await BYD.call('open_browser', b.name);
    if (r && r.notice) BYD.dialogs.notice(r.notice.title, r.notice.text);
    else if (r && !r.ok && !r.internal && r.error) BYD.dialogs.notice('Couldn\'t open it', r.error);
  }
  async function removeProfile(b, p) {
    var snap = { browser: b.name, key: p.key, name: p.name, index: b.profiles.indexOf(p),
                 data: { key: p.key, name: p.name, source_name: p.source_name, renamed: !!p.renamed, color: p.color || '',
                         args: p.args || [], avatar_custom: !!p.avatar_custom } };
    if (!applyState(await BYD.call('remove_profile', b.name, p.key))) return;
    BYD.toast({
      text: 'Profile removed // ' + snap.name,
      onUndo: async function () {
        var r = await BYD.call('restore_profile', snap.browser, snap.key, snap.data, snap.index);
        if (!applyState(r, { select: snap.browser })) failedRestore(r);
      }
    });
  }
  var launching = false;
  async function launch(b, p) {
    if (launching) return;
    launching = true;
    try {
      var r = await BYD.call('launch_profile', b.name, p.key);
      if (r.ok && r.stats) {
        S.stats = r.stats;
        p.uses = (p.uses || 0) + 1;                 // the card order only follows this on the next redraw
        p.last = Date.now() / 1000;
        renderStats();
      } else if (r.notice) { BYD.dialogs.notice(r.notice.title, r.notice.text); refreshDead(true); }
      else if (r.error && !r.internal) { BYD.dialogs.notice('Couldn\'t open it', r.error); refreshDead(true); }
    } finally { launching = false; }
  }
  $('#add-profile').addEventListener('click', addProfiles);

  // ───────── keyboard: arrows move between profile cards, Enter launches, Ctrl+1..9 switches browser ─────────
  function mainBlocked() { return $('#main-ui').inert || !!menuEl || !!drag || !!pend; }
  function typing(t) {
    return !!t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.tagName === 'SELECT' || t.isContentEditable);
  }

  function stepCard(key) {
    var cards = Array.prototype.slice.call(elViews.querySelectorAll('.view .cw'));
    if (!cards.length) return;
    var at = cards.indexOf(document.activeElement), next = at;
    if (at < 0) {
      next = 0;
    } else if (key === 'ArrowRight') {
      next = Math.min(cards.length - 1, at + 1);
    } else if (key === 'ArrowLeft') {
      next = Math.max(0, at - 1);
    } else {
      var rects = cards.map(function (c) { return c.getBoundingClientRect(); });
      var r0 = rects[at], cx = r0.left + r0.width / 2, dir = key === 'ArrowDown' ? 1 : -1;
      var rowGap = null, best = -1, bestDx = Infinity;
      rects.forEach(function (r) {
        var d = (r.top - r0.top) * dir;
        if (d > 4 && (rowGap === null || d < rowGap)) rowGap = d;       // the nearest row in that direction
      });
      if (rowGap !== null) {
        rects.forEach(function (r, i) {
          if (Math.abs((r.top - r0.top) * dir - rowGap) > 4) return;
          var dx = Math.abs(r.left + r.width / 2 - cx);                   // the card closest to where we are
          if (dx < bestDx) { bestDx = dx; best = i; }
        });
        if (best >= 0) next = best;
      }
    }
    if (next !== at || at < 0) cards[next].focus();
  }

  document.addEventListener('keydown', function (e) {
    if (e.defaultPrevented || e.isComposing || mainBlocked() || typing(e.target)) return;
    if (e.ctrlKey && !e.altKey && !e.shiftKey && !e.metaKey) {
      var m = /^(?:Digit|Numpad)([1-9])$/.exec(e.code || '');
      if (m) {
        e.preventDefault();
        var target = S.browsers[parseInt(m[1], 10) - 1];
        if (target) selectBrowser(target.name);
      }
      return;
    }
    if (e.ctrlKey || e.altKey || e.metaKey || e.shiftKey) return;
    if (e.key === 'ArrowLeft' || e.key === 'ArrowRight' || e.key === 'ArrowUp' || e.key === 'ArrowDown') {
      e.preventDefault();
      stepCard(e.key);
    }
  });

  // a shortcut can disappear while Beyonder sits in the tray: look again whenever the window comes back
  window.addEventListener('focus', function () { refreshDead(); });
  document.addEventListener('visibilitychange', function () { if (!document.hidden) refreshDead(); });

  // ───────── drag to reorder: browsers in the top row, profile cards in the panel ─────────
  // Pointer based (the stage is scaled, so native drag and drop would misplace things). The card follows the
  // pointer and moves to the slot of any card it is dragged over; the others glide out of the way.
  var DRAG_PX = 6;
  var pend = null, drag = null, dragSuppress = false;

  function dragItems(d) {
    if (d.kind === 'browser') return Array.prototype.slice.call(elBrowsers.querySelectorAll('.tc-b'));
    return Array.prototype.slice.call(d.container.children);
  }
  function dragOrder(d) {
    return dragItems(d).map(function (el) { return d.kind === 'browser' ? el._name : el._p.key; });
  }

  document.addEventListener('pointerdown', function (e) {
    if (e.button !== 0 || pend || drag || swallow) return;
    if (mainBlocked() || document.body.classList.contains('intro')) return;
    var t = e.target, el = null, kind = null;
    if (t && t.closest) {
      el = t.closest('#browsers .tc-b');
      if (el) kind = 'browser';
      else { el = t.closest('#views .cwrap'); if (el) kind = 'profile'; }
    }
    if (!el) return;
    pend = { kind: kind, el: el, id: e.pointerId, x0: e.clientX, y0: e.clientY, x: e.clientX, y: e.clientY };
    document.addEventListener('pointermove', onDragMove);
    document.addEventListener('pointerup', onDragEnd);
    document.addEventListener('pointercancel', onDragEnd);
  });

  function onDragMove(e) {
    var s = pend || drag;
    if (!s || e.pointerId !== s.id) return;
    s.x = e.clientX;
    s.y = e.clientY;
    if (pend) {
      if (Math.abs(s.x - s.x0) + Math.abs(s.y - s.y0) < DRAG_PX) return;
      beginDrag();
    }
    if (drag) dragUpdate();
  }

  function beginDrag() {
    var d = pend;
    pend = null;
    drag = d;
    var rect = d.el.getBoundingClientRect();
    d.gx = d.x0 - rect.left;
    d.gy = d.y0 - rect.top;
    d.container = d.kind === 'browser' ? elBrowsers : d.el.parentNode;
    d.holder = d.kind === 'browser' ? elBrowsers : elViews;
    d.start = dragOrder(d);
    d.last = null;
    dragSuppress = true;                                  // the click that follows the drop must not launch anything
    try { d.holder.setPointerCapture(d.id); } catch (ex) { /* the document listeners still follow the pointer */ }
    d.el.classList.add('dragging');
    document.body.classList.add('dragmode');
    if (d.kind === 'profile') d.raf = requestAnimationFrame(dragScroll);
  }

  function dragUpdate() {
    var d = drag;
    if (!d) return;
    var el = d.el, all = dragItems(d), target = null, sc = BYD.scale || 1;
    for (var i = 0; i < all.length; i++) {
      if (all[i] === el) continue;
      var r = all[i].getBoundingClientRect();
      if (d.x >= r.left && d.x <= r.right && d.y >= r.top && d.y <= r.bottom) { target = all[i]; break; }
    }
    // d.last stops a card that is still gliding away from being picked again straight after the swap
    if (target && target !== d.last) {
      var from = all.indexOf(el), to = all.indexOf(target);
      var before = all.map(function (n) { return n === el ? null : n.getBoundingClientRect(); });
      if (from < to) d.container.insertBefore(el, target.nextSibling);
      else d.container.insertBefore(el, target);
      if (!BYD.REDUCED) {
        all.forEach(function (n, k) {
          if (n === el || !n.animate) return;
          var a = n.getBoundingClientRect(), b = before[k];
          var dx = (b.left - a.left) / sc, dy = (b.top - a.top) / sc;
          if (Math.abs(dx) < 1 && Math.abs(dy) < 1) return;
          n.animate([{ transform: 'translate(' + dx + 'px,' + dy + 'px)' }, { transform: 'translate(0px,0px)' }],
            { duration: 170, easing: 'cubic-bezier(.22,.8,.3,1)' });
        });
      }
    }
    d.last = target;
    el.style.transform = '';                              // measure where the card sits in the layout...
    var base = el.getBoundingClientRect();
    var tx = (d.x - d.gx - base.left) / sc, ty = (d.y - d.gy - base.top) / sc;
    el.style.transform = 'translate(' + tx + 'px,' + ty + 'px) scale(1.05)';   // ...and keep it under the pointer
  }

  // dragging a profile near the top or bottom edge of the panel scrolls it
  function dragScroll() {
    var d = drag;
    if (!d || d.kind !== 'profile') return;
    var view = elViews.querySelector('.view');
    if (view) {
      var sc = BYD.scale || 1, r = view.getBoundingClientRect(), edge = 56 * sc, v = 0;
      if (d.y < r.top + edge) v = -(r.top + edge - d.y) / sc / 4;
      else if (d.y > r.bottom - edge) v = (d.y - (r.bottom - edge)) / sc / 4;
      v = Math.max(-18, Math.min(18, v));
      if (Math.abs(v) >= 1) { view.scrollTop += v; dragUpdate(); }
    }
    d.raf = requestAnimationFrame(dragScroll);
  }

  function onDragEnd(e) {
    var s = pend || drag;
    if (s && e && e.pointerId !== undefined && e.pointerId !== s.id) return;
    document.removeEventListener('pointermove', onDragMove);
    document.removeEventListener('pointerup', onDragEnd);
    document.removeEventListener('pointercancel', onDragEnd);
    if (pend) { pend = null; return; }                    // it was just a click
    var d = drag;
    if (!d) return;
    drag = null;
    cancelAnimationFrame(d.raf);
    try { d.holder.releasePointerCapture(d.id); } catch (ex) { /* already released */ }
    document.body.classList.remove('dragmode');
    var el = d.el, held = el.style.transform;
    el.classList.remove('dragging');
    el.style.transform = '';
    if (!BYD.REDUCED && el.animate && held) {             // settle into the slot
      el.animate([{ transform: held }, { transform: 'translate(0px,0px) scale(1)' }],
        { duration: 170, easing: 'cubic-bezier(.22,.8,.3,1)' });
    }
    setTimeout(function () { dragSuppress = false; }, 80);
    commitOrder(d);
  }

  document.addEventListener('click', function (e) {
    if (dragSuppress) { e.stopPropagation(); e.preventDefault(); }
  }, true);

  function reordered(list, names, key) {
    var by = {};
    list.forEach(function (x) { by[x[key]] = x; });
    var next = names.map(function (n) { return by[n]; }).filter(Boolean);
    list.forEach(function (x) { if (next.indexOf(x) < 0) next.push(x); });
    return next;
  }

  async function commitOrder(d) {
    var names = dragOrder(d);
    if (names.join('\u0000') === d.start.join('\u0000')) return;     // dropped where it was
    var r;
    if (d.kind === 'browser') {
      S.browsers = reordered(S.browsers, names, 'name');
      r = await BYD.call('reorder_browsers', names);
      if (!r || !r.ok) applyState(await BYD.call('get_state'));
      return;
    }
    var b = cur();
    if (!b) return;
    b.profiles = reordered(b.profiles, names, 'key');
    r = await BYD.call('reorder_profiles', b.name, names);
    if (!r || !r.ok) { applyState(await BYD.call('get_state')); return; }
    if (ST.sort !== 'manual') {                           // dragging while sorted turns the order you see into the manual one
      var r2 = await BYD.call('set_setting', 'sort', 'manual');
      if (r2 && r2.ok) ST.sort = 'manual';
    }
  }

  // the tray menu launched something while the window was closed: reload what is on screen
  window.__bydRefresh = async function () {
    if (drag || pend) return;
    var r = await BYD.call('get_state');
    if (r && r.ok) applyState(r);
  };

  // ───────── startup ─────────
  // ───────── settings (gear button) and theme: Light / Dark / System ─────────
  function takeSettings(st) {
    ST.theme = st.theme || 'system';
    ST.autostart = st.autostart !== false;
    ST.minimize_after_launch = st.minimize_after_launch !== false;
    ST.close_action = st.close_action === 'quit' ? 'quit' : 'tray';
    ST.sort = (st.sort === 'most_used' || st.sort === 'recent') ? st.sort : 'manual';
    ST.hotkey_enabled = !!st.hotkey_enabled;
    ST.hotkey = st.hotkey || 'Ctrl+Alt+B';
    ST.hotkey_status = st.hotkey_status || 'off';
  }

  async function loadTheme() {
    var root = document.documentElement;
    var st = await BYD.call('get_settings');
    if (st && st.ok) {
      takeSettings(st);
      BYD.theme.mode = st.theme;
      root.setAttribute('data-theme', st.resolved === 'light' ? 'light' : 'dark');
    } else {
      root.setAttribute('data-theme', 'dark');
    }
  }

  async function chooseMode(mode) {
    var r = await BYD.call('set_theme', mode);
    if (!r || !r.ok) return false;
    BYD.theme.mode = mode;
    ST.theme = mode;
    BYD.switchTheme(r.resolved);
    return true;
  }

  // every Settings change is applied at once; resolves true when it went through
  async function changeSetting(key, value) {
    if (key === 'theme') return chooseMode(value);
    var r = await BYD.call('set_setting', key, value);
    if (!r || !r.ok) {
      if (r && !r.internal && r.error) BYD.dialogs.notice('Couldn\'t change it', r.error);
      return false;
    }
    ST[key] = value;
    if (r.hotkey_status) ST.hotkey_status = r.hotkey_status;
    if (key === 'sort') showPanel({ keepScroll: true });
    return true;
  }

  async function setHotkey(keys) {
    var r = await BYD.call('set_hotkey', keys);
    if (r && r.ok) {
      ST.hotkey = r.hotkey;
      ST.hotkey_status = r.hotkey_status;
      return { ok: true, keys: r.hotkey, status: r.hotkey_status };
    }
    return { ok: false, error: (r && r.error) || 'Could not set that shortcut.' };
  }

  // the settings and the state of a restored backup replace everything on screen
  function adoptSettings(st) {
    if (!st) return;
    takeSettings(st);
    BYD.theme.mode = st.theme;
    BYD.switchTheme(st.resolved);
  }

  async function exportBackup() {
    var r = await BYD.call('export_backup');
    if (!r || !r.ok) {
      if (r && !r.internal && r.error) await BYD.dialogs.notice('Couldn\'t save it', r.error);
      return;
    }
    if (r.cancelled) return;
    await BYD.dialogs.notice('Backup saved', r.path);
  }

  async function restoreBackup() {
    var pick = await BYD.call('pick_file', 'backup');
    if (!pick || !pick.ok || !pick.path) return;
    var ok = await BYD.dialogs.confirm({
      title: '[ RESTORE BACKUP? ]',
      text: 'Everything in your data folder is replaced with this backup:\n' + pick.path +
        '\n\nA copy of your current data is saved next to the data folder first.',
      confirmLabel: 'Restore'
    });
    if (!ok) return;
    var r = await BYD.call('restore_backup', pick.path);
    if (!r || !r.ok) {
      if (r && !r.internal && r.error) await BYD.dialogs.notice('Couldn\'t restore it', r.error);
      return;
    }
    if (settingsCtl) settingsCtl.close();
    adoptSettings(r.settings);
    applyState(r);
    BYD.dialogs.notice('Backup restored', 'Your previous data was saved to:\n' + r.safety);
  }

  function openRemoved() {
    var ctl = BYD.dialogs.removed({ onState: function (res, o) { applyState(res, o); } });
    return ctl.whenClosed;
  }

  var settingsCtl = null;
  function openSettings() {
    if ($('#main-ui').inert || settingsCtl) return;
    closeMenu();
    settingsCtl = BYD.dialogs.settings({
      values: ST,
      onChange: changeSetting,
      actions: { setHotkey: setHotkey, exportBackup: exportBackup, restoreBackup: restoreBackup, removed: openRemoved }
    });
    settingsCtl.whenClosed.then(function () { settingsCtl = null; });
  }
  $('#btn-settings').addEventListener('click', openSettings);

  // Windows changed its color mode while Beyonder is set to System
  window.__bydSystemTheme = function (resolved) {
    if (BYD.theme.mode === 'system') BYD.switchTheme(resolved);
  };

  function intro() {
    var wm = $('#wordmark'), targets = [elBrowsers, $('#panel'), $('#stats')];
    var finish = function () {
      document.body.classList.remove('pre', 'intro');
      [wm].concat(targets).forEach(function (el) { el.getAnimations().forEach(function (a) { a.cancel(); }); });
    };
    if (BYD.REDUCED || !wm.animate) { finish(); return; }
    var anims = [];
    anims.push(wm.animate([{ clipPath: 'inset(100% 0 0 0)' }, { clipPath: 'inset(0% 0 0 0)' }], { duration: 800, easing: 'cubic-bezier(.65,0,.35,1)', fill: 'both' }));
    anims.push(elBrowsers.animate([{ opacity: 0, transform: 'translateY(-22px)' }, { opacity: 1, transform: 'translateY(0)' }],
      { duration: 550, delay: 800, easing: 'cubic-bezier(.22,.8,.3,1)', fill: 'both' }));
    var rise = { duration: 600, delay: 800 + Math.round(0.45 * 550), easing: 'cubic-bezier(.22,.8,.3,1)', fill: 'both' };
    anims.push($('#panel').animate([{ opacity: 0, transform: 'translateY(24px)' }, { opacity: 1, transform: 'translateY(0)' }], rise));
    anims.push($('#stats').animate([{ opacity: 0, transform: 'translateY(24px)' }, { opacity: 1, transform: 'translateY(0)' }], rise));
    document.body.classList.remove('pre');
    Promise.all(anims.map(function (a) { return a.finished; })).then(finish, finish);
    setTimeout(finish, 3500);
  }

  // fonts come through Python as raw bytes, which WebView2 accepts from any page address
  async function loadFonts() {
    var r = await BYD.call('get_fonts');
    if (!r.ok || !r.fonts) return;
    var families = { heading: 'BYD Heading', accent: 'BYD Accent', body: 'BYD Body', button: 'BYD Button' };
    await Promise.all(Object.keys(families).map(async function (key) {
      var b64 = r.fonts[key];
      if (!b64) { BYD.logJs('error', 'Font file not found for ' + key + ' (assets/fonts)'); return; }
      try {
        var bin = atob(b64), bytes = new Uint8Array(bin.length);
        for (var i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
        var face = new FontFace(families[key], bytes.buffer, { weight: '100 900', style: 'normal' });
        await face.load();
        document.fonts.add(face);
      } catch (ex) {
        BYD.logJs('error', 'Font ' + key + ' failed to load: ' + ex);
      }
    }));
  }

  async function boot() {
    await loadTheme();
    await loadFonts();
    try {
      var mx = await BYD.call('is_maximized');
      if (mx && mx.ok && window.__bydMaxState) window.__bydMaxState(mx.maximized);
    } catch (ex) { /* the window state is only cosmetic */ }
    var r = await BYD.call('get_state');
    if (r.ok && r.state) {
      S.browsers = r.state.browsers;
      S.stats = r.state.stats;
      S.current = S.browsers.length ? S.browsers[0].name : null;
    } else if (!r.internal) {
      BYD.showError('Could not load your data: ' + (r.error || 'unknown error'));
    }
    renderAll({});
    await BYD.fontsReady();
    updateExtra();
    intro();
  }
  boot();
})();
