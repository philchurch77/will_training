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

  // Seconds the clock has been running since it was last started. Zero when
  // it is paused, which is what makes `accumulated` the whole story then.
  function running(s) {
    return s.startedAt ? (Date.now() - s.startedAt) / 1000 : 0;
  }

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
    //
    // Compare against the running total, not the paused one. While the clock
    // is running `accumulated` is stale by the whole running portion, so the
    // seconds this phone itself posted a moment ago would always look like
    // news from elsewhere. And rebase the start timestamp when adopting: the
    // banked figure already contains the running portion, so leaving
    // `startedAt` where it was makes elapsed() count those minutes twice.
    // That is what made the clock jump on every tick - a tick banks the
    // elapsed time and reloads Today, and the jump was the whole session so
    // far, again.
    if (card) {
      var banked = parseInt(card.dataset.seconds, 10) || 0;
      var local = state.accumulated + running(state);
      if (banked > local) {
        state.accumulated = banked;
        if (state.startedAt) { state.startedAt = Date.now(); }
      }
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
    return Math.min(MAX, Math.round(state.accumulated + running(state)));
  }

  function fmt(seconds) {
    var m = Math.floor(seconds / 60);
    var s = seconds % 60;
    return m + ':' + (s < 10 ? '0' : '') + s;
  }

  // --- painting ----------------------------------------------------------
  var openBtn = null;
  var byhandForm = null;
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

    // No offering to set it by hand while it is visibly running.
    if (openBtn && byhandForm && byhandForm.hidden) {
      openBtn.hidden = !!state.startedAt;
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

  // --- setting it by hand ------------------------------------------------
  // He trained and forgot to start the clock. No typing: the same minus/plus
  // stepper he uses to count keepy-ups, in fives, starting on the length the
  // day is planned at so the usual answer is nought taps away.
  openBtn = document.getElementById('byhandopen');
  byhandForm = document.getElementById('byhandform');

  if (openBtn && byhandForm) {
    var valEl = document.getElementById('byhandval');
    var minutesField = document.getElementById('byhandminutes');
    var saveBtn = document.getElementById('byhandsave');
    var minutes = parseInt(valEl.dataset.start, 10) || 30;

    function paintByhand() {
      valEl.textContent = String(minutes);
      minutesField.value = String(minutes);
      saveBtn.textContent = 'Save ' + minutes + ' minutes';
    }

    function bumpByhand(by) {
      minutes = Math.max(5, Math.min(180, minutes + by));
      paintByhand();
      if (navigator.vibrate) { navigator.vibrate(8); }
    }

    document.getElementById('byhandplus').addEventListener('click', function () {
      bumpByhand(5);
    });
    document.getElementById('byhandminus').addEventListener('click', function () {
      bumpByhand(-5);
    });

    openBtn.addEventListener('click', function () {
      // Start from whatever is on the clock if anything is, so this doubles as
      // a way to correct a number that is wrong rather than missing.
      var onClock = Math.round(elapsed() / 60);
      minutes = Math.max(5, Math.round((onClock || minutes) / 5) * 5);
      paintByhand();
      byhandForm.hidden = false;
      openBtn.hidden = true;
    });

    document.getElementById('byhandcancel').addEventListener('click', function () {
      byhandForm.hidden = true;
      openBtn.hidden = false;
    });

    // What he says happened is what happened. Write it to the phone's own
    // clock before the form goes, or the stale local value would win the next
    // time this page loads and quietly put the old number back.
    byhandForm.addEventListener('submit', function () {
      state.accumulated = minutes * 60;
      state.startedAt = null;
      write(state);
      clearInterval(ticker);
      ticker = null;
      releaseScreen();
    });

    paintByhand();
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
