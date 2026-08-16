/* Service worker for Will's Training.

   Rendered by Django so the precache list always matches the drills that
   actually exist. Served from / so its scope covers the whole app.

   Note: browsers only register a service worker over HTTPS or on localhost.
   On a plain-http LAN address the app still works, just without offline. */

// Bump this whenever the CSS, JS or icon change - filenames are not
// content-hashed, and static assets are served cache-first, so an old cache
// would keep serving the previous stylesheet forever.
const CACHE = 'will-training-v6';

// Built by the view as JSON. A {% templatetag openblock %} for {% templatetag closeblock %} loop with escapejs works too, but
// escapejs writes every hyphen as a unicode escape, and a precache list you
// cannot read by eye is a precache list nobody ever checks.
const PRECACHE = {{ precache|safe }};

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE)
      // addAll fails the whole install if any single URL 404s, so add them
      // one at a time and let stragglers be fetched on demand instead.
      .then((cache) => Promise.all(
        PRECACHE.map((url) => cache.add(url).catch(() => null))
      ))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(
        keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))
      ))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const request = event.request;

  // Never cache anything that changes state - ticks must reach the server,
  // and the app's own queue handles them when they cannot.
  if (request.method !== 'GET') { return; }

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) { return; }

  const isStatic = url.pathname.startsWith('/static/');

  // Only ever keep a clean 200 from this origin. A redirect to the login page
  // or a 500 stored here would be replayed offline as if it were the app, and
  // he would open his session to find a login screen he cannot get past.
  const keep = (res) => res.ok && !res.redirected && res.type === 'basic';

  if (isStatic) {
    // Cache-first: these change only when CACHE above is bumped.
    event.respondWith(
      caches.match(request).then((hit) => hit || fetch(request).then((res) => {
        if (keep(res)) {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(request, copy));
        }
        return res;
      }))
    );
    return;
  }

  // Network-first for pages, so he sees today's real state when there is
  // signal, and the last known good copy when there is not.
  event.respondWith(
    fetch(request)
      .then((res) => {
        if (keep(res)) {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(request, copy));
        }
        return res;
      })
      .catch(() => caches.match(request)
        .then((hit) => hit || caches.match('{% url "training:offline" %}')))
  );
});
