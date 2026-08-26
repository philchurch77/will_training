/* The drill screen: the rep counter and the "how did that feel?" buttons.
   Vanilla, no dependencies, no build step.

   There is deliberately no countdown here any more. A clock ticking down on
   the one drill he was enjoying is what made him stop doing it, so the timing
   moved up to the session as a whole - see session.js. What is left is a
   counter for the drills with a number to beat, which is the opposite thing:
   a reason to keep going rather than a reason to stop. */
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
  if (!count) { return; }

  var repsField = document.getElementById('actual_reps');
  var note = document.getElementById('countnote');
  var value = 0;
  var target = parseInt(count.dataset.target, 10) || 0;

  function render() {
    count.textContent = String(value);
    repsField.value = String(value);
    var beaten = target && value >= target;
    count.classList.toggle('is-beaten', !!beaten);
    if (note) {
      note.textContent = beaten
        ? 'Target beaten. Keep going and see how far you get.'
        : 'Tap the plus every time you get one.';
    }
  }

  function bump(by) {
    value = Math.max(0, value + by);
    render();
    if (navigator.vibrate) { navigator.vibrate(8); }
  }

  document.getElementById('plus').addEventListener('click', function () { bump(1); });
  document.getElementById('minus').addEventListener('click', function () { bump(-1); });
  render();
})();
