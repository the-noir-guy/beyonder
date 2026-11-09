(function () {
  'use strict';
  var BYD = window.BYD, h = BYD.h;
  var D = BYD.dialogs = {};

  function pad2(n) { return String(n).padStart(2, '0'); }

  var SEARCH_SVG = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>';
  var CHECK_SVG = '<svg class="ck" width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="square" stroke-linejoin="miter"><path d="M2.5 7.5l3 3 6-7"/></svg>';
  var DASH_SVG = '<svg class="dh" width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="square"><path d="M3 7h8"/></svg>';

  // ───────── Add Browsers: scans this PC, shows what it finds, and adds the ones you pick ─────────
  // o.onSaved(result) runs after the browsers were added; result.added lists their names
  D.browsers = function (o) {
    var items = [];                  // { id, name, icon, on, el }  (only browsers that are not in the launcher yet)
    var addedCount = 0;              // browsers found that are already in the launcher
    var phase = 'loading';           // loading | ready | failed
    var failText = '';
    var query = '';
    var closed = false;
    var picking = false;

    // search bar
    var search = h('input', { class: 'in', type: 'text', spellcheck: 'false', autocomplete: 'off', placeholder: 'Search browsers', 'aria-label': 'Search browsers' });
    var searchRow = h('div', { class: 'frow psearch' },
      h('div', { class: 'fw' }, h('div', { class: 'bi' }, h('span', { class: 'sico', html: SEARCH_SVG }), search)));

    // select all + counter
    var all = h('button', { class: 'pall', type: 'button', role: 'checkbox', 'aria-checked': 'false', 'aria-label': 'Select all' },
      h('span', { class: 'pbox' }, h('span', { class: 'pbi', html: CHECK_SVG + DASH_SVG })),
      h('span', { class: 'mono w', text: 'Select all' }));
    var status = h('span', { class: 'mono pstat' });
    var tools = h('div', { class: 'ptools' }, all, status);

    // grid (fixed height, scrolls); the stage also holds the centered message group for empty and failed states
    var grid = h('div', { class: 'pgrid sscroll' });
    var msg = h('div', { class: 'pmsg', hidden: true });
    var loader = BYD.ui.loader('Scanning system');             // centered in the grid area, not in the whole popup
    var stage = h('div', { class: 'pstage' }, grid, msg, loader);

    // the Add Manually tile: last cell of the grid, never selectable
    var manual = h('button', { class: 'bp bpm', type: 'button', title: 'Add Manually', 'aria-label': 'Add Manually' },
      h('span', { class: 'bpt' }, h('span', { class: 'tw ch' }, h('span', { class: 'ti plus ch', text: '+' }))),
      h('span', { class: 'bpn' }, h('span', { class: 'mono bpl', text: 'Add Manually' })));

    function letter(name) { return (name || '?').charAt(0).toUpperCase(); }
    function visible(it) { return !query || it.name.toLowerCase().indexOf(query) >= 0; }
    function pickable() { return items.filter(visible); }

    function paint() {
      items.forEach(function (it) {
        it.el.classList.toggle('on', it.on);
        it.el.setAttribute('aria-checked', it.on ? 'true' : 'false');
      });
      var vis = pickable(), onVis = vis.filter(function (it) { return it.on; }).length;
      var state = !vis.length || onVis === 0 ? 'false' : (onVis === vis.length ? 'true' : 'mixed');
      all.setAttribute('aria-checked', state);
      all.disabled = !vis.length;
      var total = items.length;
      var count = items.filter(function (it) { return it.on; }).length;
      status.classList.remove('bad');
      if (phase !== 'ready') status.textContent = '';
      else if (total) status.textContent = 'SELECTED ' + pad2(count) + ' / ' + pad2(total) + (addedCount ? ' \u00b7 ' + pad2(addedCount) + ' ADDED' : '');
      else if (addedCount) status.textContent = pad2(addedCount) + ' ADDED';
      else status.textContent = '';
      if (ctl.buttons.ok) ctl.buttons.ok.disabled = !count || ctl.busy;
    }

    // the failed state: two lines of text, no tile
    function fillMessage(line1, line2) {
      msg.textContent = '';
      msg.append(h('div', { class: 'mono pm1', text: line1 }), h('div', { class: 'mono pm2', text: line2 }));
    }

    function render() {
      items.forEach(function (it) { it.el.hidden = !visible(it); });
      var shown = items.filter(visible).length;
      var showGrid = phase === 'ready' && shown > 0;
      stage.classList.toggle('empty', !showGrid);
      if (showGrid) {
        msg.hidden = true;
        if (manual.parentNode !== grid || grid.lastElementChild !== manual) grid.append(manual);
      } else if (phase === 'failed') {
        msg.hidden = false;
        fillMessage('SCAN FAILED', failText);
      } else if (phase === 'ready') {            // everything added, nothing found, or no match: only the Add Manually tile
        msg.hidden = false;
        if (manual.parentNode !== msg || msg.children.length !== 1) {
          msg.textContent = '';
          msg.append(manual);
        }
      } else {
        msg.hidden = true;
      }
      paint();
    }

    function itemEl(it) {
      var inner = it.icon ? h('img', { src: it.icon, alt: '', draggable: 'false' }) : letter(it.name);
      var tile = h('span', { class: 'ti ch' }, inner);
      if (it.icon) inner.addEventListener('error', function () { tile.textContent = letter(it.name); });
      var btn = h('button', { class: 'bp', type: 'button', role: 'checkbox', title: it.name, 'aria-label': it.name },
        h('span', { class: 'bpt' }, h('span', { class: 'tw ch' }, tile), h('span', { class: 'lock', 'aria-hidden': 'true' })),
        h('span', { class: 'bpn' }, h('span', { class: 'mono bpl', text: it.name })));
      btn.addEventListener('click', function () {
        it.on = !it.on;
        paint();
      });
      return btn;
    }

    all.addEventListener('click', function () {
      var vis = pickable();
      if (!vis.length) return;
      var every = vis.every(function (it) { return it.on; });
      vis.forEach(function (it) { it.on = !every; });
      paint();
    });
    search.addEventListener('input', function () {
      query = search.value.trim().toLowerCase();
      render();
    });

    // Add Manually: pick a program file, the page selects it (new tile just before the Add Manually tile)
    function takeManual(r) {
      query = '';
      search.value = '';
      var it = null;
      items.forEach(function (x) { if (x.id === r.id) it = x; });
      if (it) {
        it.on = true;
      } else {
        it = { id: r.id, name: r.name, icon: r.icon, on: true, el: null };
        it.el = itemEl(it);
        items.push(it);
        grid.append(it.el);
      }
      render();
      it.el.scrollIntoView({ block: 'nearest' });
    }

    async function pickManual() {
      if (picking || closed || phase !== 'ready' || ctl.busy) return;
      picking = true;
      manual.disabled = true;
      try {
        var pick = await BYD.call('pick_file', 'exe');
        if (closed || !pick || !pick.ok || !pick.path) return;
        var res = await BYD.call('inspect_browser', pick.path);
        if (closed) return;
        if (!res || !res.ok) {
          if (res && !res.internal) { status.textContent = res.error; status.classList.add('bad'); }
          return;
        }
        takeManual(res);
      } finally {
        picking = false;
        manual.disabled = false;
      }
    }
    manual.addEventListener('click', pickManual);

    async function submit(c) {
      var ids = items.filter(function (it) { return it.on; }).map(function (it) { return it.id; });
      if (!ids.length || c.busy || closed) return;
      c.setBusy(true);
      var res = await BYD.call('add_browsers', ids);
      c.setBusy(false);
      if (!res.ok) {
        if (!res.internal) { status.textContent = res.error; status.classList.add('bad'); }
        return;
      }
      closed = true;
      c.close(res);
      if (o.onSaved) o.onSaved(res);
    }

    var ctl = BYD.openModal({
      meta: '_ADD.BROWSERS // SYSTEM SCAN',
      title: '[ ADD BROWSERS ]',
      content: [searchRow, tools, stage],
      buttons: [
        { label: 'Cancel', id: 'cancel', onClick: function (c) { c.close(); } },
        { label: 'Add', id: 'ok', primary: true, onClick: submit }
      ],
      onSubmit: submit,
      focus: function () { return search; }
    });
    ctl.el.classList.add('scanning');
    ctl.buttons.ok.disabled = true;
    ctl.whenClosed.then(function () { closed = true; });

    // the scan runs while the popup opens; the loader stays at least a moment so it never just flashes
    var minimum = new Promise(function (r) { setTimeout(r, 450); });
    Promise.all([BYD.call('scan_browsers'), minimum]).then(function (out) {
      if (closed) return;
      var r = out[0];
      ctl.el.classList.remove('scanning');
      if (!r || !r.ok) {
        phase = 'failed';
        failText = (r && !r.internal && r.error) || 'Close this window and try again.';
        render();
        return;
      }
      phase = 'ready';
      addedCount = r.added_count | 0;
      items = (r.browsers || []).map(function (b) {
        var it = { id: b.id, name: b.name, icon: b.icon, on: false, el: null };
        it.el = itemEl(it);
        grid.append(it.el);
        return it;
      });
      render();
    });
    return ctl;
  };

  // ───────── Add Profiles: reads the browser's own profiles and imports the ones you pick ─────────
  // o.browser is the browser {name, ...}; o.onSaved(result) runs after the profiles were added (result.added lists their keys)
  D.profiles = function (o) {
    var br = o.browser;
    var items = [];                  // { key, name, label, imported, on, el }
    var phase = 'loading';           // loading | ready | failed
    var failText = '';
    var note = '';                   // a message in the counter's place (pink)
    var query = '';
    var anchor = null;               // the row Shift+Click ranges start from
    var closed = false;

    // search bar, select all and counter: the same markup as the Add Browsers popup
    var search = h('input', { class: 'in', type: 'text', spellcheck: 'false', autocomplete: 'off', placeholder: 'Search profiles', 'aria-label': 'Search profiles' });
    var searchRow = h('div', { class: 'frow psearch' },
      h('div', { class: 'fw' }, h('div', { class: 'bi' }, h('span', { class: 'sico', html: SEARCH_SVG }), search)));
    var all = h('button', { class: 'pall', type: 'button', role: 'checkbox', 'aria-checked': 'false', 'aria-label': 'Select all' },
      h('span', { class: 'pbox' }, h('span', { class: 'pbi', html: CHECK_SVG + DASH_SVG })),
      h('span', { class: 'mono w', text: 'Select all' }));
    var status = h('span', { class: 'mono pstat' });
    var tools = h('div', { class: 'ptools' }, all, status);

    // the list (fixed height, scrolls), the message group used when there is no row to show, and the loader
    // (centered in the list area, not in the whole popup)
    var list = h('div', { class: 'plist sscroll', role: 'group', 'aria-label': 'Profiles' });
    var msg = h('div', { class: 'pmsg', hidden: true });
    var loader = BYD.ui.loader('Reading profiles');
    var stage = h('div', { class: 'pstage' }, list, msg, loader);

    function visible(it) {
      if (!query) return true;
      return it.name.toLowerCase().indexOf(query) >= 0 || it.label.toLowerCase().indexOf(query) >= 0;
    }
    function shown() { return items.filter(visible); }
    function importable() { return shown().filter(function (it) { return !it.imported; }); }

    function paint() {
      items.forEach(function (it) { it.el.setAttribute('aria-checked', it.on ? 'true' : 'false'); });
      var vis = importable(), onVis = vis.filter(function (it) { return it.on; }).length;
      all.setAttribute('aria-checked', !vis.length || onVis === 0 ? 'false' : (onVis === vis.length ? 'true' : 'mixed'));
      all.disabled = !vis.length;
      var total = items.filter(function (it) { return !it.imported; }).length;
      var count = items.filter(function (it) { return !it.imported && it.on; }).length;
      status.classList.toggle('bad', !!note);
      if (note) status.textContent = note;
      else if (phase === 'ready' && items.length) status.textContent = 'SELECTED ' + pad2(count) + ' / ' + pad2(total);
      else status.textContent = '';
      if (ctl && ctl.buttons.ok) ctl.buttons.ok.disabled = !count || phase !== 'ready' || ctl.busy;
    }

    // one centered line in the empty stage
    function say(text) {
      msg.textContent = '';
      msg.append(h('div', { class: 'mono pm2 only', text: text }));
    }

    function render() {
      items.forEach(function (it) { it.el.hidden = !visible(it); });
      var failed = phase === 'failed';
      var none = phase === 'ready' && !items.length;                       // the browser has no profiles at all
      var nomatch = phase === 'ready' && items.length > 0 && !shown().length;   // the search matches none
      stage.classList.toggle('empty', failed || none || nomatch);
      msg.hidden = !(failed || none || nomatch);
      if (failed) {
        msg.textContent = '';
        msg.append(h('div', { class: 'mono pm1', text: 'COULD NOT READ PROFILES' }), h('div', { class: 'mono pm2', text: failText }));
      } else if (none) {
        say('NO PROFILES FOUND');
      } else if (nomatch) {
        say('NO MATCH');
      }
      paint();
    }

    function onRow(it, e) {
      if (phase !== 'ready' || it.imported) return;
      note = '';
      var vis = shown();
      if (e.shiftKey && anchor && anchor !== it && vis.indexOf(anchor) >= 0) {
        // Shift+Click: every importable row between the anchor and this row gets the anchor's state
        var a = vis.indexOf(anchor), b = vis.indexOf(it), state = anchor.on;
        for (var i = Math.min(a, b); i <= Math.max(a, b); i++) {
          if (!vis[i].imported) vis[i].on = state;
        }
      } else {
        it.on = !it.on;
      }
      anchor = it;
      paint();
    }

    function rowEl(it) {
      var btn = h('button', { class: 'prow', type: 'button', role: 'checkbox', title: it.name, 'aria-label': it.name + ' [ ' + it.label + ' ]' },
        h('span', { class: 'pbox' }, h('span', { class: 'pbi', html: CHECK_SVG + DASH_SVG })),
        h('span', { class: 'mono prn', text: it.name }),
        h('span', { class: 'mono prl', text: '[ ' + it.label + ' ]' }));
      if (it.imported) btn.disabled = true;
      btn.addEventListener('mousedown', function (e) { if (e.shiftKey) e.preventDefault(); });   // no text selection while Shift+Clicking
      btn.addEventListener('click', function (e) { onRow(it, e); });
      return btn;
    }

    function buildItems(rows) {
      list.textContent = '';
      items = (rows || []).map(function (r) {
        var it = { key: r.key, name: r.name || r.key, label: r.label || r.key, imported: !!r.imported, on: false, el: null };
        it.on = it.imported;
        it.el = rowEl(it);
        list.append(it.el);
        return it;
      });
      anchor = null;
    }

    all.addEventListener('click', function () {
      if (phase !== 'ready') return;
      note = '';
      var vis = importable();
      if (!vis.length) return;
      var every = vis.every(function (it) { return it.on; });
      vis.forEach(function (it) { it.on = !every; });
      anchor = null;
      paint();
    });
    search.addEventListener('input', function () {
      query = search.value.trim().toLowerCase();
      note = '';
      render();
    });

    async function submit(c) {
      if (phase !== 'ready' || c.busy || closed) return;
      var keys = items.filter(function (it) { return !it.imported && it.on; }).map(function (it) { return it.key; });
      if (!keys.length) return;
      c.setBusy(true);
      var res = await BYD.call('add_profiles', br.name, keys);
      c.setBusy(false);
      if (!res.ok) {
        if (!res.internal) { note = res.error; paint(); }
        return;
      }
      closed = true;
      c.close(res);
      if (o.onSaved) o.onSaved(res);
    }

    var ctl = null;
    ctl = BYD.openModal({
      meta: '_ADD.PROFILES // ' + String(br.name || '').toUpperCase(),
      title: '[ ADD PROFILES ]',
      content: [searchRow, tools, stage],
      buttons: [
        { label: 'Cancel', id: 'cancel', onClick: function (c) { c.close(); } },
        { label: 'Add', id: 'ok', primary: true, onClick: submit }
      ],
      onSubmit: submit,
      focus: function () { return search; }
    });
    ctl.el.classList.add('scanning');
    ctl.buttons.ok.disabled = true;
    ctl.whenClosed.then(function () { closed = true; });

    // reading runs while the popup opens (it may wait for the search around the browser's program file to finish);
    // the loader stays at least a moment so it never just flashes
    var minimum = new Promise(function (r) { setTimeout(r, 450); });
    Promise.all([BYD.call('list_browser_profiles', br.name), minimum]).then(function (out) {
      if (closed) return;
      var r = out[0];
      ctl.el.classList.remove('scanning');
      if (r && r.ok && !r.supported) {                  // the page normally opens the notice before this popup; this is only a safety net
        closed = true;
        ctl.close();
        ctl.whenClosed.then(function () { D.notice('Not supported yet', r.unsupported_text || 'Profile import isn\'t supported for this browser yet.'); });
        return;
      }
      if (!r || !r.ok) {
        phase = 'failed';
        failText = (r && !r.internal && r.error) || 'Close this window and try again.';
        render();
        return;
      }
      phase = 'ready';
      buildItems(r.profiles);
      render();
    });
    return ctl;
  };

  // ───────── Edit Profile: only Beyonder's own copy changes (name and picture), never the browser's profile ─────────
  var PENCIL = '<svg class="pen" width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21.174 6.812a1 1 0 0 0-3.986-3.987L3.842 16.174a2 2 0 0 0-.5.83l-1.321 4.352a.5.5 0 0 0 .623.622l4.353-1.32a2 2 0 0 0 .83-.497z"/><path d="m15 5 4 4"/></svg>';

  // a text field with an optional small button (Reset) next to it
  function textField(o) {
    var input = h('input', { class: 'in', type: 'text', spellcheck: 'false', autocomplete: 'off', maxlength: o.max ? String(o.max) : null, placeholder: o.placeholder || '', 'aria-label': o.label });
    input.value = o.value || '';
    var row = h('div', { class: 'frow' }, h('div', { class: 'fw' }, h('div', { class: 'bi' }, input)));
    if (o.action) {
      var btn = h('button', { class: 'bi btn', type: 'button', text: o.action.label });
      btn.addEventListener('click', o.action.run);
      row.append(h('div', { class: 'bslot' }, h('div', { class: 'bwb' }, btn)));
    }
    return { el: h('div', null, h('div', { class: 'lbl mono', text: o.label }), row), input: input };
  }

  // o.browser, o.profile; o.onSaved(result) runs after saving
  D.profile = function (o) {
    var br = o.browser, p = o.profile;
    var picture = null;                          // null = unchanged, 'reset' = the browser's own picture, or a cropped PNG data URL
    var closed = false;
    var avBtn = h('button', { class: 'avp has', type: 'button', 'aria-label': 'Choose profile picture' });
    var msgEl = h('div', { class: 'mono emsg', role: 'alert' });

    function paintAvatar() {
      avBtn.replaceChildren();
      var src = picture === 'reset' ? (p.locked ? (br.icon_url || null) : null) : (picture || p.avatar_url || null);   // the Default profile resets to the browser's icon
      if (src) {
        avBtn.style.background = '';
        avBtn.style.color = '';
        avBtn.append(h('img', { src: src, alt: '', draggable: 'false' }));
      } else {
        var c = BYD.tileColors(p.key, p.color);
        avBtn.style.background = c.bg;
        avBtn.style.color = c.fg;
        avBtn.append(BYD.initialSvg(BYD.firstLetter(nameF.input.value || p.name), c.fg));
      }
      avBtn.append(h('span', { class: 'veil' }));
      avBtn.insertAdjacentHTML('beforeend', PENCIL);
      avBtn.append(h('span', { class: 'ring' }));
    }

    async function pickAvatar() {
      var r = await BYD.call('pick_file', 'picture');
      if (!r || !r.ok || !r.path) return;
      var pic = await BYD.call('load_picture', r.path);
      if (!pic || !pic.ok) { if (pic && !pic.internal) msgEl.textContent = pic.error || 'Couldn\'t open that picture.'; return; }
      msgEl.textContent = '';
      var out = await D.crop(pic.data_url);
      if (out) { picture = out; paintAvatar(); }
      avBtn.focus();
    }

    // the Default profile (it only starts the browser) always keeps its name: the field is read-only and has no Reset
    var nameF = textField({ label: 'Profile name', value: p.locked ? 'Default' : p.name, max: 80,
      action: p.locked ? null : { label: 'Reset', run: function () { nameF.input.value = p.source_name || p.name; msgEl.textContent = ''; paintAvatar(); nameF.input.focus(); } } });
    if (p.locked) { nameF.input.readOnly = true; nameF.input.setAttribute('aria-readonly', 'true'); }
    nameF.input.addEventListener('input', function () { msgEl.textContent = ''; if (!picture && !p.avatar_url || picture === 'reset') paintAvatar(); });

    var resetPic = h('button', { class: 'bi btn', type: 'button', text: 'Reset' });
    resetPic.addEventListener('click', function () { picture = 'reset'; msgEl.textContent = ''; paintAvatar(); avBtn.focus(); });
    avBtn.addEventListener('click', pickAvatar);
    var avRow = h('div', { class: 'avrow' }, avBtn,
      h('div', { class: 'avtxt' }, h('span', { class: 'mono w', text: 'Profile picture' }), h('span', { class: 'mono', text: 'Click to choose and adjust' })),
      h('div', { class: 'bslot avreset' }, h('div', { class: 'bwb' }, resetPic)));
    paintAvatar();

    async function submit(c) {
      if (closed) return;
      var name = p.locked ? 'Default' : nameF.input.value.trim();
      if (!name) { msgEl.textContent = 'Give the profile a name.'; return; }
      c.setBusy(true);
      var res = await BYD.call('edit_profile', br.name, p.key, name, picture);
      c.setBusy(false);
      if (!res.ok) { if (!res.internal) msgEl.textContent = res.error; return; }
      closed = true;
      c.close(res);
      if (o.onSaved) o.onSaved(res);
    }

    var ctl = BYD.openModal({
      meta: '_EDIT.PROFILE // STEP 01 OF 01',
      title: '[ EDIT PROFILE ]',
      content: [avRow, nameF.el, msgEl],
      buttons: [
        { label: 'Cancel', id: 'cancel', onClick: function (c) { c.close(); } },
        { label: 'Save', id: 'ok', primary: true, onClick: submit }
      ],
      onSubmit: submit,
      focus: function () { return p.locked ? avBtn : nameF.input; }
    });
    ctl.whenClosed.then(function () { closed = true; });
    return ctl;
  };

  // ───────── Adjust Picture: resolves with a 512 px PNG data URL, or null ─────────
  D.crop = function (dataUrl) {
    return new Promise(function (resolve) {
      var S = 300, ZMAX = 4;
      var img = new Image();
      var st = { zoom: 1, s0: 1, ox: 0, oy: 0 };
      var canvas = h('canvas', { width: S * 2, height: S * 2 });
      var ctx = canvas.getContext('2d');
      var view = h('div', { class: 'crop' }, canvas, h('div', { class: 'mask' }), h('div', { class: 'cring' }));
      var slider = h('input', { class: 'zoom', type: 'range', min: '1', max: String(ZMAX), step: '0.01', value: '1', 'aria-label': 'Zoom' });
      var pending = false;

      function clamp() {
        var s = st.s0 * st.zoom;
        st.ox = Math.min(0, Math.max(S - img.naturalWidth * s, st.ox));
        st.oy = Math.min(0, Math.max(S - img.naturalHeight * s, st.oy));
      }
      function draw() {
        pending = false;
        ctx.setTransform(2, 0, 0, 2, 0, 0);
        ctx.clearRect(0, 0, S, S);
        ctx.imageSmoothingQuality = 'high';
        var s = st.s0 * st.zoom;
        ctx.drawImage(img, st.ox, st.oy, img.naturalWidth * s, img.naturalHeight * s);
        slider.style.setProperty('--p', ((st.zoom - 1) / (ZMAX - 1) * 100) + '%');
      }
      function redraw() { if (!pending) { pending = true; requestAnimationFrame(draw); } }
      function setZoom(z) {
        z = Math.min(ZMAX, Math.max(1, z));
        var sOld = st.s0 * st.zoom, sNew = st.s0 * z;
        var mx = (S / 2 - st.ox) / sOld, my = (S / 2 - st.oy) / sOld;
        st.zoom = z;
        st.ox = S / 2 - mx * sNew;
        st.oy = S / 2 - my * sNew;
        clamp();
        slider.value = String(z);
        redraw();
      }

      var drag = null;
      view.addEventListener('pointerdown', function (e) {
        if (e.button !== 0) return;
        view.setPointerCapture(e.pointerId);
        drag = { x: e.clientX, y: e.clientY };
      });
      view.addEventListener('pointermove', function (e) {
        if (!drag) return;
        st.ox += (e.clientX - drag.x) / BYD.scale;
        st.oy += (e.clientY - drag.y) / BYD.scale;
        drag = { x: e.clientX, y: e.clientY };
        clamp();
        redraw();
      });
      var endDrag = function () { drag = null; };
      view.addEventListener('pointerup', endDrag);
      view.addEventListener('pointercancel', endDrag);
      view.addEventListener('wheel', function (e) {
        e.preventDefault();
        setZoom(st.zoom * (e.deltaY < 0 ? 1.1 : 1 / 1.1));
      }, { passive: false });
      slider.addEventListener('input', function () { setZoom(parseFloat(slider.value)); });

      function result() {
        var s = st.s0 * st.zoom;
        var sx = Math.max(0, -st.ox / s), sy = Math.max(0, -st.oy / s);
        var ex = Math.min(img.naturalWidth, (S - st.ox) / s), ey = Math.min(img.naturalHeight, (S - st.oy) / s);
        var out = document.createElement('canvas');
        out.width = out.height = 512;
        var c = out.getContext('2d');
        c.imageSmoothingQuality = 'high';
        c.drawImage(img, sx, sy, ex - sx, ey - sy, 0, 0, 512, 512);
        return out.toDataURL('image/png');
      }

      img.onerror = function () { BYD.showError('Could not load that picture.'); resolve(null); };
      img.onload = function () {
        if (!img.naturalWidth || !img.naturalHeight) { resolve(null); return; }
        st.s0 = S / Math.min(img.naturalWidth, img.naturalHeight);
        st.ox = (S - img.naturalWidth * st.s0) / 2;
        st.oy = (S - img.naturalHeight * st.s0) / 2;
        var ctl = BYD.openModal({
          meta: '_ADJUST.PICTURE // DRAG + WHEEL',
          title: '[ ADJUST PICTURE ]',
          content: [view, slider],
          buttons: [
            { label: 'Cancel', id: 'cancel', onClick: function (c) { c.close(null); } },
            { label: 'Done', id: 'ok', primary: true, onClick: function (c) { c.close(result()); } }
          ],
          onSubmit: function (c) { c.close(result()); },
          onCancel: function (c) { c.close(null); },
          focus: function () { return slider; }
        });
        draw();
        ctl.whenClosed.then(function (r) { resolve(r || null); });
      };
      img.src = dataUrl;
    });
  };

  // ───────── confirmation and notice ─────────
  D.confirm = function (o) {
    return new Promise(function (resolve) {
      var ctl = BYD.openModal({
        meta: '_CONFIRM // ACTION REQUIRED',
        title: o.title || '[ ARE YOU SURE? ]',
        content: [h('p', { class: 'dtext', text: o.text || '' })],
        buttons: [
          { label: 'Cancel', id: 'cancel', onClick: function (c) { c.close(false); } },
          { label: o.confirmLabel || 'Confirm', id: 'ok', primary: true, onClick: function (c) { c.close(true); } }
        ],
        onSubmit: function (c) { c.close(true); },
        onCancel: function (c) { c.close(false); },
        focus: function () { return ctl.buttons.cancel; }
      });
      ctl.whenClosed.then(function (r) { resolve(r === true); });
    });
  };

  // ───────── Settings ─────────
  // a row of choices; onPick(value) resolves true when the change went through
  function seg(o) {
    var cur = o.value, busy = false, btns = [];
    var wrap = h('div', { class: 'seg', role: 'radiogroup', 'aria-label': o.label });
    function paint() {
      btns.forEach(function (b) { b.el.setAttribute('aria-checked', b.value === cur ? 'true' : 'false'); });
    }
    o.options.forEach(function (opt) {
      var el = h('button', { class: 'sgo', type: 'button', role: 'radio', text: opt.label });
      el.addEventListener('click', async function () {
        if (busy || opt.value === cur) return;
        busy = true;
        var ok = false;
        try { ok = await o.onPick(opt.value); } finally { busy = false; }
        if (ok) { cur = opt.value; paint(); }
      });
      btns.push({ el: el, value: opt.value });
      wrap.append(el);
    });
    paint();
    return wrap;
  }

  // one button in the same frame, for actions (Export, Restore, Open)
  function action(label, fn) {
    var btn = h('button', { class: 'sgo', type: 'button', text: label });
    btn.addEventListener('click', async function () {
      if (btn.disabled) return;
      btn.disabled = true;
      try { await fn(); } finally { btn.disabled = false; }
    });
    return h('div', { class: 'seg' }, btn);
  }

  // sub: a short hint, or an element when the hint changes later
  function srow(title, sub, control) {
    var subEl = (sub && sub.nodeType) ? sub : (sub ? h('div', { class: 'sts', text: sub }) : null);
    return h('div', { class: 'srow' }, h('div', { class: 'stx' }, h('div', { class: 'stt', text: title }), subEl), control);
  }

  function ssec(title, rows, first) {
    return h('div', { class: 'ssec' + (first ? ' first' : '') },
      h('div', { class: 'shd' }, h('span', { class: 'mono w', text: title }), h('span', { class: 'sln' })),
      h('div', { class: 'srows' }, rows));
  }

  // 'Ctrl+Alt+B' from a keydown, or null while only modifiers are held
  function comboFromEvent(e) {
    var code = e.code || '', key = null;
    if (/^Key[A-Z]$/.test(code)) key = code.slice(3);
    else if (/^Digit[0-9]$/.test(code)) key = code.slice(5);
    else if (/^F([1-9]|1[0-2])$/.test(code)) key = code;
    else if (code === 'Space') key = 'Space';
    if (!key) return null;
    var parts = [];
    if (e.ctrlKey) parts.push('Ctrl');
    if (e.altKey) parts.push('Alt');
    if (e.shiftKey) parts.push('Shift');
    if (e.metaKey) parts.push('Win');
    return { text: parts.concat([key]).join('+') };
  }

  // click it, press the keys; o: { value, status, hint (element), onSet(keys) -> Promise<{ok, keys, status, error}> }
  function keyField(o) {
    var cur = o.value, status = o.status, listening = false;
    var btn = h('button', { class: 'sgo keyb', type: 'button' });
    function fmt(k) { return String(k).split('+').join(' + ').toUpperCase(); }
    function setHint(text, bad) { o.hint.textContent = text; o.hint.classList.toggle('bad', !!bad); }
    function statusHint() {
      if (status === 'in_use') setHint('In use by another app', true);
      else if (status === 'error') setHint('Windows refused that shortcut', true);
      else setHint('Click, then press the keys', false);
    }
    function idle() {
      listening = false;
      btn.classList.remove('listening');
      btn.textContent = fmt(cur);
      window.removeEventListener('keydown', onKey, true);
    }
    async function commit(text) {
      idle();
      btn.disabled = true;
      var r = null;
      try { r = await o.onSet(text); } finally { btn.disabled = false; }
      if (r && r.ok) { cur = r.keys || text; status = r.status; statusHint(); }
      else setHint((r && r.error) || 'Could not set that shortcut', true);
      btn.textContent = fmt(cur);
    }
    // on window (capture) so the dialog's own Escape / Enter / Tab handling never sees these keys
    function onKey(e) {
      e.preventDefault();
      e.stopImmediatePropagation();
      if (e.repeat) return;
      if (e.key === 'Escape' && !e.ctrlKey && !e.altKey && !e.shiftKey && !e.metaKey) { idle(); statusHint(); return; }
      var c = comboFromEvent(e);
      if (!c) {
        var m = [];
        if (e.ctrlKey) m.push('Ctrl');
        if (e.altKey) m.push('Alt');
        if (e.shiftKey) m.push('Shift');
        if (e.metaKey) m.push('Win');
        btn.textContent = m.length ? fmt(m.join('+')) + ' + …' : 'PRESS KEYS…';
        return;
      }
      if (!(e.ctrlKey || e.altKey || e.metaKey)) { setHint('Add Ctrl, Alt or Win', true); return; }
      commit(c.text);
    }
    btn.addEventListener('click', function () {
      if (listening) return;
      listening = true;
      btn.classList.add('listening');
      btn.textContent = 'PRESS KEYS…';
      setHint('Hold Ctrl, Alt or Win and press a key. Esc cancels', false);
      window.addEventListener('keydown', onKey, true);
    });
    btn.addEventListener('blur', function () { if (listening) { idle(); statusHint(); } });
    btn.textContent = fmt(cur);
    statusHint();
    return h('div', { class: 'seg' }, btn);
  }

  // o.values: the current settings; o.onChange(key, value) -> Promise<boolean>;
  // o.actions: { setHotkey(keys), exportBackup(), restoreBackup(), removed() }
  D.settings = function (o) {
    var v = o.values, act = o.actions || {};
    var onOff = [{ value: false, label: 'Off' }, { value: true, label: 'On' }];
    function pick(key) { return function (value) { return o.onChange(key, value); }; }
    var keyHint = h('div', { class: 'sts' });

    var content = h('div', { class: 'sbox sscroll' }, [
      ssec('General', [
        srow('Theme', 'Light, dark or follow Windows', seg({ label: 'Theme', value: v.theme, onPick: pick('theme'),
          options: [{ value: 'light', label: 'Light' }, { value: 'dark', label: 'Dark' }, { value: 'system', label: 'System' }] })),
        srow('Start with Windows', 'Opens in the tray at sign-in', seg({ label: 'Start with Windows', value: !!v.autostart,
          onPick: pick('autostart'), options: onOff }))
      ], true),
      ssec('Launch', [
        srow('Minimize after launch', 'Steps aside once a profile opens', seg({ label: 'Minimize after launch',
          value: !!v.minimize_after_launch, onPick: pick('minimize_after_launch'), options: onOff })),
        srow('Cross button', 'What the window X does', seg({ label: 'Cross button', value: v.close_action,
          onPick: pick('close_action'),
          options: [{ value: 'tray', label: 'Hide to tray' }, { value: 'quit', label: 'Quit' }] }))
      ]),
      ssec('Profiles', [
        srow('Default sort', 'Order of the profile cards', seg({ label: 'Default sort', value: v.sort, onPick: pick('sort'),
          options: [{ value: 'manual', label: 'Manual' }, { value: 'most_used', label: 'Most used' }, { value: 'recent', label: 'Recent' }] }))
      ]),
      ssec('Global hotkey', [
        srow('Hotkey', 'Show or hide Beyonder from anywhere', seg({ label: 'Global hotkey', value: !!v.hotkey_enabled,
          onPick: pick('hotkey_enabled'), options: onOff })),
        srow('Keys', keyHint, keyField({ value: v.hotkey, status: v.hotkey_status, hint: keyHint, onSet: act.setHotkey }))
      ]),
      ssec('Data', [
        srow('Backup', 'Save your data folder as a zip', action('Export', function () { return act.exportBackup(); })),
        srow('Restore', 'Replace your data with a backup', action('Restore', function () { return act.restoreBackup(); })),
        srow('Removed items', 'Bring back browsers and profiles', action('Open', function () { return act.removed(); }))
      ])
    ]);

    var ctl = BYD.openModal({
      meta: '_SETTINGS // SYSTEM CONFIG',
      title: '[ SETTINGS ]',
      content: [content],
      buttons: [{ label: 'Close', id: 'ok', primary: true, onClick: function (c) { c.close(); } }],
      onSubmit: function (c) { c.close(); },
      focus: function () { return ctl.el.querySelector('.sgo[aria-checked="true"]'); }
    });
    return ctl;
  };

  // ───────── Removed items: bring them back ─────────
  // o.onState(result, { select }) hands a restored state back to the main window
  D.removed = function (o) {
    var listEl = h('div', { class: 'rlist sscroll' });

    function btn(label, fn) {
      var b = h('button', { class: 'sgo', type: 'button', text: label });
      b.addEventListener('click', async function () {
        if (b.disabled) return;
        b.disabled = true;
        try { await fn(); } finally { b.disabled = false; }
      });
      return b;
    }

    function rowEl(title, sub, buttons) {
      return h('div', { class: 'srow rrow' },
        h('div', { class: 'stx' }, h('div', { class: 'stt', text: title, title: title }), h('div', { class: 'sts', text: sub })),
        h('div', { class: 'seg' }, buttons));
    }

    async function load() {
      var r = await BYD.call('list_removed');
      if (r && r.ok) render(r);
    }

    async function restore(method, args, select) {
      var r = await BYD.call.apply(null, [method].concat(args));
      if (r && r.ok) o.onState(r, { select: select });
      else if (r && !r.internal && r.error) await D.notice('Couldn\'t restore it', r.error);
      await load();
    }

    function render(r) {
      listEl.replaceChildren();
      var any = false;
      (r.browsers || []).forEach(function (b) {
        any = true;
        listEl.append(rowEl(b.name, 'Browser // ' + b.profiles + (b.profiles === 1 ? ' profile' : ' profiles'), [
          btn('Restore', function () { return restore('restore_browser', [b.name, 1000000], b.name); })
        ]));
      });
      (r.profiles || []).forEach(function (p) {
        any = true;
        listEl.append(rowEl(p.name, 'Profile // ' + p.browser, [
          btn('Restore', function () { return restore('restore_profile', [p.browser, p.key, p.data || {}, 1000000], p.browser); })
        ]));
      });
      if (!any) listEl.append(h('div', { class: 'rnone mono', text: 'Nothing has been removed' }));
    }

    var ctl = BYD.openModal({
      meta: '_REMOVED // RESTORE',
      title: '[ REMOVED ITEMS ]',
      content: [listEl],
      buttons: [{ label: 'Close', id: 'ok', primary: true, onClick: function (c) { c.close(); } }],
      onSubmit: function (c) { c.close(); }
    });
    load();
    return ctl;
  };

  D.notice = function (title, text) {
    var t = '[ ' + String(title || 'Notice').toUpperCase() + ' ]';
    var ctl = BYD.openModal({
      meta: '_NOTICE // SYSTEM MESSAGE',
      title: t,
      content: [h('p', { class: 'dtext', text: text || '' })],
      buttons: [{ label: 'OK', id: 'ok', primary: true, onClick: function (c) { c.close(); } }],
      onSubmit: function (c) { c.close(); }
    });
    return ctl.whenClosed;
  };
})();
