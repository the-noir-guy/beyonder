(function () {
  'use strict';
  var BYD = window.BYD;
  var root = document.documentElement;

  // ───────── text scramble on every button (45 ms steps, 600 ms, left to right, mixed characters, on hover) ─────────
  var SCR = { speed: 45, duration: 600, chars: 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789$@#%&*+=?!<>/\\|~^' };
  var SEL = '#add-profile, .wbtn, .bi.btn, .mi, .ep-foot button';

  function randChar() { return SCR.chars.charAt(Math.floor(Math.random() * SCR.chars.length)); }

  function scramble(el) {
    var st = el._scr || (el._scr = { orig: '', timer: 0 });
    if (st.timer) { clearInterval(st.timer); st.timer = 0; }
    else st.orig = el.textContent;
    var orig = st.orig;
    if (!orig) return;
    var chars = orig.split(''), n = chars.length, t0 = performance.now();
    function frame() {
      if (!el.isConnected) { clearInterval(st.timer); st.timer = 0; return; }
      var t = performance.now() - t0, out = '', done = true;
      for (var i = 0; i < n; i++) {
        var c = chars[i];
        if (c === ' ' || t >= SCR.duration * (i + 1) / n) out += c;
        else { out += randChar(); done = false; }
      }
      el.textContent = out;
      if (done) { clearInterval(st.timer); st.timer = 0; el.textContent = orig; }
    }
    frame();
    st.timer = setInterval(frame, SCR.speed);
  }

  document.addEventListener('mouseover', function (e) {
    if (BYD.REDUCED) return;
    var el = e.target.closest && e.target.closest(SEL);
    if (!el || el.disabled) return;
    if (e.relatedTarget && el.contains(e.relatedTarget)) return;
    scramble(el);
  });

  // ───────── theme switch: scanline wipe ─────────
  BYD.theme = { mode: 'system' };

  var line = document.getElementById('scanline');
  var barsBox = document.getElementById('bars');
  var busy = false, queued = null;

  function rnd(a, b) { return a + Math.random() * (b - a); }
  function pick(a) { return a[Math.floor(Math.random() * a.length)]; }
  function clearBars() { barsBox.replaceChildren(); }
  function barH() {
    var r = Math.random();
    if (r < 0.2) return rnd(2, 3.5);
    if (r < 0.8) return rnd(5, 14);
    return rnd(14, 24);
  }
  var RAINBOW = 'linear-gradient(90deg,#ff6b9d,#ff5fe0,#8a7dff,#3df0ff,#ffb28a)';
  function addBar(x, y, w, h) {
    var d = document.createElement('i'), r = Math.random();
    d.style.left = x.toFixed(0) + 'px';
    d.style.top = y.toFixed(0) + 'px';
    d.style.width = w.toFixed(0) + 'px';
    d.style.height = h.toFixed(1) + 'px';
    if (r < 0.35) { d.style.background = '#fff'; if (Math.random() < 0.5) d.style.boxShadow = '-4px 0 0 #ff3d8b, 4px 0 0 #3df0ff'; }
    else if (r < 0.6) { d.style.background = '#000'; if (Math.random() < 0.5) d.style.boxShadow = '-4px 0 0 #ff3d8b, 4px 0 0 #3df0ff'; }
    else if (r < 0.85) d.style.background = pick(['#ff3d8b', '#3df0ff', '#8a7dff']);
    else d.style.background = RAINBOW;
    d.style.opacity = rnd(0.75, 1).toFixed(2);
    barsBox.appendChild(d);
  }

  function scan() {
    var D = 900, E = 'cubic-bezier(.6,0,.3,1)', vh = window.innerHeight, vw = window.innerWidth;
    root.animate({ clipPath: ['inset(0 0 100% 0)', 'inset(0 0 0% 0)'] },
      { duration: D, easing: E, fill: 'forwards', pseudoElement: '::view-transition-new(root)' });
    line.style.display = 'block';
    var la = line.animate([{ transform: 'translateY(-8px)' }, { transform: 'translateY(' + (vh + 8) + 'px)' }],
      { duration: D, easing: E, fill: 'forwards' });
    var last = 0;
    (function tick(now) {
      if (la.playState !== 'running') return;
      if (now - last > 45) {
        last = now;
        clearBars();
        var y = line.getBoundingClientRect().top, n = Math.round(rnd(3, 7));
        for (var i = 0; i < n; i++) addBar(rnd(0, vw * 0.7), y + rnd(-46, 46), vw * rnd(0.1, 0.5), barH());
      }
      requestAnimationFrame(tick);
    })(0);
    la.finished.then(function () { line.style.display = 'none'; clearBars(); la.cancel(); }, function () {});
  }

  function apply(next) { root.setAttribute('data-theme', next); }

  // next: 'light' or 'dark'; instant skips the animation (used at startup)
  BYD.switchTheme = function (next, instant) {
    if (next !== 'light' && next !== 'dark') return;
    if (busy) { queued = next; return; }
    if (next === root.getAttribute('data-theme')) return;
    if (instant || BYD.REDUCED || !document.startViewTransition) { apply(next); return; }
    busy = true;
    var vt;
    try { vt = document.startViewTransition(function () { apply(next); }); }
    catch (e) { apply(next); busy = false; return; }
    vt.ready.then(scan).catch(function () {});
    var end = function () {
      busy = false;
      line.style.display = 'none';
      clearBars();
      if (queued) { var q = queued; queued = null; BYD.switchTheme(q); }
    };
    vt.finished.then(end, end);
  };
})();
