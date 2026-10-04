/* App shell: service worker registration and the connection banner.

   The old fixed plan queued ticks here, in localStorage under
   'will-training-queue', and replayed them when signal came back. The plan
   was retired in leg 3d and the tick endpoints with it, so nothing can send
   those any more. The keys are deliberately left on his phone, never read
   and never removed: a tick that somehow never landed survives there as a
   record someone could read by hand, and three small keys cost nothing.
   Plays are deck.js's job. */
(function () {
  'use strict';

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

  // --- connection banner -------------------------------------------------
  function paintConnection() {
    document.body.classList.toggle('is-offline', !navigator.onLine);
  }
  window.addEventListener('online', paintConnection);
  window.addEventListener('offline', paintConnection);
  paintConnection();
})();
