(function () {
  'use strict';
  var BYD = window.BYD, h = BYD.h;
  var layer = document.getElementById('modal-layer');
  var mainUi = document.getElementById('main-ui');
  var stack = [];
  var FOCUSABLE = 'button:not([disabled]),input:not([disabled]),[tabindex]:not([tabindex="-1"])';

  function frame() {
    return '<svg class="ovl-frame" viewBox="0 0 ' + BYD.W + ' ' + BYD.H + '" fill="none" stroke="currentColor" aria-hidden="true">' + BYD.frameSvg(BYD.W, BYD.H, true) + '</svg>';
  }

  function refreshInert() {
    var live = stack.filter(function (m) { return !m.closed; });
    mainUi.inert = live.length > 0;
    live.forEach(function (m, i) { m.ovl.inert = i !== live.length - 1; });
  }

  function fitTitle(el) {
    var size = 34;
    el.style.fontSize = size + 'px';
    while (el.scrollWidth > el.clientWidth + 1 && size > 16) {
      size -= 1;
      el.style.fontSize = size + 'px';
    }
  }


  // ───────── popup wipe (entrance and exit) ─────────
  // A glitch line travels down the popup; the popup is revealed exactly down to the line. The exit is the exact reverse.
  var WIPE_CAP = 600, WIPE_TAIL = 180, LINE_PX = 6, BAR_K = 0.85, BAR_N = 6;
  var RAINBOW = 'linear-gradient(90deg,#ff6b9d,#ff5fe0,#8a7dff,#3df0ff,#ffb28a)';
  var rnd = function (a, b) { return a + Math.random() * (b - a); };
  var pick = function (a) { return a[Math.floor(Math.random() * a.length)]; };

  // 1 ms per 1 px of popup height; a popup taller than WIPE_CAP uses the static WIPE_CAP ms instead
  function wipeMs(dlg) {
    return Math.max(1, Math.min(Math.round(dlg.offsetHeight), WIPE_CAP));
  }

  function barHeight() {
    var r = Math.random();
    return BAR_K * (r < 0.15 ? rnd(2, 3.5) : r < 0.75 ? rnd(6, 16) : rnd(16, 28));
  }
  function makeBar(box, x, y, w, hh) {
    var d = document.createElement('i'), r = Math.random();
    d.style.left = x.toFixed(1) + 'px'; d.style.top = y.toFixed(1) + 'px';
    d.style.width = w.toFixed(1) + 'px'; d.style.height = hh.toFixed(1) + 'px';
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

  // returns { done: Promise, stop: fn } ; stop() snaps to the end state at once
  function wipe(dir, dlg, glow, pw, D) {
    var out = dir === 'out', T = WIPE_TAIL;
    var ease = out ? 'cubic-bezier(.7,0,.4,1)' : 'cubic-bezier(.6,0,.3,1)';
    var H = dlg.offsetHeight, W = dlg.offsetWidth, M = '-150px';
    pw.replaceChildren();
    var ln = document.createElement('div'), bx = document.createElement('div');
    ln.className = 'dlg-ln'; bx.className = 'dlg-bx';
    pw.append(ln, bx);
    var o = { duration: D, easing: ease, fill: 'both', delay: out ? T : 0 };
    var a = dlg.animate(out ? [{ clipPath: 'inset(0 0 0 0)' }, { clipPath: 'inset(0 0 100% 0)' }]
                            : [{ clipPath: 'inset(0 0 100% 0)' }, { clipPath: 'inset(0 0 0 0)' }], o);
    var l = ln.animate(out ? [{ transform: 'translateY(' + H + 'px)' }, { transform: 'translateY(0px)' }]
                           : [{ transform: 'translateY(0px)' }, { transform: 'translateY(' + H + 'px)' }], o);
    // the glow is clipped by the same moving edge as the popup; once the line is at the bottom the part below the popup is let out
    var s = out ? T / (D + T) : D / (D + T);
    var full = 'inset(' + M + ' ' + M + ' ' + M + ' ' + M + ')', edge = 'inset(' + M + ' ' + M + ' 0px ' + M + ')', none = 'inset(0px ' + M + ' 100% ' + M + ')';
    var g = glow.animate(out ? [{ clipPath: full, offset: 0, easing: 'linear' }, { clipPath: edge, offset: s, easing: ease }, { clipPath: none, offset: 1 }]
                             : [{ clipPath: none, offset: 0, easing: ease }, { clipPath: edge, offset: s, easing: 'linear' }, { clipPath: full, offset: 1 }],
                         { duration: D + T, fill: 'both' });

    var running = true, last = 0, t0 = performance.now(), startAt = out ? T : 0;
    ln.style.visibility = out ? 'hidden' : '';
    function endGlitch() {
      if (!running) return;
      running = false;
      pw.replaceChildren();
    }
    (function tick(now) {
      if (!running) return;
      if (now - t0 >= startAt) {
        if (ln.style.visibility) ln.style.visibility = '';
        if (now - last > 45) {
          last = now;
          bx.replaceChildren();
          var y0 = ln.getBoundingClientRect().top - pw.getBoundingClientRect().top;
          y0 = y0 / (BYD.scale || 1) + LINE_PX / 2;
          var n = Math.round(BAR_N * rnd(0.7, 1.25));
          for (var i = 0; i < n; i++) {
            var bh = barHeight(), w = W * rnd(0.15, 0.75), x = rnd(0, W - w);
            var y = Math.max(0, Math.min(H - bh, y0 + rnd(-60, 60) - bh / 2));
            makeBar(bx, x, y, w, bh);
          }
        }
      }
      requestAnimationFrame(tick);
    })(t0);

    var done = new Promise(function (resolve) {
      // the line and the bars end the instant the popup is complete; only the glow's short tail runs on afterwards
      Promise.all([a.finished, l.finished]).then(function () {
        endGlitch();
        if (!out) { a.cancel(); l.cancel(); }
      }, endGlitch);
      g.finished.then(function () {
        endGlitch();
        if (!out) g.cancel();
        resolve();
      }, function () { endGlitch(); resolve(); });
    });
    return {
      done: done,
      stop: function () {
        endGlitch();
        if (!out) { a.cancel(); l.cancel(); g.cancel(); }
      }
    };
  }

  BYD.openModal = function (spec) {
    var ctl = { closed: false, busy: false, animating: false, spec: spec, buttons: {} };
    var prevFocus = document.activeElement;

    var title = h('h2', { class: 'dtitle', text: spec.title });
    var btnRow = h('div', { class: 'dbtns' });
    (spec.buttons || []).forEach(function (b) {
      var btn;
      if (b.primary) {
        btn = h('button', { class: 'wbtn', type: 'button', text: b.label });
        btnRow.append(h('div', { class: 'bslot' }, h('div', { class: 'wb' }, btn)));
      } else {
        btn = h('button', { class: 'bi btn', type: 'button', text: b.label });
        btnRow.append(h('div', { class: 'bslot' }, h('div', { class: 'bwb' }, btn)));
      }
      btn.addEventListener('click', function () { if (!ctl.busy && !ctl.animating) b.onClick(ctl); });
      ctl.buttons[b.id || b.label] = btn;
    });

    var body = h('div', { class: 'dbody' },
      h('div', { class: 'dmeta' }, h('span', { class: 'mono w', text: spec.meta || '' }), h('span', { class: 'hz' })),
      title, spec.content || [], btnRow);
    var dlg = h('div', { class: 'dlg', role: 'dialog', 'aria-modal': 'true', 'aria-label': spec.title },
      h('div', { class: 'dlg-bw rb' },
        h('div', { class: 'dlg-in' }, body)));
    var bg = h('div', { class: 'ovl-bg' }, h('div', { class: 'dim' }));
    bg.insertAdjacentHTML('beforeend', frame());
    var glow = h('div', { class: 'dlg-glow' }, h('div', { class: 'dlg-gs' }));
    var pw = h('div', { class: 'dlg-pw' });
    var pos = h('div', { class: 'dlg-pos' }, h('div', { class: 'dlg-wrap' }, glow, dlg, pw));
    var ovl = h('div', { class: 'ovl' }, bg, pos);

    // a click on the empty area around the popup closes it like Escape does; a press that started inside
    // the popup (selecting text, dragging the zoom slider) and ends outside does not count
    var pressedOutside = false;
    ovl.addEventListener('pointerdown', function (e) {
      pressedOutside = e.button === 0 && !dlg.contains(e.target);
    });
    ovl.addEventListener('pointerup', function (e) {
      var was = pressedOutside;
      pressedOutside = false;
      if (was && e.button === 0 && !dlg.contains(e.target) && !ctl.busy && !ctl.animating && !ctl.closed) ctl.cancel();
    });

    ctl.el = dlg;
    ctl.ovl = ovl;
    ctl.title = title;
    ctl.whenClosed = new Promise(function (r) { ctl._resolve = r; });

    ctl.setBusy = function (b) {
      ctl.busy = !!b;
      dlg.classList.toggle('busy', !!b);
    };
    ctl.submit = function () { if (!ctl.busy && !ctl.animating && spec.onSubmit) spec.onSubmit(ctl); };
    ctl.cancel = function () { if (spec.onCancel) spec.onCancel(ctl); else ctl.close(); };
    ctl.focusFirst = function () {
      var t = spec.focus ? spec.focus() : null;
      if (!t) t = dlg.querySelector('input') || dlg.querySelector('.wbtn') || dlg.querySelector('button');
      if (t) t.focus();
    };
    ctl.close = function (result) {
      if (ctl.closed) return;
      ctl.closed = true;
      ctl.result = result;
      var idx = stack.indexOf(ctl);
      if (idx >= 0) stack.splice(idx, 1);
      var live = stack.filter(function (m) { return !m.closed; });
      mainUi.inert = live.length > 0;
      live.forEach(function (m, i) { m.ovl.inert = i !== live.length - 1; });
      var finish = function () {
        ovl.remove();
        var top = stack[stack.length - 1];
        if (top) { top.ovl.inert = false; if (top.lastFocus && document.body.contains(top.lastFocus)) top.lastFocus.focus(); }
        else if (prevFocus && document.body.contains(prevFocus) && prevFocus.focus) prevFocus.focus();
        ctl._resolve(result);
      };
      if (BYD.REDUCED || !pos.animate) { finish(); return; }
      if (ctl._wipe) { ctl._wipe.stop(); ctl._wipe = null; }
      ctl.animating = true;
      var D = wipeMs(dlg), T = WIPE_TAIL;
      bg.animate([{ opacity: 1 }, { opacity: 0 }], { duration: D, delay: T, easing: 'ease-in', fill: 'forwards' });
      var w = wipe('out', dlg, glow, pw, D);
      w.done.then(finish, finish);
    };

    stack.forEach(function (m) { m.lastFocus = document.activeElement; });
    stack.push(ctl);
    layer.append(ovl);
    refreshInert();
    fitTitle(title);
    if (BYD.fontsReady) BYD.fontsReady().then(function () { fitTitle(title); });

    if (!BYD.REDUCED && pos.animate) {
      ctl.animating = true;
      var D = wipeMs(dlg);
      bg.animate([{ opacity: 0 }, { opacity: 1 }], { duration: D, easing: 'ease-out' });
      ctl._wipe = wipe('in', dlg, glow, pw, D);
      ctl._wipe.done.then(function () { ctl._wipe = null; if (!ctl.closed) ctl.animating = false; });
    }
    requestAnimationFrame(function () { if (!ctl.closed) ctl.focusFirst(); });
    return ctl;
  };

  document.addEventListener('keydown', function (e) {
    if (!stack.length) return;
    var top = stack[stack.length - 1];
    if (top.closed) return;
    if (e.key === 'Escape') {
      e.preventDefault(); e.stopImmediatePropagation();
      if (!top.busy && !top.animating) top.cancel();
      return;
    }
    if (e.key === 'Enter' && !e.isComposing) {
      var t = e.target;
      if (t && (t.tagName === 'BUTTON' || t.tagName === 'TEXTAREA')) return;
      e.preventDefault();
      top.submit();
      return;
    }
    if (e.key === 'Tab') {
      var items = Array.prototype.filter.call(top.el.querySelectorAll(FOCUSABLE), function (n) { return n.offsetParent !== null; });
      if (!items.length) return;
      var first = items[0], last = items[items.length - 1], cur = document.activeElement;
      var inside = top.el.contains(cur);
      if (e.shiftKey && (!inside || cur === first)) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && (!inside || cur === last)) { e.preventDefault(); first.focus(); }
    }
  }, true);

  // ───────── helpers for popup content ─────────
  var ui = BYD.ui = {};

  // the loading mark ("segment bar"): 8 blocks with a three-block light wave (cyan, hot pink, head) running left to right,
  // and a label under it. The colours and the timing are in style.css (.segbar)
  ui.loader = function (label) {
    var bar = h('div', { class: 'segbar', 'aria-hidden': 'true' });
    for (var i = 0; i < 8; i++) {
      var block = h('i');
      block.style.animationDelay = (i * 0.16).toFixed(2) + 's';
      bar.append(block);
    }
    return h('div', { class: 'pload', role: 'status' },
      bar,
      h('div', { class: 'mono w pload-t', text: label || 'Loading' }));
  };
})();
