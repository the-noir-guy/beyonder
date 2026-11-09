(function () {
  'use strict';
  var BYD = window.BYD = window.BYD || {};

  BYD.REDUCED = !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  BYD.scale = 1;

  // tiny DOM builder: text is always inserted as text, never as HTML
  BYD.h = function (tag, attrs) {
    var e = document.createElement(tag);
    if (attrs) {
      Object.keys(attrs).forEach(function (k) {
        var v = attrs[k];
        if (v === null || v === undefined || v === false) return;
        if (k === 'class') e.className = v;
        else if (k === 'text') e.textContent = v;
        else if (k === 'html') e.innerHTML = v;
        else if (k.slice(0, 2) === 'on' && typeof v === 'function') e.addEventListener(k.slice(2), v);
        else e.setAttribute(k, v === true ? '' : v);
      });
    }
    for (var i = 2; i < arguments.length; i++) append(e, arguments[i]);
    return e;
  };
  function append(parent, kid) {
    if (kid === null || kid === undefined || kid === false) return;
    if (Array.isArray(kid)) { kid.forEach(function (k) { append(parent, k); }); return; }
    parent.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  }

  var ready = new Promise(function (resolve) {
    if (window.pywebview && window.pywebview.api) resolve();
    else window.addEventListener('pywebviewready', function () { resolve(); }, { once: true });
  });
  BYD.ready = ready;

  // on-screen error panel
  var errs = [];
  BYD.showError = function (message) {
    errs.push(String(message));
    if (errs.length > 6) errs.shift();
    var panel = document.getElementById('errpanel');
    document.getElementById('err-text').textContent = errs.join('\n\n');
    panel.hidden = false;
  };
  window.__bydError = BYD.showError;
  document.getElementById('err-close').addEventListener('click', function () {
    errs = [];
    document.getElementById('errpanel').hidden = true;
  });

  function logJs(level, message) {
    ready.then(function () {
      try { window.pywebview.api.log_js(level, message); } catch (e) { /* ignore */ }
    });
  }
  BYD.logJs = logJs;

  window.addEventListener('error', function (e) {
    if (e.message && e.message.indexOf('ResizeObserver') === 0) return;
    var where = e.filename ? ' (' + String(e.filename).split('/').pop() + ':' + e.lineno + ')' : '';
    var msg = (e.message || 'Script error') + where;
    BYD.showError('JavaScript error: ' + msg);
    logJs('error', msg + '\n' + ((e.error && e.error.stack) || ''));
  });
  window.addEventListener('unhandledrejection', function (e) {
    var r = e.reason;
    var msg = (r && (r.stack || r.message)) || String(r);
    BYD.showError('Unhandled promise error: ' + msg);
    logJs('error', msg);
  });

  // call a Python method; always resolves with an object that has "ok"
  BYD.call = async function (name) {
    var args = Array.prototype.slice.call(arguments, 1);
    await ready;
    try {
      var fn = window.pywebview.api[name];
      if (typeof fn !== 'function') throw new Error('API method missing: ' + name);
      var res = await fn.apply(null, args);
      if (res && res.internal) BYD.showError(res.error);
      return res || { ok: false, error: 'No response from Python.', internal: true };
    } catch (ex) {
      BYD.showError('Bridge error in ' + name + ': ' + ex);
      logJs('error', 'bridge ' + name + ': ' + ex);
      return { ok: false, error: String(ex), internal: true };
    }
  };

  // wait for the three local fonts, and log any that failed to load
  BYD.fontsReady = function () {
    var done = (document.fonts && document.fonts.ready) ? document.fonts.ready : Promise.resolve();
    var timeout = new Promise(function (r) { setTimeout(r, 2000); });
    return Promise.race([done, timeout]).then(function () {
      try {
        document.fonts.forEach(function (f) {
          if (f.status === 'error') logJs('error', 'Font failed to load: ' + f.family + ' (check assets/fonts)');
        });
      } catch (e) { /* ignore */ }
    });
  };

  // colours of the tile shown for a profile without a picture: its own colour, or a stable one taken from its key
  var TILE_PALETTE = ['#ff6b9d', '#ff5fe0', '#8a7dff', '#3df0ff', '#ffb28a'];
  BYD.tileColors = function (key, color) {
    var bg;
    if (color && /^[0-9A-Fa-f]{6}$/.test(color)) {
      bg = '#' + color;
    } else {
      var sum = 2166136261, text = String(key || '');
      for (var i = 0; i < text.length; i++) { sum ^= text.charCodeAt(i); sum = Math.imul(sum, 16777619); }
      bg = TILE_PALETTE[(sum >>> 0) % TILE_PALETTE.length];
    }
    var r = parseInt(bg.slice(1, 3), 16), g = parseInt(bg.slice(3, 5), 16), b = parseInt(bg.slice(5, 7), 16);
    return { bg: bg, fg: (0.299 * r + 0.587 * g + 0.114 * b) > 150 ? '#000' : '#fff' };
  };
  // the first letter of a name (a whole emoji counts as one letter), in capitals
  BYD.firstLetter = function (name) {
    var t = String(name || '').trim();
    var first = t ? Array.from(t)[0] : '?';
    return first.toUpperCase();
  };

  // A generated initial: an SVG <text> in the heading font, centred on its real ink box (the visible shape), not on the
  // font's line box. The glyph is measured on an offscreen canvas with the same font stack as --f-head; with
  // text-anchor:start and an alphabetic baseline the ink spans x-L .. x+R and y-A .. y+D, so
  //   x = cx - (R - L) / 2   and   y = cy + (A - D) / 2   put its centre on (cx, cy).
  // Cards and the Edit Profile popup both use this, so they cannot drift apart. The svg fills its round parent
  // (position:relative) and ignores the pointer.
  var INI_STACK = '"BYD Heading","Orbitron",sans-serif';
  var INI_SIZE = 40;                                     // in the 100-unit viewBox: about 32 px in an 80 px tile
  var iniCtx = null;
  BYD.initialSvg = function (letter, fill) {
    var NS = 'http://www.w3.org/2000/svg';
    var svg = document.createElementNS(NS, 'svg');
    svg.setAttribute('viewBox', '0 0 100 100');
    svg.setAttribute('aria-hidden', 'true');
    svg.setAttribute('class', 'ini');
    var text = document.createElementNS(NS, 'text');
    text.setAttribute('fill', fill);
    text.setAttribute('text-anchor', 'start');
    text.style.fontFamily = INI_STACK;
    text.style.fontWeight = '800';
    text.style.fontSize = INI_SIZE + 'px';
    text.textContent = letter;
    svg.appendChild(text);
    function place() {
      if (!iniCtx) iniCtx = document.createElement('canvas').getContext('2d');
      iniCtx.font = '800 ' + INI_SIZE + 'px ' + INI_STACK;
      var m = iniCtx.measureText(letter);
      var L = m.actualBoundingBoxLeft, R = m.actualBoundingBoxRight, A = m.actualBoundingBoxAscent, D = m.actualBoundingBoxDescent;
      text.setAttribute('x', (50 - (R - L) / 2).toFixed(2));
      text.setAttribute('y', (50 + (A - D) / 2).toFixed(2));
    }
    place();
    var loaded = true;
    try { loaded = !document.fonts || !document.fonts.check || document.fonts.check('800 32px "BYD Heading"'); } catch (e) { loaded = true; }
    if (!loaded) BYD.fontsReady().then(place);           // the heading font is not there yet: measure again when it is
    return svg;
  };

  // turn an SVG file (as data URL) into a PNG data URL, 256 px high
  BYD.rasterizeSvg = function (dataUrl) {
    return new Promise(function (resolve, reject) {
      var img = new Image();
      img.onload = function () {
        var w = img.naturalWidth || 256, hgt = img.naturalHeight || 256;
        var k = 256 / hgt;
        var c = document.createElement('canvas');
        c.width = Math.max(1, Math.round(w * k));
        c.height = 256;
        c.getContext('2d').drawImage(img, 0, 0, c.width, c.height);
        try { resolve(c.toDataURL('image/png')); } catch (e) { reject(e); }
      };
      img.onerror = function () { reject(new Error('Could not read the SVG.')); };
      img.src = dataUrl;
    });
  };

  document.addEventListener('contextmenu', function (e) {
    if (!(e.target.closest && e.target.closest('input,textarea'))) e.preventDefault();
  });
  window.addEventListener('wheel', function (e) { if (e.ctrlKey) e.preventDefault(); }, { passive: false });
})();
