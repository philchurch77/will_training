/* The deck: deals his hand, runs a card, keeps every play, backs it up.

   Everything on /deck/ is drawn here from what the phone already holds - the
   cards baked into the page and the plays in localStorage - so it looks and
   works the same with no signal as with full bars. The server is the backup:
   plays go to /api/plays/ when there is signal, and come back from it if the
   phone ever loses its own copy.

   Three rules this file is built around, and TestDeckScript reads it to keep
   them:

   * A play is never lost. It is saved on the phone before anything else
     happens, the list of plays only ever grows (savePlays refuses anything
     shorter or missing an id), and no answer from the server - a 401, a 403,
     a refusal, an HTML page - removes one.
   * Nothing counts down at him. A timed card fills a bar he started himself,
     with no numbers on it, and buzzes at the end. That is the one exception
     to the rule in CLAUDE.md, and runTimedBar writes no text at all.
   * The date is the phone's own. A play at half past midnight in summer
     belongs to today, so the date is built from the local clock, not cut
     from an ISO string, which is UTC. */
(function () {
  'use strict';

  var PLAYS_KEY = 'will-deck-plays-v1';
  var HAND_KEY = 'will-deck-hand-v1';
  var DRAFT_KEY = 'will-deck-draft-v1';   // a weak-foot score awaiting its strong foot
  var MAX_BATCH = 500;          // the ceiling api_plays reads per request
  var HAND_SIZE = 5;
  var FREE_PLAY = 'free-play';
  var MOVES = 'moves';
  var PINNED_SECOND = ['quick-feet', 'combos'];

  var root = document.getElementById('deck');
  var dataEl = document.getElementById('deck-cards');
  if (!root || !dataEl) { return; }

  var PLAYS_URL = root.getAttribute('data-plays-url');
  var LOGIN_URL = root.getAttribute('data-login-url');

  // --- cards ---------------------------------------------------------------
  // Arrive sorted by Card.order, which also puts the packs in their order.
  var CARDS = JSON.parse(dataEl.textContent || '[]');
  var BY_SLUG = {};
  var BY_PACK = {};
  var PACK_ORDER = [];
  CARDS.forEach(function (card) {
    BY_SLUG[card.slug] = card;
    if (!BY_PACK[card.pack]) { BY_PACK[card.pack] = []; PACK_ORDER.push(card.pack); }
    BY_PACK[card.pack].push(card);
  });

  // --- storage -------------------------------------------------------------
  // If localStorage is blocked or full, carry on in memory and say so on
  // screen: a play he can see is better than an error, but he must not think
  // it is kept when it is not.
  var storageOk = true;
  var memory = {};

  function getItem(key) {
    if (storageOk) {
      try {
        var value = localStorage.getItem(key);
        memory[key] = value;
        return value;
      } catch (e) { storageOk = false; }
    }
    return Object.prototype.hasOwnProperty.call(memory, key) ? memory[key] : null;
  }

  function setItem(key, value) {
    memory[key] = value;
    if (storageOk) {
      try { localStorage.setItem(key, value); return true; } catch (e) { storageOk = false; }
    }
    return false;
  }

  function loadPlays() {
    var raw = getItem(PLAYS_KEY);
    if (!raw) { return []; }
    try {
      var list = JSON.parse(raw);
      if (Array.isArray(list)) {
        return list.filter(function (p) { return p && typeof p === 'object' && p.id; });
      }
    } catch (e) { /* fall through */ }
    // Unreadable. Put the text somewhere safe before anything writes over it,
    // so Dad can still dig it out; the server has the backup either way.
    setItem(PLAYS_KEY + '-unreadable-' + Date.now(), raw);
    setItem(PLAYS_KEY, '[]');
    return [];
  }

  // The only way plays are written. It refuses a list that is shorter than
  // the stored one or is missing any play the stored one has, so no bug
  // anywhere in this file can throw a score away.
  function savePlays(next) {
    var current = loadPlays();
    if (next.length < current.length) { return false; }
    var ids = {};
    next.forEach(function (play) { ids[play.id] = true; });
    for (var i = 0; i < current.length; i++) {
      if (!ids[current[i].id]) { return false; }
    }
    // False when the phone would not take it: the play is held in memory and
    // the warning at the top of the screen says the phone is not keeping it.
    return setItem(PLAYS_KEY, JSON.stringify(next));
  }

  // One shape for a play, wherever it comes from.
  function makePlay(fields, synced) {
    return {
      id: fields.id, card: fields.card, date: fields.date, played_at: fields.played_at,
      score: fields.score, weak_score: fields.weak_score,
      synced: !!synced, refused: null
    };
  }

  // Read, change, write, in one go, so a sync answer landing while he plays
  // a card is applied to the list as it is now, not as it was.
  // If another tab wrote in between and savePlays refuses, read again and
  // have one more go. `change` must be safe to run twice on a fresh list.
  var writeLost = false;
  function updatePlays(change) {
    for (var attempt = 0; attempt < 2; attempt++) {
      var list = loadPlays();
      change(list);
      if (savePlays(list)) { return true; }
      if (!storageOk) { return false; }
    }
    writeLost = true;
    return false;
  }

  // --- ids, dates, numbers -------------------------------------------------
  function pad(n) { return n < 10 ? '0' + n : String(n); }

  function localDate(d) {
    d = d || new Date();
    return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate());
  }

  // randomUUID needs HTTPS or localhost, and iOS 15.4 or later; the app is
  // also opened over plain http on the home wifi.
  function newId() {
    var c = window.crypto;
    if (c && c.randomUUID) { return c.randomUUID(); }
    var b = new Uint8Array(16);
    if (c && c.getRandomValues) {
      c.getRandomValues(b);
    } else {
      for (var j = 0; j < 16; j++) { b[j] = Math.floor(Math.random() * 256); }
    }
    b[6] = (b[6] & 0x0f) | 0x40;
    b[8] = (b[8] & 0x3f) | 0x80;
    var h = [];
    for (var i = 0; i < 16; i++) { h.push((b[i] + 256).toString(16).slice(1)); }
    return h.slice(0, 4).join('') + '-' + h.slice(4, 6).join('') + '-' +
      h.slice(6, 8).join('') + '-' + h.slice(8, 10).join('') + '-' + h.slice(10).join('');
  }

  function shuffle(list) {
    var out = list.slice();
    for (var i = out.length - 1; i > 0; i--) {
      var j = Math.floor(Math.random() * (i + 1));
      var t = out[i]; out[i] = out[j]; out[j] = t;
    }
    return out;
  }

  // A time card's score is tenths of a second.
  function tenthsText(tenths) { return (tenths / 10).toFixed(1) + ' s'; }

  function scoreText(card, value) {
    return card.scoring === 'time' ? tenthsText(value) : String(value);
  }

  // --- bests ---------------------------------------------------------------
  function counts(card, value) {
    return value !== null && value !== undefined &&
      (card.scoring !== 'time' || value > 0);
  }

  function beats(card, value, best) {
    if (best === null) { return true; }
    return card.scoring === 'time' ? value < best : value > best;
  }

  // His best on a card, per foot, from every play the phone holds.
  function bestsFor(card, plays) {
    var best = { score: null, weak: null };
    plays.forEach(function (play) {
      if (play.card !== card.slug) { return; }
      if (counts(card, play.score) && beats(card, play.score, best.score)) {
        best.score = play.score;
      }
      if (counts(card, play.weak_score) && beats(card, play.weak_score, best.weak)) {
        best.weak = play.weak_score;
      }
    });
    return best;
  }

  function playedOn(plays, day) {
    var done = {};
    plays.forEach(function (play) { if (play.date === day) { done[play.card] = true; } });
    return done;
  }

  // --- dealing -------------------------------------------------------------
  // Five cards from five packs: always a Moves card, always one of Quick feet
  // or Combos, then three more from the packs left. Free play is never dealt;
  // it has its own button. A card he has already played today, or that was
  // in the hand he just dealt away, is passed over while there is another.
  function deal(previous) {
    var plays = loadPlays();
    var avoid = playedOn(plays, localDate());
    (previous || []).forEach(function (slug) { avoid[slug] = true; });
    var hand = [];
    var taken = {};
    var usedPacks = {};

    function take(pack) {
      var all = (BY_PACK[pack] || []).filter(function (c) { return !taken[c.slug]; });
      var fresh = all.filter(function (c) { return !avoid[c.slug]; });
      var pool = fresh.length ? fresh : all;
      if (!pool.length) { return false; }
      var card = pool[Math.floor(Math.random() * pool.length)];
      hand.push(card.slug);
      taken[card.slug] = true;
      usedPacks[pack] = true;
      return true;
    }

    take(MOVES);
    var second = shuffle(PINNED_SECOND.filter(function (p) { return BY_PACK[p]; }));
    for (var s = 0; s < second.length && !take(second[s]); s++) { /* next */ }
    var others = shuffle(PACK_ORDER.filter(function (p) {
      return p !== FREE_PLAY && !usedPacks[p];
    }));
    for (var o = 0; o < others.length && hand.length < HAND_SIZE; o++) { take(others[o]); }
    // Fewer than five packs with cards in: repeat a pack rather than deal short.
    var any = shuffle(PACK_ORDER.filter(function (p) { return p !== FREE_PLAY; }));
    for (var a = 0; a < any.length * HAND_SIZE && hand.length < HAND_SIZE; a++) {
      take(any[a % any.length]);
    }
    return hand;
  }

  // The same hand all day, until he deals again or a card in it is retired.
  function currentHand() {
    var today = localDate();
    var stored = null;
    try { stored = JSON.parse(getItem(HAND_KEY) || 'null'); } catch (e) { stored = null; }
    var ok = stored && stored.date === today && Array.isArray(stored.slugs) &&
      stored.slugs.length && stored.slugs.every(function (s) { return BY_SLUG[s]; });
    if (ok) { return stored.slugs; }
    var hand = deal();
    setItem(HAND_KEY, JSON.stringify({ date: today, slugs: hand }));
    return hand;
  }

  function dealAgain(previous) {
    setItem(HAND_KEY, JSON.stringify({ date: localDate(), slugs: deal(previous) }));
    renderHand();
  }

  // --- drawing -------------------------------------------------------------
  // Text always goes in as text, never as HTML.
  function el(tag, attrs, kids) {
    var node = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (key) {
      var value = attrs[key];
      if (value === null || value === undefined || value === false) { return; }
      if (key === 'text') { node.textContent = value; }
      else if (key === 'class') { node.className = value; }
      else if (key === 'hidden') { node.hidden = true; }
      else if (key.slice(0, 2) === 'on') { node.addEventListener(key.slice(2), value); }
      else { node.setAttribute(key, value); }
    });
    add(node, kids);
    return node;
  }

  function add(parent, kids) {
    (kids || []).forEach(function (kid) {
      if (kid === null || kid === undefined || kid === false) { return; }
      parent.appendChild(typeof kid === 'string' ? document.createTextNode(kid) : kid);
    });
    return parent;
  }

  function clear(node) { while (node.firstChild) { node.removeChild(node.firstChild); } }

  // Timers and screen locks belonging to the screen on show; stopped when he
  // leaves it, so a timer he walked away from does not buzz in his pocket.
  var cleanups = [];
  function onLeave(fn) { cleanups.push(fn); }

  var statusEl = el('p', { class: 'deck-status', 'aria-live': 'polite' });
  var renderedDate = null;
  var onCard = false;

  // The one message that means a score may be lost goes at the top, where he
  // sees it before he plays, not down with the calm ones.
  var warnEl = el('div', { class: 'deck-warn', role: 'alert', hidden: true },
    ['This phone is not keeping your scores. Tell Dad.']);

  function show(nodes, isCard, keepScroll) {
    cleanups.splice(0).forEach(function (fn) { try { fn(); } catch (e) { /* gone */ } });
    clear(root);
    root.appendChild(warnEl);
    add(root, nodes);
    root.appendChild(statusEl);
    paintStatus();
    renderedDate = localDate();
    onCard = !!isCard;
    if (!keepScroll) { window.scrollTo(0, 0); }
  }

  function kitText(card) {
    // Not "Rebounder  Rebounder": the pack name already says it.
    var kit = (card.kit || []).filter(function (k) { return k !== card.pack_name.toLowerCase(); });
    if (!kit.length) { return ''; }
    var words = kit.join(', ');
    return words.charAt(0).toUpperCase() + words.slice(1);
  }

  // Done is a tick and the word, never colour alone.
  function cardRow(card, done) {
    return el('a', { class: 'drill-row deck-row' + (done ? ' is-done' : ''), href: '#card/' + card.slug }, [
      el('span', { class: 'tick', 'aria-hidden': 'true', text: done ? '✓' : '' }),
      el('span', { class: 'drill-main' }, [
        el('span', { class: 'drill-name', text: card.name }),
        el('span', { class: 'drill-meta' }, [
          el('span', { text: card.pack_name }),
          kitText(card) ? el('span', { text: kitText(card) }) : null,
          done ? el('span', { class: 'deck-done', text: 'Done' }) : null
        ])
      ]),
      el('span', { class: 'chev', 'aria-hidden': 'true', text: '›' })
    ]);
  }

  function freePlayButton(doneToday) {
    var card = BY_SLUG[FREE_PLAY];
    if (!card) { return null; }
    if (doneToday) {
      return el('button', { type: 'button', class: 'btn btn-quiet mt', disabled: 'disabled' },
        ['✓ Football logged today']);
    }
    return el('button', {
      type: 'button', class: 'btn mt',
      onclick: function () {
        savePlay(card, null, null);
        route();
      }
    }, [card.name]);
  }

  // --- the hand ------------------------------------------------------------
  function renderHand(keepScroll) {
    var plays = loadPlays();
    var done = playedOn(plays, localDate());
    var hand = currentHand();
    var count = Object.keys(done).filter(function (s) { return s !== FREE_PLAY; }).length;
    var sub = count === 0 ? 'Pick one to start.'
      : count >= 3 ? count + ' done. That is a session!'
      : 'Done today: ' + count + ' of 3';

    show([
      el('div', { class: 'card card-hero' }, [
        el('div', { class: 'hero-kicker', text: 'Your hand' }),
        el('h1', { class: 'hero-big', text: 'Play any 3' }),
        el('p', { class: 'hero-sub', text: sub })
      ]),
      el('div', { class: 'drill-list' }, hand.map(function (slug) {
        return cardRow(BY_SLUG[slug], done[slug]);
      })),
      freePlayButton(done[FREE_PLAY]),
      el('a', { class: 'btn btn-quiet mt', href: '#all', text: 'Pick from the whole deck' }),
      // Last, so a stray thumb does not throw his hand away.
      el('button', {
        type: 'button', class: 'btn btn-quiet mt',
        onclick: function () { dealAgain(hand); }
      }, ['Deal again'])
    ], false, keepScroll);
  }

  // --- the whole deck ------------------------------------------------------
  // A plain list under pack headings: everything is reachable by scrolling
  // down, nothing by scrolling sideways.
  function renderAll(keepScroll) {
    var done = playedOn(loadPlays(), localDate());
    var rows = [];
    PACK_ORDER.forEach(function (pack) {
      var cards = BY_PACK[pack];
      rows.push(el('div', { class: 'drill-group' }, [
        el('span', { class: 'drill-group-name', text: cards[0].pack_name }),
        el('span', { class: 'drill-group-count', text: String(cards.length) })
      ]));
      cards.forEach(function (card) { rows.push(cardRow(card, done[card.slug])); });
    });
    show([
      el('a', { class: 'deck-back', href: '#', text: '‹ Back to my hand' }),
      el('div', { class: 'drill-list' }, rows)
    ], false, keepScroll);
  }

  // --- a card --------------------------------------------------------------
  function renderCard(card) {
    var before = bestsFor(card, loadPlays());
    var stage = el('div', { class: 'card deck-stage' });
    var bestEl = bestLine(card, before);

    show([
      el('a', { class: 'deck-back', href: '#', text: '‹ Back to my hand' }),
      el('h1', { class: 'deck-title', text: card.name }),
      el('p', { class: 'drill-meta deck-meta' }, [
        el('span', { text: card.pack_name }),
        kitText(card) ? el('span', { text: kitText(card) }) : null
      ]),
      el('p', { class: 'instructions', text: card.instructions }),
      el('div', { class: 'cue', text: card.cue }),
      bestEl,
      stage
    ], true);

    if (card.scoring === 'none') {
      var doneToday = playedOn(loadPlays(), localDate())[card.slug];
      add(stage, [freePlayButton(doneToday)]);
      return;
    }

    var feet = card.per_foot ? ['weak', 'strong'] : ['one'];
    var results = {};

    function step(i) {
      var foot = feet[i];
      var last = i === feet.length - 1;
      var label = last ? 'Save' : 'Next: strong foot';
      clear(stage);
      if (card.per_foot) {
        add(stage, [el('h2', { class: 'deck-foot', text: foot === 'weak' ? 'Weak foot' : 'Strong foot' })]);
      }
      if (foot === 'strong') {
        add(stage, [el('p', { class: 'deck-best', text: 'Weak foot: ' + scoreText(card, results.weak) + '. Now the strong foot.' })]);
      }
      var next = function (value) {
        results[foot] = value;
        // The weak foot's number is kept on the phone straight away: if the
        // page is thrown away while he sets up the strong-foot go, opening
        // the card again picks up from here instead of losing it.
        if (foot === 'weak') {
          setItem(DRAFT_KEY, JSON.stringify({ card: card.slug, date: localDate(), weak: value }));
        }
        if (last) { finish(); } else { step(i + 1); }
      };
      if (card.scoring === 'time') { stopwatch(stage, label, next); }
      else if (card.timer_seconds) { timedThenCount(stage, card, label, next); }
      else { stepper(stage, card, label, next); }
      if (foot === 'strong') {
        add(stage, [el('button', {
          type: 'button', class: 'btn btn-quiet mt',
          onclick: function () { setItem(DRAFT_KEY, 'null'); renderCard(card); }
        }, ['Start again with the weak foot'])]);
      }
    }

    function finish() {
      var score = card.per_foot ? results.strong : results.one;
      var weak = card.per_foot ? results.weak : null;
      savePlay(card, score, weak);
      setItem(DRAFT_KEY, 'null');
      var now = bestLine(card, bestsFor(card, loadPlays()));
      bestEl.parentNode.replaceChild(now, bestEl);
      bestEl = now;
      summary(stage, card, before, score, weak);
    }

    var draft = readDraft(card);
    if (draft) {
      results.weak = draft.weak;
      step(1);
    } else {
      step(0);
    }
  }

  // A weak-foot score from earlier today on this card, still waiting for its
  // strong foot.
  function readDraft(card) {
    if (!card.per_foot) { return null; }
    var draft = null;
    try { draft = JSON.parse(getItem(DRAFT_KEY) || 'null'); } catch (e) { draft = null; }
    return draft && draft.card === card.slug && draft.date === localDate() &&
      typeof draft.weak === 'number' ? draft : null;
  }

  function bestLine(card, best) {
    if (best.weak === null && best.score === null) {
      return el('p', { class: 'deck-best', text: 'No score yet. This one sets it.' });
    }
    if (!card.per_foot) {
      return el('p', { class: 'deck-best', text: 'Your best: ' + scoreText(card, best.score) });
    }
    // A line each, so the two never wrap into one another on a small phone.
    var shown = function (v) { return v === null ? '-' : scoreText(card, v); };
    return el('p', { class: 'deck-best' }, [
      'Best, weak foot: ' + shown(best.weak), el('br'),
      'Best, strong foot: ' + shown(best.score)
    ]);
  }

  function savePlay(card, score, weak) {
    var play = makePlay({
      id: newId(),
      card: card.slug,
      date: localDate(),
      played_at: new Date().toISOString(),
      score: score,
      weak_score: weak
    }, false);
    // On the phone first. Sending it is a bonus that can happen later.
    updatePlays(function (list) { list.push(play); });
    sync();
    return play;
  }

  // A 0 is saved - nought corners is a real result - but it is not cheered.
  function verdict(card, value, best) {
    if (!counts(card, value) || value === 0) { return ''; }
    if (best === null) { return 'First score'; }
    return beats(card, value, best) ? 'New best!' : '';
  }

  function summary(stage, card, before, score, weak) {
    clear(stage);
    var lines = [];
    if (card.per_foot) {
      lines.push(resultLine('Weak foot', card, weak, verdict(card, weak, before.weak)));
      lines.push(resultLine('Strong foot', card, score, verdict(card, score, before.score)));
      var gap = Math.abs(score - weak);
      var weakWins = beats(card, weak, score);
      lines.push(el('p', {
        class: 'deck-gap',
        text: gap === 0 ? 'No gap between your feet!'
          : weakWins ? 'Your weak foot won!'
          : 'Gap: ' + scoreText(card, gap) + '. Close it next time.'
      }));
    } else {
      lines.push(resultLine('Score', card, score, verdict(card, score, before.score)));
    }
    add(stage, [el('div', { class: 'hero-kicker', text: 'Saved' })].concat(lines).concat([
      el('button', {
        type: 'button', class: 'btn mt',
        onclick: function () { renderCard(card); }
      }, ['Play it again']),
      el('a', { class: 'btn btn-quiet mt', href: '#', text: 'Back to my hand' })
    ]));
  }

  function resultLine(label, card, value, flag) {
    return el('div', { class: 'deck-result' }, [
      el('span', { class: 'deck-result-label', text: label }),
      el('span', { class: 'deck-result-num', text: scoreText(card, value) }),
      flag ? el('span', { class: 'deck-flag' + (flag === 'New best!' ? ' is-best' : ''), text: flag }) : null
    ]);
  }

  // --- the stepper ---------------------------------------------------------
  // Starts at 0, never at his best: a number he did not reach, saved with one
  // tap, would sit on his record for good.
  function stepper(stage, card, label, done) {
    var hasMax = card.out_of !== null && card.out_of !== undefined;
    var max = hasMax ? card.out_of : 999;
    var value = 0;
    var shown = el('div', { class: 'count-val', 'aria-live': 'polite', text: '0' });

    function set(v) {
      value = Math.max(0, Math.min(max, v));
      shown.textContent = String(value);
    }
    function btn(delta, cls) {
      return el('button', {
        type: 'button', class: cls,
        'aria-label': (delta > 0 ? 'Add ' : 'Take away ') + Math.abs(delta),
        onclick: function () { set(value + delta); }
      }, [(delta > 0 ? '+' : '−') + Math.abs(delta)]);
    }

    var what = card.score_label || 'score';
    add(stage, [
      el('p', { class: 'count-target', text: hasMax ? what + ', out of ' + card.out_of : what }),
      el('div', { class: 'counter counter-sm' }, [btn(-1, 'count-btn'), shown, btn(1, 'count-btn')]),
      el('div', { class: 'btn-row deck-fives' }, [btn(-5, 'btn btn-quiet'), btn(5, 'btn btn-quiet')]),
      el('button', { type: 'button', class: 'btn mt', onclick: function () { done(value); } }, [label])
    ]);
  }

  // --- the timed bar -------------------------------------------------------
  // Fills the bar, and that is all. No numbers, no text, no aria-valuenow:
  // nothing here may tell him how long is left. TestDeckScript reads this
  // function and fails if any of that creeps in. The time comes from
  // Date.now(), not from counting ticks, which drift and stall when the
  // screen sleeps.
  function runTimedBar(seconds, fill, onDone) {
    var total = seconds * 1000;
    var startedAt = Date.now();
    var finished = false;
    var timer = null;
    function frame() {
      var part = Math.min(1, (Date.now() - startedAt) / total);
      fill.style.transform = 'scaleX(' + part + ')';
      if (part >= 1 && !finished) {
        finished = true;
        clearInterval(timer);
        onDone();
      }
    }
    timer = setInterval(frame, 100);
    frame();
    return function stop() { finished = true; clearInterval(timer); };
  }

  function timedThenCount(stage, card, label, done) {
    var fill = el('div', { class: 'deck-timer-fill' });
    var bar = el('div', { class: 'deck-timer', role: 'progressbar', 'aria-label': 'Timer ready' }, [fill]);
    var shout = el('p', { class: 'deck-shout', 'aria-live': 'assertive' });
    var scoreBox = el('div');
    var start = el('button', { type: 'button', class: 'btn', onclick: go }, ['Start']);
    var skip = el('button', { type: 'button', class: 'btn btn-quiet mt', onclick: count }, ['Put the score in']);

    add(stage, [
      el('p', { class: 'count-target', text: 'Tap Start and go until it buzzes.' }),
      bar, shout, start, skip, scoreBox
    ]);

    function go() {
      var buzz = buzzer();
      var awake = holdAwake();
      start.hidden = true;
      skip.hidden = true;
      bar.classList.add('is-running');
      bar.setAttribute('aria-label', 'Timer running');
      var stop = runTimedBar(card.timer_seconds, fill, function () {
        awake();
        buzz();
        bar.classList.remove('is-running');
        bar.classList.add('is-done');
        bar.setAttribute('aria-label', 'Timer finished');
        shout.textContent = 'Stop!';
        count();
      });
      onLeave(function () { stop(); awake(); });
    }

    function count() {
      start.hidden = true;
      skip.hidden = true;
      if (!scoreBox.firstChild) { stepper(scoreBox, card, label, done); }
    }
  }

  // iPhones cannot vibrate and the silent switch mutes web audio, so the
  // buzz is a bonus; the full bar and "Stop!" are what actually tell him.
  // iOS only lets a page make sound from a tap, so the audio is woken up
  // inside the Start tap with a silent blip and used at the end.
  var audio = null;
  function buzzer() {
    try {
      var AC = window.AudioContext || window.webkitAudioContext;
      if (AC && !audio) { audio = new AC(); }
      if (audio) {
        if (audio.resume) { audio.resume(); }
        beep(0, 0.01, 0);
      }
    } catch (e) { audio = null; }
    return function () {
      if (navigator.vibrate) { try { navigator.vibrate([200, 100, 200]); } catch (e) { /* no buzz */ } }
      beep(0, 0.2, 0.3);
      beep(0.3, 0.2, 0.3);
    };
  }

  function beep(after, length, volume) {
    if (!audio) { return; }
    try {
      var osc = audio.createOscillator();
      var gain = audio.createGain();
      osc.frequency.value = 880;
      gain.gain.value = volume;
      osc.connect(gain);
      gain.connect(audio.destination);
      osc.start(audio.currentTime + after);
      osc.stop(audio.currentTime + after + length);
    } catch (e) { /* no sound */ }
  }

  // Thirty seconds is as long as many phones stay awake untouched.
  function holdAwake() {
    var lock = null;
    var released = false;
    if (navigator.wakeLock && navigator.wakeLock.request) {
      navigator.wakeLock.request('screen').then(function (l) {
        if (released) { l.release(); } else { lock = l; }
      }).catch(function () { /* stays as it is */ });
    }
    return function () {
      released = true;
      if (lock) { lock.release().catch(function () {}); lock = null; }
    };
  }

  // --- the stopwatch -------------------------------------------------------
  // Counts up, and he stops it. The time is Date.now() minus when he started.
  function stopwatch(stage, label, done) {
    var shown = el('div', { class: 'clock deck-watch', 'aria-live': 'off', text: tenthsText(0) });
    var startedAt = 0;
    var result = 0;
    var timer = null;
    var awake = function () {};

    function tenths() { return Math.floor((Date.now() - startedAt) / 100); }
    function halt() { clearInterval(timer); timer = null; awake(); }

    var startBtn = el('button', {
      type: 'button', class: 'btn',
      onclick: function () {
        startedAt = Date.now();
        awake = holdAwake();
        timer = setInterval(function () { shown.textContent = tenthsText(tenths()); }, 100);
        startBtn.hidden = true;
        stopBtn.hidden = false;
      }
    }, ['Start']);
    var stopBtn = el('button', {
      type: 'button', class: 'btn', hidden: true,
      onclick: function () {
        result = tenths();
        halt();
        shown.textContent = tenthsText(result);
        stopBtn.hidden = true;
        againBtn.hidden = false;
        saveBtn.hidden = result <= 0;
      }
    }, ['Stop']);
    var againBtn = el('button', {
      type: 'button', class: 'btn btn-quiet mt', hidden: true,
      onclick: function () {
        result = 0;
        shown.textContent = tenthsText(0);
        againBtn.hidden = true;
        saveBtn.hidden = true;
        startBtn.hidden = false;
      }
    }, ['Try again']);
    var saveBtn = el('button', {
      type: 'button', class: 'btn mt', hidden: true,
      onclick: function () { done(result); }
    }, [label]);

    onLeave(halt);
    add(stage, [shown, startBtn, stopBtn, saveBtn, againBtn]);
  }

  // --- status --------------------------------------------------------------
  var signedOut = false;

  function paintStatus() {
    var plays = loadPlays();
    var waiting = plays.filter(function (p) { return !p.synced; });
    var stuck = waiting.filter(function (p) { return p.refused; });
    clear(statusEl);
    warnEl.hidden = storageOk && !writeLost;
    if (signedOut) {
      add(statusEl, [
        'Saved on this phone, not backed up.',
        el('a', { class: 'btn btn-quiet mt', href: LOGIN_URL + '?next=' + encodeURIComponent(location.pathname), text: 'Sign in to back it up' })
      ]);
      return;
    }
    if (waiting.length) {
      add(statusEl, [waiting.length + (waiting.length === 1 ? ' score is' : ' scores are') +
        ' saved on this phone, and will be backed up when there is signal.']);
    } else if (plays.length) {
      add(statusEl, ['Every score is backed up.']);
    }
    if (stuck.length) {
      add(statusEl, [' ' + stuck.length + ' could not be backed up yet.']);
    }
  }

  // --- sync ----------------------------------------------------------------
  // The token comes from the cookie at send time. The one baked into the page
  // goes stale at the next sign-in, and the page he has is often a cached one.
  function csrfToken() {
    var m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : (root.getAttribute('data-csrf') || '');
  }

  // Only a JSON answer is an answer. Anything else - the login page, an
  // error page, the offline page - means "try again later".
  function isJson(res) {
    return (res.headers.get('Content-Type') || '').indexOf('application/json') === 0;
  }

  // What the server is sent: the play without the phone's own bookkeeping.
  function wire(play) {
    var out = makePlay(play);
    delete out.synced;
    delete out.refused;
    return out;
  }

  var syncing = false;

  function sync() {
    if (syncing || !window.fetch || !PLAYS_URL) { paintStatus(); return; }
    // Ones never refused go first, so a stuck play cannot hold up the rest.
    var waiting = loadPlays().filter(function (p) { return !p.synced; });
    if (!waiting.length) { paintStatus(); return; }
    waiting.sort(function (a, b) { return (a.refused ? 1 : 0) - (b.refused ? 1 : 0); });
    syncing = true;
    post(waiting.slice(0, MAX_BATCH), true).then(function (savedCount) {
      syncing = false;
      paintStatus();
      // Plays still waiting - the next batch, or a card he finished while
      // this one was in flight - go now, as long as this round moved. A
      // round that saved nothing stops, or a refused play would loop.
      var left = loadPlays().some(function (p) { return !p.synced; });
      if (savedCount > 0 && left) { sync(); }
    }, function () {
      syncing = false;
      paintStatus();
    });
  }

  function post(batch, retry) {
    return fetch(PLAYS_URL, {
      method: 'POST',
      credentials: 'same-origin',
      cache: 'no-store',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
      body: JSON.stringify({ plays: batch.map(wire) })
    }).then(function (res) {
      if (res.status === 401) { signedOut = true; return 0; }
      // A stale token: read the cookie again and have one more go.
      if (res.status === 403 && retry) { return post(batch, false); }
      if (!res.ok || !isJson(res)) { return 0; }
      signedOut = false;
      return res.json().then(applyAnswer);
    });
  }

  // Marks plays sent, and notes why any were refused. Removes nothing.
  function applyAnswer(body) {
    var saved = {};
    var refused = {};
    var savedCount = 0;
    (body && body.saved || []).forEach(function (id) { saved[id] = true; });
    (body && body.refused || []).forEach(function (r) {
      if (r && r.id) { refused[r.id] = r.reason || 'refused'; }
    });
    updatePlays(function (list) {
      savedCount = 0;
      list.forEach(function (play) {
        if (saved[play.id]) {
          if (!play.synced) { savedCount++; }
          play.synced = true;
          play.refused = null;
        } else if (refused[play.id]) {
          play.refused = refused[play.id];
        }
      });
    });
    return savedCount;
  }

  // Whatever the server holds that the phone does not - a reset phone, a new
  // phone, cleared site data - comes back here. Both copies kept: the phone's
  // own wins where the two have the same id.
  function restore() {
    if (!window.fetch || !PLAYS_URL) { return Promise.resolve(false); }
    return fetch(PLAYS_URL, { credentials: 'same-origin', cache: 'no-store' }).then(function (res) {
      if (res.status === 401) { signedOut = true; return false; }
      if (!res.ok || !isJson(res)) { return false; }
      signedOut = false;
      return res.json().then(function (body) {
        var changed = false;
        if (!body || !Array.isArray(body.plays)) { return false; }
        updatePlays(function (list) {
          var mine = {};
          var theirs = {};
          list.forEach(function (play) { mine[play.id] = play; });
          body.plays.forEach(function (s) { theirs[s.id] = true; });
          // The server has lost one the phone thought was sent - a disk
          // restored from backup, say. Mark it unsent so sync() sends it
          // again, rather than saying "backed up" about a play that is not.
          list.forEach(function (play) {
            if (play.synced && !theirs[play.id]) { play.synced = false; play.refused = null; changed = true; }
          });
          body.plays.forEach(function (s) {
            var local = mine[s.id];
            if (local) {
              if (!local.synced) { local.synced = true; local.refused = null; changed = true; }
              return;
            }
            list.push(makePlay(s, true));
            changed = true;
          });
        });
        return changed;
      });
    }).catch(function () { return false; });
  }

  // --- routing -------------------------------------------------------------
  // One page, routed by the hash, so the phone's back button goes back to the
  // hand and the one cached page serves every card.
  function route(keepScroll) {
    var hash = location.hash.replace(/^#/, '');
    if (hash.indexOf('card/') === 0 && BY_SLUG[hash.slice(5)]) {
      renderCard(BY_SLUG[hash.slice(5)]);
    } else if (hash === 'all') {
      renderAll(keepScroll);
    } else {
      renderHand(keepScroll);
    }
  }

  // A redraw from the background must never land on a card he is halfway
  // through scoring.
  function refreshList() { if (!onCard) { route(true); } else { paintStatus(); } }

  function backUp() {
    restore().then(function (changed) {
      if (changed) { refreshList(); }
      sync();
    });
  }

  window.addEventListener('hashchange', function () { route(); });
  window.addEventListener('online', backUp);
  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState !== 'visible') { return; }
    // Left open overnight: a new day is a new hand.
    if (renderedDate !== localDate()) { refreshList(); }
    sync();
  });

  route();
  backUp();
})();
