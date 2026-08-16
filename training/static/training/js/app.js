/* App shell: service worker registration and the offline completion queue.

   The garden has patchy signal, so a tick must never be lost. If the POST
   fails we stash it in localStorage and replay it when we are back online.
   The server endpoint is idempotent (one SessionLog per drill per day), so
   replaying a tick that actually did land is harmless. */
(function () {
  'use strict';

  var QUEUE_KEY = 'will-training-queue';

  // --- service worker ----------------------------------------------------
  // Only registers over HTTPS or on localhost. Over plain http on a LAN IP
  // the browser refuses, and the app simply runs without offline support.
  if ('serviceWorker' in navigator) {
    window.addEventListener('load', function () {
      navigator.serviceWorker.register('/sw.js').catch(function () {
        /* no offline support here - not fatal */
      });
    });
  }

  // --- skill filter strip ------------------------------------------------
  // The strip scrolls sideways and the lit chip is what tells him which filter
  // he is on. Tapping a chip at the far end loads a page whose strip has
  // scrolled back to the left, hiding the very confirmation he needs, so nudge
  // it back into view. Minimum nudge only, so the leading chips stay put where
  // they can. The 36 clears the fade on the right edge.
  var strip = document.querySelector('.chips');
  if (strip) {
    var lit = strip.querySelector('.chip.is-on');
    if (lit) {
      var overshoot = lit.offsetLeft + lit.offsetWidth - strip.clientWidth + 36;
      if (overshoot > 0) { strip.scrollLeft = overshoot; }
    }
    // 2px of slack: scrollLeft goes fractional on a zoomed phone and an exact
    // comparison then never reports the end.
    var paintMore = function () {
      var more = strip.scrollLeft + strip.clientWidth < strip.scrollWidth - 2;
      strip.classList.toggle('has-more', more);
    };
    strip.addEventListener('scroll', paintMore, { passive: true });
    window.addEventListener('resize', paintMore);
    paintMore();
  }

  // --- connection banner -------------------------------------------------
  function paintConnection() {
    document.body.classList.toggle('is-offline', !navigator.onLine);
  }
  window.addEventListener('online', function () { paintConnection(); flush(); });
  window.addEventListener('offline', paintConnection);
  paintConnection();

  // --- queue -------------------------------------------------------------
  function readQueue() {
    try {
      return JSON.parse(localStorage.getItem(QUEUE_KEY) || '[]');
    } catch (e) {
      return [];
    }
  }

  function writeQueue(items) {
    try {
      localStorage.setItem(QUEUE_KEY, JSON.stringify(items));
    } catch (e) { /* storage full or blocked - nothing useful to do */ }
  }

  function enqueue(entry) {
    var items = readQueue();
    // One entry per drill per day, matching the server's own constraint.
    items = items.filter(function (i) {
      return !(i.url === entry.url && i.body.date === entry.body.date);
    });
    items.push(entry);
    writeQueue(items);
  }

  function post(url, body) {
    var form = new FormData();
    Object.keys(body).forEach(function (k) {
      if (body[k] !== null && body[k] !== undefined && body[k] !== '') {
        form.append(k, body[k]);
      }
    });
    return fetch(url, {
      method: 'POST',
      body: form,
      credentials: 'same-origin',
      headers: { 'X-Requested-With': 'XMLHttpRequest' }
    }).then(function (res) {
      if (!res.ok) { throw new Error('bad status ' + res.status); }
      return res;
    });
  }

  function flush() {
    var items = readQueue();
    if (!items.length) { return Promise.resolve(); }

    // Drain one at a time; anything that still fails goes back in the queue.
    var remaining = [];
    var chain = Promise.resolve();
    items.forEach(function (item) {
      chain = chain.then(function () {
        return post(item.url, item.body).catch(function () {
          remaining.push(item);
        });
      });
    });
    return chain.then(function () { writeQueue(remaining); });
  }

  // Try to drain anything left over from a previous visit.
  if (navigator.onLine) { flush(); }

  // --- intercept the "I've finished this" form ---------------------------
  var form = document.getElementById('doneform');
  if (!form) { return; }

  form.addEventListener('submit', function (event) {
    if (navigator.onLine) { return; }  // online: let the normal POST happen

    event.preventDefault();
    var data = new FormData(form);
    var body = {};
    data.forEach(function (v, k) { body[k] = v; });

    enqueue({ url: form.getAttribute('action'), body: body });

    // Remember it locally so Today can show the tick straight away even
    // though the server has not heard about it yet.
    try {
      var pending = JSON.parse(localStorage.getItem('will-training-pending') || '{}');
      pending[form.dataset.slug] = body.date;
      localStorage.setItem('will-training-pending', JSON.stringify(pending));
    } catch (e) { /* ignore */ }

    window.location.href = '/?done=' + encodeURIComponent(form.dataset.slug);
  });
})();
