/* Timer, rep counter and the "how did that feel?" buttons.
   Vanilla, no dependencies, no build step. */
(function () {
  'use strict';

  // --- rating ------------------------------------------------------------
  var ratingField = document.getElementById('rating');
  document.querySelectorAll('.rate').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var value = btn.dataset.rate;
      var already = btn.getAttribute('aria-pressed') === 'true';
      document.querySelectorAll('.rate').forEach(function (b) {
        b.setAttribute('aria-pressed', 'false');
      });
      if (already) {
        ratingField.value = '';
      } else {
        btn.setAttribute('aria-pressed', 'true');
        ratingField.value = value;
      }
    });
  });

  // --- rep counter -------------------------------------------------------
  var count = document.getElementById('count');
  if (count) {
    var repsField = document.getElementById('actual_reps');
    var value = 0;
    var target = parseInt(count.dataset.target, 10) || 0;

    var render = function () {
      count.textContent = String(value);
      repsField.value = String(value);
      count.style.color = target && value >= target ? 'var(--accent)' : '';
    };
    var bump = function (by) {
      value = Math.max(0, value + by);
      render();
      if (navigator.vibrate) { navigator.vibrate(8); }
    };

    document.getElementById('plus').addEventListener('click', function () { bump(1); });
    document.getElementById('minus').addEventListener('click', function () { bump(-1); });
    render();
  }

  // --- countdown timer ---------------------------------------------------
  var clock = document.getElementById('clock');
  if (!clock) { return; }

  var minutesField = document.getElementById('actual_minutes');
  var note = document.getElementById('clocknote');
  var startstop = document.getElementById('startstop');
  var resetBtn = document.getElementById('reset');

  var total = (parseInt(clock.dataset.seconds, 10) || 0) * 60;
  var left = total;
  var running = false;
  var started = false;
  var ticker = null;
  var wakeLock = null;

  function fmt(seconds) {
    var sign = seconds < 0 ? '-' : '';
    var s = Math.abs(seconds);
    var m = Math.floor(s / 60);
    var r = s % 60;
    return sign + m + ':' + (r < 10 ? '0' : '') + r;
  }

  function paint() {
    clock.textContent = fmt(left);
    clock.classList.toggle('is-up', left <= 0);
    // Record whole minutes actually trained, so the coach view and the
    // minutes-per-skill chart reflect what he really did. Left blank until he
    // actually starts the clock, so the drill's planned duration is used if he
    // just taps "finished" without timing himself.
    if (!started) { return; }
    var done = Math.max(0, total - left);
    minutesField.value = String(Math.max(1, Math.round(done / 60)));
  }

  // Keep the screen awake mid-drill. Progressive enhancement: if the browser
  // does not support it, the timer still runs.
  function holdScreen() {
    if (!('wakeLock' in navigator)) { return; }
    navigator.wakeLock.request('screen').then(function (lock) {
      wakeLock = lock;
    }).catch(function () { /* denied or unsupported - not important */ });
  }
  function releaseScreen() {
    if (wakeLock) { wakeLock.release().catch(function () {}); wakeLock = null; }
  }

  function tick() {
    left -= 1;
    paint();
    if (left === 0) {
      if (navigator.vibrate) { navigator.vibrate([120, 60, 120]); }
      if (note) { note.textContent = "Time's up - nice work!"; }
    }
  }

  function start() {
    running = true;
    started = true;
    startstop.textContent = 'Pause';
    if (note) { note.textContent = 'Go!'; }
    ticker = setInterval(tick, 1000);
    holdScreen();
  }

  function stop() {
    running = false;
    startstop.textContent = 'Start';
    clearInterval(ticker);
    ticker = null;
    releaseScreen();
  }

  startstop.addEventListener('click', function () {
    if (running) { stop(); } else { start(); }
  });

  resetBtn.addEventListener('click', function () {
    stop();
    left = total;
    started = false;
    minutesField.value = "";
    if (note) { note.textContent = 'Tap start when you are ready'; }
    paint();
  });

  // Re-acquire the lock if he switches away and comes back.
  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'visible' && running) { holdScreen(); }
  });

  paint();
  minutesField.value = '';
})();
