/* The deck: deals his hand, runs a card, keeps every play, backs it up.

   Everything on / is drawn here from what the phone already holds - the
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
  // Missing on a page cached before the switch-over (leg 3c): no link then.
  var BEFORE_URL = root.getAttribute('data-before-url');

  // --- cards ---------------------------------------------------------------
  // Arrive sorted by Card.order, which also puts the packs in their order.
  var CARDS = JSON.parse(dataEl.textContent || '[]');
  var BY_SLUG = {};
  var BY_PACK = {};
  var PACK_ORDER = [];
  var BY_MOVE = {};        // move slug -> {1: card, 2: card, 3: card}
  var MOVE_ORDER = [];
  CARDS.forEach(function (card) {
    BY_SLUG[card.slug] = card;
    if (!BY_PACK[card.pack]) { BY_PACK[card.pack] = []; PACK_ORDER.push(card.pack); }
    BY_PACK[card.pack].push(card);
    if (card.move) {
      if (!BY_MOVE[card.move]) { BY_MOVE[card.move] = {}; MOVE_ORDER.push(card.move); }
      BY_MOVE[card.move][card.level] = card;
    }
  });

  // The game's numbers, from deck_rules.py. Absent on a page cached before
  // the game existed: then the game stays hidden and plays go unstamped,
  // which the server stores as worth nothing. Never a number of our own here.
  var RULES = null;
  try { RULES = JSON.parse((document.getElementById('deck-rules') || {}).textContent || 'null'); } catch (e) { RULES = null; }
  // The one fallback: a page cached before the game still says "play any 3".
  var SESSION_CARDS = RULES ? RULES.session_cards : 3;

  // The deck's badges, as baked into the page: code, name, emoji,
  // description, legend, earned. Earned is refreshed from the server cache.
  var BADGES = [];
  try { BADGES = JSON.parse((document.getElementById('deck-badges') || {}).textContent || '[]'); } catch (e) { BADGES = []; }

  // What only the server can know - badges awarded at sync, and the run of
  // goal weeks up to last week. A cache, rebuilt from each answer; badges in
  // it are only ever added, because already earned stays earned.
  var SERVER_KEY = 'will-deck-server-v1';

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
      // The stamp travels with the play everywhere, or wire() and restore()
      // would quietly drop what it was worth.
      points: nullable(fields.points), medal: nullable(fields.medal), bests: nullable(fields.bests),
      synced: !!synced, refused: null
    };
  }

  function nullable(v) { return v === undefined ? null : v; }

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
    // Starts from his old app's best on the same exercise, when there is one
    // (deck_rules.HISTORY_CARDS), so beating it is a real personal best.
    var start = RULES && RULES.starting_bests && RULES.starting_bests[card.slug];
    var best = { score: start ? start.score : null, weak: start ? start.weak : null };
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

  // --- the game ------------------------------------------------------------
  // A play is stamped once, when he saves it: points, medal, bests. Everything
  // after that - his total, his level, what is unlocked - adds up stamps, so
  // a change to the numbers in deck_rules.py never takes back what he earned.

  var MEDAL_WORDS = ['', 'Bronze', 'Silver', 'Gold'];

  // A word and stars, never a colour on its own.
  function medalText(medal) {
    return medal ? MEDAL_WORDS[medal] + ' ' + new Array(medal + 1).join('★') : '';
  }

  function thisMonday() {
    var d = new Date();
    d.setDate(d.getDate() - ((d.getDay() + 6) % 7));
    return localDate(d);
  }

  // This week's entry in the baked calendar: {monday, move, test}.
  function thisWeek() {
    if (!RULES) { return null; }
    var monday = thisMonday();
    for (var i = 0; i < RULES.calendar.length; i++) {
      if (RULES.calendar[i].monday === monday) { return RULES.calendar[i]; }
    }
    return null;
  }

  function skillMove() { var week = thisWeek(); return week ? week.move : null; }

  function moveName(move) {
    var first = BY_MOVE[move] && (BY_MOVE[move][1] || BY_MOVE[move][2] || BY_MOVE[move][3]);
    return first ? first.name.split(':')[0] : move;
  }

  // The part of a move card's name after the move: "on the spot".
  function levelName(card) {
    var parts = card.name.split(': ');
    return parts.length > 1 ? parts[1].charAt(0).toUpperCase() + parts[1].slice(1) : card.name;
  }

  // The worse foot of a play: a medal means both feet reached it.
  function worseFoot(card, score, weak) {
    if (!counts(card, score) || !counts(card, weak)) { return null; }
    return beats(card, score, weak) ? weak : score;
  }

  function medalFor(card, score, weak) {
    var targets = card.medals || [];
    var value = card.per_foot ? worseFoot(card, score, weak) : score;
    if (!counts(card, value)) { return 0; }
    for (var i = 2; i >= 0; i--) {
      var target = targets[i];
      if (target === null || target === undefined) { continue; }
      if (card.scoring === 'time' ? value <= target : value >= target) { return i + 1; }
    }
    return 0;
  }

  // A best of 0 is no best to beat: otherwise saving 0 first, by accident or
  // on purpose, turns any next score into a "new best" worth the bonus.
  function realBest(value) { return value === 0 ? null : value; }

  // What this play is worth, worked out once. `before` is his best on the
  // card before this play; a first score is not a personal best.
  function stamp(card, score, weak, before) {
    if (!RULES) { return { points: null, medal: null, bests: null }; }
    var P = RULES.points;
    var bests = 0;
    if (card.scoring !== 'none') {
      if (counts(card, score) && realBest(before.score) !== null && beats(card, score, before.score)) { bests++; }
      if (card.per_foot && counts(card, weak) && realBest(before.weak) !== null && beats(card, weak, before.weak)) { bests++; }
    }
    var points = P.base;
    if (card.per_foot || RULES.weak_foot_cards.indexOf(card.slug) >= 0) { points += P.weak_foot; }
    points += bests * P.best;
    if (card.move && card.move === skillMove()) { points *= P.skill_multiplier; }
    return {
      points: points,
      medal: card.scoring === 'none' ? 0 : medalFor(card, score, weak),
      bests: bests
    };
  }

  function totalPoints(plays) {
    var total = RULES ? RULES.starting_points : 0;
    plays.forEach(function (play) { total += play.points || 0; });
    return total;
  }

  // {index, name, next (name or null), part (0-1 of the way to next)}
  function levelFor(points) {
    var levels = RULES.levels;
    var i = 0;
    while (i + 1 < levels.length && points >= levels[i + 1].points) { i++; }
    var next = levels[i + 1];
    return {
      index: i,
      name: levels[i].name,
      next: next ? next.name : null,
      part: next ? (points - levels[i].points) / (next.points - levels[i].points) : 1
    };
  }

  function bestMedal(slug, plays) {
    var best = 0;
    plays.forEach(function (play) {
      if (play.card === slug && (play.medal || 0) > best) { best = play.medal; }
    });
    return best;
  }

  // The card one level down that has to be gold first, or null.
  function gateFor(card) {
    if (!card.move || !card.level || card.level <= 1) { return null; }
    return (BY_MOVE[card.move] || {})[card.level - 1] || null;
  }

  // Level 1 is always open; a higher level opens on gold one level down.
  function isOpen(card, plays) {
    if (!RULES) { return true; }
    var gate = gateFor(card);
    return !gate || bestMedal(gate.slug, plays) === 3;
  }

  // The highest open level of a move.
  function topOpen(move, plays) {
    var levels = BY_MOVE[move] || {};
    for (var level = 3; level >= 1; level--) {
      if (levels[level] && isOpen(levels[level], plays)) { return levels[level]; }
    }
    return null;
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

    // A locked move level is never dealt.
    function take(pack) {
      var all = (BY_PACK[pack] || []).filter(function (c) {
        return !taken[c.slug] && isOpen(c, plays);
      });
      var fresh = all.filter(function (c) { return !avoid[c.slug]; });
      var pool = fresh.length ? fresh : all;
      if (!pool.length) { return false; }
      add1(pool[Math.floor(Math.random() * pool.length)]);
      return true;
    }
    function add1(card) {
      hand.push(card.slug);
      taken[card.slug] = true;
      usedPacks[card.pack] = true;
    }

    // The Moves card is the skill of the week at its highest open level, so
    // the double points are always in his hand.
    var skill = skillMove();
    var skillCard = skill ? topOpen(skill, plays) : null;
    if (skillCard) { add1(skillCard); } else { take(MOVES); }
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
    var plays = loadPlays();
    // Dealt again if a card in it was retired, or is locked - a hand stored
    // before the game existed may hold a level he has not opened.
    var ok = stored && stored.date === today && Array.isArray(stored.slugs) &&
      stored.slugs.length && stored.slugs.every(function (s) {
        return BY_SLUG[s] && isOpen(BY_SLUG[s], plays);
      });
    if (ok) {
      // He just won gold on the skill card in his hand: swap in the level it
      // opened, so the double points follow him up without a re-deal.
      var skill = skillMove();
      var top = skill ? topOpen(skill, plays) : null;
      var slugs = stored.slugs.map(function (s) {
        return top && BY_SLUG[s].move === skill && s !== top.slug ? top.slug : s;
      });
      if (slugs.join() !== stored.slugs.join()) {
        setItem(HAND_KEY, JSON.stringify({ date: today, slugs: slugs }));
      }
      return slugs;
    }
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
    if (!isCard) { add(root, [badgeFlash()]); }
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
  // Locked, best medal and double points are all said in words.
  function cardRow(card, done, plays) {
    var locked = !isOpen(card, plays);
    var medal = bestMedal(card.slug, plays);
    var double = RULES && card.move && card.move === skillMove();
    return el('a', {
      class: 'drill-row deck-row' + (done ? ' is-done' : '') + (locked ? ' is-locked' : ''),
      href: '#card/' + card.slug
    }, [
      el('span', { class: 'tick', 'aria-hidden': 'true', text: done ? '✓' : '' }),
      el('span', { class: 'drill-main' }, [
        el('span', { class: 'drill-name', text: card.name }),
        el('span', { class: 'drill-meta' }, [
          locked ? el('span', { class: 'deck-lock', text: 'Locked' }) : null,
          el('span', { text: card.pack_name }),
          kitText(card) ? el('span', { text: kitText(card) }) : null,
          double && !locked ? el('span', { class: 'deck-double', text: 'Double points' }) : null,
          medal ? el('span', { class: 'deck-medal', text: medalText(medal) }) : null,
          done ? el('span', { class: 'deck-done', text: 'Done' }) : null
        ])
      ]),
      locked ? null : el('span', { class: 'chev', 'aria-hidden': 'true', text: '›' })
    ]);
  }

  // Level, points and the skill of the week, at the top of the hand.
  function gameStrip(plays) {
    if (!RULES) { return null; }
    var points = totalPoints(plays);
    var level = levelFor(points);
    var fill = el('div', { class: 'bar-fill' + (level.part > 0 ? '' : ' is-zero') });
    fill.style.width = Math.round(level.part * 100) + '%';
    var skill = skillMove();
    // Kept light: the cards below are the job, this is the scoreboard.
    return el('div', { class: 'card deck-game' }, [
      el('div', { class: 'deck-level' }, [
        el('span', { class: 'deck-level-name', text: level.name }),
        el('span', { class: 'deck-points', text: points + ' points' })
      ]),
      level.next ? el('div', { class: 'bar-track deck-bar', role: 'img', 'aria-label': 'On the way to ' + level.next }, [fill]) : null,
      el('p', { class: 'deck-next', text: level.next ? 'Next: ' + level.next : 'Top level. Legend!' }),
      RULES.starting_points > 0
        ? el('p', { class: 'deck-next', text: 'Includes ' + RULES.starting_points +
          (RULES.starting_points === 1 ? ' point' : ' points') + ' from before the cards.' })
        : null,
      skill ? el('p', { class: 'deck-skill' }, [
        'Skill of the week: ', el('strong', { text: moveName(skill) }), '. Double points.'
      ]) : null,
      weekBlock(plays)
    ]);
  }

  // The album and badges are destinations, not the day's job: under the
  // cards, so the cards stay on the first screen.
  function gameLinks() {
    if (!RULES) { return null; }
    return el('div', { class: 'deck-links' }, [
      el('a', { class: 'deck-back', href: '#album', text: 'Sticker album ›' }),
      // Not on a page cached before the badges existed: it has none to show.
      // Since the switch-over this is a shortcut to the Progress tab.
      BADGES.length ? el('a', { class: 'deck-back', href: '#progress', text: 'Badges ›' }) : null
    ]);
  }

  // In a test week, the Test week row leads the list, looking like a card -
  // a side quest, never louder than the cards.
  function testRow() {
    var week = thisWeek();
    if (!week || !week.test || !RULES.test_cards) { return null; }
    var monday = thisMonday();
    var done = {};
    loadPlays().forEach(function (play) { if (play.date >= monday) { done[play.card] = true; } });
    var count = RULES.test_cards.filter(function (slug) { return done[slug]; }).length;
    var all = RULES.test_cards.length;
    return el('a', { class: 'drill-row deck-row deck-test-row', href: '#test' }, [
      el('span', { class: 'drill-main' }, [
        el('span', { class: 'drill-name', text: 'Test week' }),
        el('span', { class: 'drill-meta' }, [el('span', {
          text: count === all ? 'All ' + all + ' done!' : count + ' of ' + all + ' test cards done'
        })])
      ]),
      el('span', { class: 'chev', 'aria-hidden': 'true', text: '›' })
    ]);
  }

  // --- the week ------------------------------------------------------------
  // Sessions this week from the phone's own plays, so it is right offline. A
  // session is SESSION_CARDS different cards on one day, free play included;
  // the same rule is in deck_rules.session_dates - change both.
  function sessionsBetween(plays, from, to) {
    var perDay = {};
    plays.forEach(function (play) {
      if (play.date < from || play.date > to) { return; }
      (perDay[play.date] = perDay[play.date] || {})[play.card] = true;
    });
    return Object.keys(perDay).filter(function (day) {
      return Object.keys(perDay[day]).length >= RULES.session_cards;
    }).length;
  }

  function addDays(isoDate, days) {
    var p = isoDate.split('-');
    return localDate(new Date(+p[0], +p[1] - 1, +p[2] + days));
  }

  function weekStatus(plays) {
    var monday = thisMonday();
    var sessions = sessionsBetween(plays, monday, localDate());
    var hit = sessions >= RULES.goal_sessions;
    // Weeks in a row: the server's run to last week, plus this week once it
    // is a goal week. If the server's figure is a week old - Monday, before
    // the phone has synced - roll it on from his own plays, or the run would
    // vanish every Monday morning and read as broken.
    var gw = loadServer().goal_weeks;
    var before = null;
    if (gw && gw.monday === monday) {
      before = gw.before;
    } else if (gw && gw.monday === addDays(monday, -7)) {
      var lastWeek = sessionsBetween(plays, gw.monday, addDays(monday, -1));
      before = lastWeek >= RULES.goal_sessions ? gw.before + 1 : 0;
    }
    var run = before === null ? null : before + (hit ? 1 : 0);
    return { sessions: sessions, goal: RULES.goal_sessions, hit: hit, run: run };
  }

  // The weekly bar: one colour, said in words. Weeks in a row only from 1 -
  // a "0 weeks" reads as a telling-off.
  function weekBlock(plays) {
    if (RULES.goal_sessions === undefined) { return null; }  // a page cached before 2b
    var week = weekStatus(plays);
    var fill = el('div', { class: 'bar-fill' + (week.sessions ? '' : ' is-zero') });
    fill.style.width = Math.round(Math.min(1, week.sessions / week.goal) * 100) + '%';
    return el('div', { class: 'deck-week' }, [
      el('div', { class: 'deck-week-row' }, [
        el('span', {}, [
          el('strong', { text: week.hit ? 'Weekly goal done!' : 'This week: ' }),
          week.hit ? '' : week.sessions + ' of ' + week.goal + ' sessions'
        ]),
        week.run ? el('span', { class: 'deck-run', text: week.run + (week.run === 1 ? ' week' : ' weeks') + ' in a row' }) : null
      ]),
      el('div', { class: 'bar-track deck-bar', role: 'img', 'aria-label': week.sessions + ' of ' + week.goal + ' sessions this week' }, [fill])
    ]);
  }

  // --- badges --------------------------------------------------------------
  // Just awarded at sync: celebrated on the next screen he sees that is not
  // a card he is halfway through, then not again.
  function badgeFlash() {
    var s = loadServer();
    if (!s.unseen.length) { return null; }
    // Only the ones this page can name are shown and cleared: a page cached
    // before a badge existed keeps it for the next page that knows it.
    var known = s.unseen.filter(badgeByCode);
    if (!known.length) { return null; }
    var lines = known.map(badgeByCode).map(function (badge) {
      return el('p', { class: 'deck-levelup' }, [
        el('span', { 'aria-hidden': 'true', text: badge.emoji + ' ' }),
        'New badge: ' + badge.name + '!'
      ]);
    });
    s.unseen = s.unseen.filter(function (code) { return !badgeByCode(code); });
    setItem(SERVER_KEY, JSON.stringify(s));
    return lines.length ? el('div', { class: 'card deck-flash', role: 'status' }, lines) : null;
  }

  // The Progress tab (leg 3c): his level and week, the album, every badge he
  // has, and the door to Before the cards. Drawn here, not on the server, so
  // it adds up the same plays as the hand and is right with no signal.
  function renderProgress(keepScroll) {
    var earned = loadServer().earned;
    var rows = BADGES.map(function (badge) {
      var has = badge.earned || earned.indexOf(badge.code) >= 0;
      return el('div', { class: 'deck-badge' + (has ? ' is-earned' : '') }, [
        el('span', { class: 'deck-badge-em', 'aria-hidden': 'true', text: badge.emoji }),
        el('span', { class: 'deck-badge-main' }, [
          el('span', { class: 'deck-badge-name', text: badge.name }),
          el('span', { class: 'deck-badge-desc', text: badge.description }),
          el('span', { class: 'deck-badge-state', text: has ? 'Earned' : 'Not yet' }),
          badge.legend ? el('span', { class: 'badge-legend', text: 'Legend' }) : null
        ])
      ]);
    });
    show([
      el('h1', { class: 'deck-title', text: 'Progress' }),
      gameStrip(loadPlays()),
      // Two doors under the scoreboard, before the long list of badges.
      el('div', { class: 'deck-doors' }, [
        el('a', { class: 'btn btn-quiet', href: '#album', text: 'Sticker album ›' }),
        BEFORE_URL ? el('a', { class: 'btn btn-quiet', href: BEFORE_URL, text: 'Before the cards ›' }) : null
      ]),
      el('h2', { text: 'My badges' }),
      el('p', { class: 'deck-note', text: 'New badges arrive when the phone has signal.' })
    ].concat(rows), false, keepScroll);
  }

  // --- test week -----------------------------------------------------------
  function renderTest(keepScroll) {
    var plays = loadPlays();
    var monday = thisMonday();
    var doneThisWeek = {};
    plays.forEach(function (play) { if (play.date >= monday) { doneThisWeek[play.card] = true; } });
    var cards = RULES.test_cards.map(function (slug) { return BY_SLUG[slug]; }).filter(Boolean);
    var left = cards.filter(function (card) { return !doneThisWeek[card.slug]; }).length;
    show([
      el('a', { class: 'deck-back', href: '#', text: '‹ Back to my hand' }),
      el('h1', { class: 'deck-title', text: 'Test week' }),
      el('p', { class: 'deck-best', text: left ? 'Play all six this week to earn Test week done.' : 'All six done. Brilliant!' }),
      el('div', { class: 'drill-list' }, cards.map(function (card) {
        return cardRow(card, doneThisWeek[card.slug], plays);
      }))
    ], false, keepScroll);
  }

  // What a free play just earned, shown once on the next screen drawn.
  var flash = null;
  function flashCard() {
    var lines = flash;
    flash = null;
    if (!lines || !lines.length) { return null; }
    return el('div', { class: 'card deck-flash', role: 'status' },
      [el('div', { class: 'hero-kicker', text: 'Football logged' })].concat(lines));
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
        // Like every other play: say what it was worth, and a level-up it
        // causes is shown, not just quietly applied.
        var was = gameState(card);
        var play = savePlay(card, null, null, { score: null, weak: null });
        flash = rewardLines(card, play, was);
        route();
      }
    }, [card.name]);
  }

  // --- the hand ------------------------------------------------------------
  function renderHand(keepScroll) {
    var plays = loadPlays();
    var done = playedOn(plays, localDate());
    var hand = currentHand();
    // Free play is one of the three, like any other card (deck_rules).
    var count = Object.keys(done).length;
    var size = SESSION_CARDS;
    var sub = count === 0 ? 'Pick one to start.'
      : count >= size ? count + ' done. That is a session!'
      : 'Done today: ' + count + ' of ' + size;

    show([
      el('div', { class: 'card card-hero' }, [
        el('div', { class: 'hero-kicker', text: 'Your hand' }),
        el('h1', { class: 'hero-big', text: 'Play any ' + size }),
        el('p', { class: 'hero-sub', text: sub })
      ]),
      flashCard(),
      gameStrip(plays),
      el('div', { class: 'drill-list' }, [testRow()].concat(hand.map(function (slug) {
        return cardRow(BY_SLUG[slug], done[slug], plays);
      }))),
      freePlayButton(done[FREE_PLAY]),
      el('a', { class: 'btn btn-quiet mt', href: '#all', text: 'Pick from the whole deck' }),
      // Last, so a stray thumb does not throw his hand away.
      el('button', {
        type: 'button', class: 'btn btn-quiet mt',
        onclick: function () { dealAgain(hand); }
      }, ['Deal again']),
      gameLinks()
    ], false, keepScroll);
  }

  // --- the whole deck ------------------------------------------------------
  // A plain list under pack headings: everything is reachable by scrolling
  // down, nothing by scrolling sideways.
  function renderAll(keepScroll) {
    var plays = loadPlays();
    var done = playedOn(plays, localDate());
    var rows = [];
    PACK_ORDER.forEach(function (pack) {
      var cards = BY_PACK[pack];
      rows.push(el('div', { class: 'drill-group' }, [
        el('span', { class: 'drill-group-name', text: cards[0].pack_name }),
        el('span', { class: 'drill-group-count', text: String(cards.length) })
      ]));
      cards.forEach(function (card) { rows.push(cardRow(card, done[card.slug], plays)); });
    });
    show([
      el('a', { class: 'deck-back', href: '#', text: '‹ Back to my hand' }),
      el('div', { class: 'drill-list' }, rows)
    ], false, keepScroll);
  }

  // --- the sticker album ---------------------------------------------------
  // Every move, every level, empty slots and locked ones included, so he can
  // see what there is to win. A medal is a word and stars; a lock says what
  // opens it.
  function renderAlbum(keepScroll) {
    var plays = loadPlays();
    var skill = skillMove();
    var blocks = MOVE_ORDER.map(function (move) {
      var slots = [1, 2, 3].map(function (level) {
        var card = BY_MOVE[move][level];
        if (!card) { return null; }
        var medal = bestMedal(card.slug, plays);
        var open = isOpen(card, plays);
        var gate = gateFor(card);
        return el(open ? 'a' : 'div', {
          class: 'deck-slot' + (medal ? ' has-medal' : '') + (open ? '' : ' is-locked'),
          href: open ? '#card/' + card.slug : null
        }, [
          el('span', { class: 'deck-slot-level', text: 'Level ' + level + ': ' + levelName(card) }),
          el('span', {
            class: 'deck-slot-medal',
            text: !open ? 'Locked. Gold on level ' + gate.level + ' opens it.'
              : medal ? medalText(medal) : 'No medal yet'
          })
        ]);
      });
      return el('div', { class: 'deck-album-move' }, [
        el('h2', { class: 'deck-album-name' }, [
          moveName(move),
          move === skill ? el('span', { class: 'deck-double', text: 'Skill of the week' }) : null
        ]),
        el('div', { class: 'deck-slots' }, slots)
      ]);
    });
    show([
      el('a', { class: 'deck-back', href: '#', text: '‹ Back to my hand' }),
      el('h1', { class: 'deck-title', text: 'Sticker album' }),
      el('p', { class: 'deck-best', text: 'Gold on a level opens the next one.' })
    ].concat(blocks), false, keepScroll);
  }

  // --- a card --------------------------------------------------------------
  function renderCard(card) {
    var plays = loadPlays();
    var before = bestsFor(card, plays);
    var stage = el('div', { class: 'card deck-stage' });
    var bestEl = bestLine(card, before);
    var medal = bestMedal(card.slug, plays);
    var gate = gateFor(card);
    var locked = !isOpen(card, plays);
    var double = RULES && card.move && card.move === skillMove();

    show([
      el('a', { class: 'deck-back', href: '#', text: '‹ Back to my hand' }),
      el('h1', { class: 'deck-title', text: card.name }),
      el('p', { class: 'drill-meta deck-meta' }, [
        el('span', { text: card.pack_name }),
        kitText(card) ? el('span', { text: kitText(card) }) : null,
        double && !locked ? el('span', { class: 'deck-double', text: 'Double points this week' }) : null
      ]),
      // Said before the instructions, so he does not read the whole card
      // first and then find out he cannot play it.
      // The same words as the album, for the same rule.
      locked ? el('p', { class: 'deck-locked', text: 'Locked. Gold on level ' + gate.level + ' (' + levelName(gate) + ') opens it.' }) : null,
      el('p', { class: 'instructions', text: card.instructions }),
      el('div', { class: 'cue', text: card.cue }),
      locked || card.scoring === 'none' ? null : bestEl,
      medal ? el('p', { class: 'deck-medal-line', text: 'Your medal: ' + medalText(medal) }) : null,
      stage
    ], true);

    // A locked level can be read, not played: it says what opens it.
    if (locked) {
      add(stage, [
        el('a', { class: 'btn', href: '#card/' + gate.slug, text: 'Go to ' + levelName(gate) })
      ]);
      return;
    }

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
      // How things stood before this play, to say what it changed.
      var was = gameState(card);
      var play = savePlay(card, score, weak, before);
      setItem(DRAFT_KEY, 'null');
      var now = bestLine(card, bestsFor(card, loadPlays()));
      bestEl.parentNode.replaceChild(now, bestEl);
      bestEl = now;
      summary(stage, card, before, score, weak, play, was);
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
    // A 0 is no best to beat (realBest), so it is not shown as his best and
    // then the next score called a first.
    if (realBest(best.weak) === null && realBest(best.score) === null) {
      return el('p', { class: 'deck-best', text: 'No score yet. This one sets it.' });
    }
    if (!card.per_foot) {
      // Still his old app's best, not yet beaten on the card: say so, or a
      // number on a card he has never played looks like a mistake.
      var start = RULES && RULES.starting_bests && RULES.starting_bests[card.slug];
      var fromBefore = start && best.score === start.score;
      return el('p', { class: 'deck-best', text: 'Your best: ' + scoreText(card, best.score) +
        (fromBefore ? ' (from before)' : '') });
    }
    // A line each, so the two never wrap into one another on a small phone.
    var shown = function (v) { return v === null ? '-' : scoreText(card, v); };
    return el('p', { class: 'deck-best' }, [
      'Best, weak foot: ' + shown(best.weak), el('br'),
      'Best, strong foot: ' + shown(best.score)
    ]);
  }

  // `before` is his best on the card before this play, for the stamp.
  function savePlay(card, score, weak, before) {
    var worth = stamp(card, score, weak, before);
    var play = makePlay({
      id: newId(),
      card: card.slug,
      date: localDate(),
      played_at: new Date().toISOString(),
      score: score,
      weak_score: weak,
      points: worth.points,
      medal: worth.medal,
      bests: worth.bests
    }, false);
    // On the phone first. Sending it is a bonus that can happen later.
    updatePlays(function (list) { list.push(play); });
    sync();
    return play;
  }

  // A 0 is saved - nought corners is a real result - but it is not cheered.
  function verdict(card, value, best) {
    if (!counts(card, value) || value === 0) { return ''; }
    if (realBest(best) === null) { return 'First score'; }
    return beats(card, value, best) ? 'New best!' : '';
  }

  // His level, and whether the next level of this move was open, so the
  // summary can say what the play just changed.
  function gameState(card) {
    if (!RULES) { return null; }
    var plays = loadPlays();
    var next = card.move ? (BY_MOVE[card.move] || {})[card.level + 1] : null;
    return {
      level: levelFor(totalPoints(plays)).index,
      next: next || null,
      nextOpen: next ? isOpen(next, plays) : true
    };
  }

  // What the play was worth: points, medal, anything it opened, a level-up.
  function rewardLines(card, play, was) {
    if (!was || play.points === null) { return []; }
    var plays = loadPlays();
    var out = [];
    var double = card.move && card.move === skillMove();
    out.push(el('p', { class: 'deck-earned' }, [
      el('strong', { text: '+' + play.points + ' points' }),
      double ? ' (double: skill of the week)' : ''
    ]));
    if (play.medal) {
      out.push(el('p', { class: 'deck-medal-won', text: medalText(play.medal) + ' medal' }));
    }
    if (was.next && !was.nextOpen && isOpen(was.next, plays)) {
      out.push(el('p', { class: 'deck-unlock' }, [
        'Gold! You opened ', el('strong', { text: was.next.name }), '.'
      ]));
    }
    var level = levelFor(totalPoints(plays));
    if (level.index > was.level) {
      out.push(el('p', { class: 'deck-levelup', text: 'Level up! You are now ' + level.name + '.' }));
    }
    return out;
  }

  function summary(stage, card, before, score, weak, play, was) {
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
    lines = lines.concat(rewardLines(card, play, was));
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
  // --- what the server knows -----------------------------------------------
  function loadServer() {
    var s = null;
    try { s = JSON.parse(getItem(SERVER_KEY) || 'null'); } catch (e) { s = null; }
    s = s || {};
    return {
      earned: Array.isArray(s.earned) ? s.earned : [],
      unseen: Array.isArray(s.unseen) ? s.unseen : [],
      goal_weeks: s.goal_weeks || null
    };
  }

  // Badges are only ever added here. `fresh` are ones just awarded, to be
  // celebrated on the next screen he sees.
  function noteServer(earned, fresh, goalWeeks) {
    var s = loadServer();
    (earned || []).concat(fresh || []).forEach(function (code) {
      if (s.earned.indexOf(code) < 0) { s.earned.push(code); }
    });
    (fresh || []).forEach(function (code) {
      if (s.unseen.indexOf(code) < 0) { s.unseen.push(code); }
    });
    // Says whether the weeks figure moved, so the hand can be redrawn.
    var moved = !!goalWeeks && JSON.stringify(goalWeeks) !== JSON.stringify(s.goal_weeks);
    if (goalWeeks) { s.goal_weeks = goalWeeks; }
    setItem(SERVER_KEY, JSON.stringify(s));
    return moved;
  }

  function badgeByCode(code) {
    for (var i = 0; i < BADGES.length; i++) { if (BADGES[i].code === code) { return BADGES[i]; } }
    return null;
  }

  function applyAnswer(body) {
    if (body) {
      noteServer([], body.badges, body.goal_weeks);
      // A badge just landed: show it now if he is not mid-card; if he is,
      // the next screen he goes to shows it.
      if (body.badges && body.badges.length) { setTimeout(refreshList, 0); }
    }
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
        // Badges he already has are not news: they go in earned, not unseen.
        if (noteServer(body.earned, [], body.goal_weeks)) { changed = true; }
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
              // A copy that lost its stamp - restored once by an old cached
              // page - gets it back from the server. Nulls only: a stamp is
              // written once, so filling a gap can never take anything back.
              ['points', 'medal', 'bests'].forEach(function (field) {
                if (local[field] === null && s[field] !== null && s[field] !== undefined) {
                  local[field] = s[field];
                  changed = true;
                }
              });
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
    } else if (hash === 'album' && RULES) {
      renderAlbum(keepScroll);
    } else if ((hash === 'progress' || hash === 'badges') && RULES) {
      renderProgress(keepScroll);
    } else if (hash === 'test' && RULES && RULES.test_cards) {
      renderTest(keepScroll);
    } else {
      renderHand(keepScroll);
    }
    lightTab(hash === 'progress' || hash === 'badges' ? 'progress' : 'cards');
  }

  // Both tabs are this one page, so the server cannot say which is lit, or
  // what the top bar should call it.
  function lightTab(name) {
    var title = document.querySelector('.topbar-title');
    if (title) { title.textContent = name === 'progress' ? 'Progress' : 'Cards'; }
    var tabs = document.querySelectorAll('.tabbar [data-tab]');
    for (var i = 0; i < tabs.length; i++) {
      var on = tabs[i].getAttribute('data-tab') === name;
      tabs[i].classList.toggle('is-on', on);
      if (on) { tabs[i].setAttribute('aria-current', 'page'); } else { tabs[i].removeAttribute('aria-current'); }
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
