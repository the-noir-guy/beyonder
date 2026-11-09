(function () {
  'use strict';
  var BYD = window.BYD;
  var TITLE_H = 38;
  var stage = document.getElementById('stage');

  BYD.W = 1280;
  BYD.H = 800;

  // the HUD frame follows the stage size, so the whole UI always fills the window
  BYD.frameSvg = function (W, H, circles) {
    var p = function (a) { return a.map(function (q) { return q.join(','); }).join(' '); };
    var cx = W / 2, out = [];
    var outer = p([[70, 22], [W - 70, 22], [W - 22, 70], [W - 22, H - 70], [W - 70, H - 22], [70, H - 22], [22, H - 70], [22, 70]]);
    if (circles) {
      out.push('<polygon points="' + outer + '"></polygon>');
      return out.join('');
    }
    out.push('<polygon points="' + outer + '" stroke-opacity=".7"></polygon>');
    out.push('<polygon points="' + p([[84, 34], [cx - 170, 34], [cx - 150, 54], [cx + 150, 54], [cx + 170, 34], [W - 84, 34], [W - 34, 84], [W - 34, H - 84], [W - 84, H - 34], [84, H - 34], [34, H - 84], [34, 84]]) + '" stroke-opacity=".3"></polygon>');
    out.push('<polyline points="' + p([[22, H / 2 - 100], [44, H / 2 - 100], [44, H / 2 + 100], [22, H / 2 + 100]]) + '" stroke-opacity=".5"></polyline>');
    out.push('<polyline points="' + p([[W - 22, H / 2 - 100], [W - 44, H / 2 - 100], [W - 44, H / 2 + 100], [W - 22, H / 2 + 100]]) + '" stroke-opacity=".5"></polyline>');
    return out.join('');
  };

  function fit() {
    var vw = window.innerWidth, vh = window.innerHeight - TITLE_H;
    if (vw < 10 || vh < 10) return;
    var s = Math.min(vw / 1280, vh / 800);
    var W = vw / s, H = vh / s;
    stage.style.width = W + 'px';
    stage.style.height = H + 'px';
    stage.style.setProperty('--H', H + 'px');
    stage.style.transform = 'scale(' + s + ')';
    BYD.scale = s;
    BYD.W = W;
    BYD.H = H;
    var f = document.getElementById('hudframe');
    f.setAttribute('viewBox', '0 0 ' + W + ' ' + H);
    f.innerHTML = BYD.frameSvg(W, H, false);
  }
  window.addEventListener('resize', fit);
  fit();

  // client pixels -> stage (design) pixels
  BYD.stagePoint = function (cx, cy) {
    var r = stage.getBoundingClientRect();
    return { x: (cx - r.left) / BYD.scale, y: (cy - r.top) / BYD.scale };
  };

  // title bar
  var bar = document.getElementById('titlebar');
  function setMax(state) {
    document.body.classList.toggle('maxed', !!state);
    document.getElementById('btn-max').setAttribute('aria-label', state ? 'Restore' : 'Maximize');
  }
  window.__bydMaxState = setMax;
  async function toggleMax() {
    var r = await BYD.call('toggle_maximize');
    if (r && r.ok) setMax(r.maximized);
  }
  bar.addEventListener('pointerdown', function (e) {
    if (e.button !== 0 || e.target.closest('button')) return;
    e.preventDefault();
    BYD.call('start_drag');
  });
  bar.addEventListener('dblclick', function (e) {
    if (e.target.closest('button')) return;
    toggleMax();
  });
  document.getElementById('btn-min').addEventListener('click', function () { BYD.call('minimize'); });
  document.getElementById('btn-max').addEventListener('click', toggleMax);
  document.getElementById('btn-close').addEventListener('click', function () { BYD.call('close'); });

  // resize handles (the frameless window has no native edges)
  document.querySelectorAll('.rh').forEach(function (hd) {
    hd.addEventListener('pointerdown', function (e) {
      if (e.button !== 0) return;
      e.preventDefault();
      BYD.call('start_resize', hd.dataset.edge);
    });
  });
})();
