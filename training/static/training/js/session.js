/* The session clock.

   One clock for the whole session, counting up, instead of a countdown on
   every drill. He starts it, works through the six drills at whatever pace he
   likes - staying on the ones he is enjoying - and stops it at the end.

   The running state lives in localStorage, not on the server, because this is
   a multi-page app: he taps into a drill and back out again constantly, and a
   clock that reset on every navigation would be useless. Only a start
   timestamp is stored, so the elapsed time survives a reload, a locked screen
   and a service worker update without any of them having to be handled.

   The server hears about the clock in two ways: every drill tick carries the
   current seconds with it, and Finish posts them on their own. Both take the
   larger value, so nothing that arrives late can rewind a session. */
(function () {
  'use strict';

  var KEY = 'will-training-clock';
  var MAX = 3 * 60 * 60;  // a garden session is not longer than this

  var chip = document.getElementById('clockchip');
  var card = document.getElementById('session');
  if (!chip && !card) { return; }

  // Today's date comes from Django, so the clock rolls over on the same
  // boundary the streak does rather than on the phone's idea of midnight.
  var today = (card || chip).dataset.today;

  function read() {
    var state;
    try {
      state = JSON.parse(localStorage.getItem(KEY) || 'null');
    } catch (e) {
      state = null;
    }
    // Yesterday's clock is not today's session. This is also what stops a
    // clock left running overnight reporting a nine hour training session.
    if (!state || state.date !== today) {
      state = { date: today, accumulated: 0, startedAt: null };
    }
    // The server may know about more time than this phone does - a tick sent
    // from somewhere else, or localStorage cleared mid-session.
    if (card) {
      var banked = parseInt(card.dataset.seconds, 10) || 0;
      if (banked > state.accumulated) { state.accumulated = banked; }
    }
    return state;
  }

  function write(state) {
    try {
      localStorage.setItem(KEY, JSON.stringify(state));
    } catch (e) { /* storage blocked - the clock still runs this session */ }
  }

  var state = read();

  function elapsed() {
    var extra = state.startedAt ? (Date.now() - state.startedAt) / 1000 : 0;
    return Math.min(MAX, Math.round(state.accumulated + extra));
  }

  function fmt(seconds) {
    var m = Math.floor(seconds / 60);
    var s = seconds % 60;
    return m + ':' + (s < 10 ? '0' : '') + s;
  }

  // --- painting ----------------------------------------------------------
  var clockEl = document.getElementById('clock');
  var startBtn = document.getElementById('clockstart');
  var finishBtn = document.getElementById('clockfinish');
  var noteEl = document.getElementById('clocknote');

  function paint() {
    var seconds = elapsed();

    if (clockEl) { clockEl.textContent = fmt(seconds); }
    if (card) { card.classList.toggle('is-running', !!state.startedAt); }
    if (startBtn) {
      startBtn.textContent = state.startedAt ? 'Pause' : (seconds ? 'Carry on' : 'Start session');
    }
    if (finishBtn) { finishBtn.hidden = !seconds; }
    if (noteEl) {
      noteEl.textContent = state.startedAt
        ? 'Take as long as you like on the ones you enjoy.'
        : (seconds ? 'Paused. Tap carry on when you are ready.'
                   : 'Start the clock, then work down your list.');
    }

    // The chip in the top bar is the only clock he can see from inside a
    // drill, so it appears the moment one is running and not before.
    if (chip) {
      chip.hidden = !state.startedAt && !seconds;
      chip.textContent = fmt(seconds);
      chip.classList.toggle('is-paused', !state.startedAt);
    }

    // Every form that posts to the server carries the clock with it.
    var fields = document.querySelectorAll('.js-clock-seconds');
    for (var i = 0; i < fields.length; i += 1) {
      fields[i].value = String(seconds);
    }

    // A forgotten clock stops itself rather than banking three hours.
    if (state.startedAt && seconds >= MAX) { pause(); }
  }

  // --- screen wake lock --------------------------------------------------
  // He puts the phone on the grass and does the drill. Progressive
  // enhancement: where it is unsupported the clock simply carries on.
  var wakeLock = null;
  function holdScreen() {
    if (!('wakeLock' in navigator)) { return; }
    navigator.wakeLock.request('screen').then(function (lock) {
      wakeLock = lock;
    }).catch(function () { /* denied - not important */ });
  }
  function releaseScreen() {
    if (wakeLock) { wakeLock.release().catch(function () {}); wakeLock = null; }
  }

  // --- running -----------------------------------------------------------
  var ticker = null;

  function run() {
    if (ticker) { return; }
    ticker = setInterval(paint, 1000);
  }

  function start() {
    state.startedAt = Date.now();
    write(state);
    run();
    holdScreen();
    paint();
  }

  function pause() {
    state.accumulated = elapsed();
    state.startedAt = null;
    write(state);
    clearInterval(ticker);
    ticker = null;
    releaseScreen();
    paint();
    save();
  }

  // Best effort only: localStorage is the truth until a tick or Finish posts
  // it properly, so a failure here costs nothing and needs no queueing.
  function save() {
    var form = document.getElementById('clockform');
    if (!form || !navigator.onLine) { return; }
    var body = new FormData(form);
    body.set('seconds', String(elapsed()));
    fetch(form.getAttribute('action'), {
      method: 'POST',
      body: body,
      credentials: 'same-origin',
      headers: { 'X-Requested-With': 'XMLHttpRequest' }
    }).catch(function () { /* it will ride along with the next tick */ });
  }

  if (startBtn) {
    startBtn.addEventListener('click', function () {
      if (state.startedAt) { pause(); } else { start(); }
      if (navigator.vibrate) { navigator.vibrate(10); }
    });
  }

  if (finishBtn) {
    finishBtn.addEventListener('click', function () {
      if (state.startedAt) {
        state.accumulated = elapsed();
        state.startedAt = null;
        write(state);
        clearInterval(ticker);
        ticker = null;
        releaseScreen();
      }
      paint();
      // requestSubmit, not submit: submit() skips the submit event, and that
      // event is where the offline queue lives.
      var form = document.getElementById('clockform');
      if (form) {
        if (form.requestSubmit) { form.requestSubmit(); } else { form.submit(); }
      }
    });
  }

  // Re-acquire the lock and catch the display up after a spell in the
  // background, where timers are throttled or stopped altogether.
  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState !== 'visible') { return; }
    paint();
    if (state.startedAt) { holdScreen(); }
  });

  if (state.startedAt) { run(); holdScreen(); }
  paint();
})();
