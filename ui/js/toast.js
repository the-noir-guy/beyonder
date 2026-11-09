(function () {
  'use strict';
  var BYD = window.BYD, h = BYD.h;
  var layer = document.getElementById('toast-layer');
  var MS = 5000, MAX = 4;
  var live = [];

  function dismiss(t, instant) {
    if (t.gone) return;
    t.gone = true;
    var i = live.indexOf(t);
    if (i >= 0) live.splice(i, 1);
    if (t.line) { try { t.line.cancel(); } catch (e) { /* ignore */ } }
    if (t.timer) clearTimeout(t.timer);
    t.el.inert = true;
    var done = function () { t.el.remove(); };
    if (instant || BYD.REDUCED || !t.el.animate) { done(); return; }
    var a = t.el.animate([{ opacity: 1, transform: 'translateY(0)' }, { opacity: 0, transform: 'translateY(12px)' }],
      { duration: 170, easing: 'ease-in', fill: 'forwards' });
    a.finished.then(done, done);
  }

  // A small overlay in the bottom-left corner: it never blocks the app behind it.
  // o: { text, undoLabel, onUndo, onCancel }
  BYD.toast = function (o) {
    var t = { gone: false, line: null, timer: 0, el: null };
    var bar = h('i');
    var undo = h('button', { class: 'wbtn', type: 'button', text: o.undoLabel || 'Undo' });
    var cancel = h('button', { class: 'bi btn', type: 'button', text: 'Cancel' });
    var el = h('div', { class: 'toast', role: 'status' },
      h('div', { class: 'tborder' }, h('div', { class: 'tclip' },
        h('div', { class: 'ttext mono', text: o.text, title: o.text }),
        h('div', { class: 'tline' }, bar),
        h('div', { class: 'tbtns' },
          h('div', { class: 'bslot' }, h('div', { class: 'bwb' }, cancel)),
          h('div', { class: 'bslot' }, h('div', { class: 'wb' }, undo))))));
    t.el = el;

    undo.addEventListener('click', function () {
      if (t.gone) return;
      dismiss(t);
      if (o.onUndo) o.onUndo();
    });
    cancel.addEventListener('click', function () {
      if (t.gone) return;
      dismiss(t);
      if (o.onCancel) o.onCancel();
    });

    while (live.length >= MAX) dismiss(live[0], true);
    live.push(t);
    layer.append(el);

    if (!BYD.REDUCED && el.animate) {
      el.animate([{ opacity: 0, transform: 'translateY(14px)' }, { opacity: 1, transform: 'translateY(0)' }],
        { duration: 200, easing: 'cubic-bezier(.22,.8,.3,1)' });
    }
    if (bar.animate) {
      t.line = bar.animate([{ transform: 'scaleX(1)' }, { transform: 'scaleX(0)' }],
        { duration: MS, easing: 'linear', fill: 'forwards' });
      t.line.onfinish = function () { dismiss(t); };
    } else {
      t.timer = setTimeout(function () { dismiss(t); }, MS);
    }
    return t;
  };
})();
