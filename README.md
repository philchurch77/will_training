# Will's Training

A small football training app for Will (9). He opens it on his phone, sees the
day's session, taps each drill off as he does it, and watches his streak and
badges build up. One profile, one 4-digit code, and no personal data beyond a
first name.

Django 5.2 + SQLite. No CDN, no build step, no JavaScript framework.

---

## Setup

`python` on this machine is the broken Windows Store stub, so use `py -3.13`.

```bash
py -3.13 -m pip install uv     # once
uv venv
uv sync
uv run manage.py migrate
uv run manage.py seed_drills   # 39 drills, the weekly plan, badges, profile
uv run manage.py runserver
```

Open <http://127.0.0.1:8000>. The default code is **1234** — change it before he
uses it (see below).

### Running the tests

```bash
uv run pytest
```

### Getting it on his phone

Find the machine's LAN address (`ipconfig`), then:

```bash
uv run manage.py runserver 0.0.0.0:8000
```

and browse to `http://<that-address>:8000` on the phone. Add it to the home
screen and it opens like an app, full screen.

**Android (Chrome).** A small **Install** chip appears in the top bar the first
time. Tap it. The chip only shows while the phone thinks the app is not
installed, so once it is done Will never sees it again. If you miss it, the
browser menu has **Install app**.

**iPhone (Safari).** Safari ignores all of that, so it has to be the Share
button → **Add to Home Screen**. It must be Safari; Chrome on iOS cannot
install anything.

Either way it lands as **Training** with the blue football icon, opens without
browser chrome, and holds his login for a year. On Android, a long press on the
icon jumps straight to *Today* or *Progress*.

> **Offline caching needs HTTPS.** Browsers only allow a service worker on
> `localhost` or over HTTPS. Over `http://192.168.x.x` the app works perfectly
> but nothing is cached, so it needs signal. If you want it working properly at
> the bottom of the garden, put it behind HTTPS — Tailscale is the least
> painful route, or Caddy with a local certificate. Nothing breaks without it;
> you just lose the offline bit.

Ticks made while offline are stored on the phone and sent when signal returns.
Replaying them is safe: the server keeps one record per drill per day, so a tick
that actually did get through is never double-counted.

---

## Publishing to Render

Everything needed is committed: `render.yaml` (the blueprint), `build.sh` (the
build step) and `requirements.txt`.

**This is not a git repo yet, and Render deploys from one.** First:

```bash
git init
git add -A
git commit -m "Will's training app"
git branch -M main
git remote add origin https://github.com/<you>/will-training.git
git push -u origin main
```

Then in Render: **New → Blueprint**, point it at the repo, apply. It reads
`render.yaml`, builds, and gives you a URL. Open it on Will's phone, tap 1234,
add to home screen.

### Read this before you deploy

**The database must live on the persistent disk.** Render wipes the normal
filesystem on every deploy and restart. `render.yaml` mounts a 1 GB disk at
`/var/data` and points `WILL_DB_PATH` at it — without that, every push would
erase Will's streak, his history and his badges. **Persistent disks are not
available on Render's free plan**, which is why the blueprint asks for
`starter`. Check current Render plans and pricing before applying.

**Free instances also sleep.** After a spell of inactivity a free service spins
down and the next visit waits ~30–60 seconds for a cold start. For a nine-year-old
in the garden that reads as "broken". Another reason for a paid instance.

**Offline finally works.** Render serves over HTTPS, so the service worker
registers — which it cannot do over `http://192.168.x.x` at home. This is the
real reason hosting it is worth doing.

**A 4-digit code on the public internet** is 10,000 guesses, so the app throttles
per IP address: five wrong tries, then a lockout that doubles each time up to an
hour, plus a global cap that catches attempts spread across many addresses. That
turns brute force from "half an hour" into "not worth it". It is proportionate to
what is stored — a first name and some football drills — but if you would rather
Will's data was not on the public internet at all, run it at home behind Tailscale
instead, which also gives you HTTPS and therefore offline.

### Settings

| Variable | What it does |
|---|---|
| `WILL_SECRET_KEY` | **Required in production.** Render generates one for you. |
| `WILL_DEBUG` | `0` in production. The app refuses to start insecurely. |
| `WILL_DB_PATH` | Full path to the SQLite file. Point it at the disk. |
| `WILL_HOSTS` | Comma-separated domains. Only needed for a custom domain — Render's own hostname is picked up automatically. |
| `WILL_TRUSTED_ORIGINS` | Extra CSRF origins, e.g. `https://will.example.com`. |
| `WILL_SSL_REDIRECT` | `0` only if something upstream already handles it. |

With `WILL_DEBUG=0` the app turns on HTTPS redirects, HSTS, secure cookies and
`X-Frame-Options: DENY`, and **refuses to boot** without a real secret key and
host list. That guard is deliberate — it is what stops a half-configured deploy
quietly serving the internet with a known key.

### After changing dependencies

`requirements.txt` is generated, not hand-written:

```bash
uv export --no-dev --no-hashes --no-emit-project -o requirements.txt
```

### Backups

The database is one file. To copy it down from Render, use a shell on the
service and `cat /var/data/db.sqlite3`, or add a small scheduled job. For a
year of a child's training history, an occasional manual copy is plenty.

---

## Changing his code (the PIN)

```bash
uv run manage.py set_pin will 4321
```

Four digits, nothing else. It is stored hashed, the same way Django stores
passwords — there is no way to read one back, only to set a new one. Wrong
guesses are throttled by IP address: five tries, then a lockout that doubles
each time.

Re-running `seed_drills` will **not** reset a code you have changed.

---

## Editing the weekly plan

**From the app** (easiest). There is one profile, so the coach screens sit
behind the same code. They are deliberately **not** in Will's tab bar — reach
them with the small **Coach** link at the top right, or go straight to `/coach/`.

- **Coach → a day** — add or remove drills, reorder them with the arrows, set
  the target minutes, or tick *Rest day* / *Optional*.
- **Coach → All drills** — edit the wording of any drill, or add your own.
- **Coach → His sessions** — everything he has logged, with his self-ratings.

If he ever finds his way in and rearranges things, `seed_drills` puts the
original week back without touching his logged sessions.

**From the code.** The plan lives at the bottom of
`training/management/commands/seed_drills.py` in `PLAN_DAYS`, as a list of
`(weekday, label, target_minutes, is_rest, is_optional, [drill slugs])`. Edit it
and re-run `uv run manage.py seed_drills`. That rebuilds the plan in place
without duplicating anything or touching his logged sessions.

`uv run manage.py seed_drills --reset` wipes the drills and plans and rebuilds
from scratch. It leaves his session history alone.

### The week as it ships (preseason)

| Day | Session | Target |
|-----|---------|--------|
| Mon | Ball mastery + first touch | 25 min |
| Tue | Dribbling + 1v1 | 25 min |
| Wed | Passing + shooting | 25 min |
| Thu | First touch + 1v1 | 25 min |
| Fri | Dribbling + passing | 25 min |
| Sat | Shooting + first touch | 25 min |
| Sun | Weak foot + freestyle | 25 min |

There is no academy and there are no matches over the summer, so all seven days
are full sessions of the same 25 minutes and every one of them counts towards
the streak. Each day is a five-minute ball-mastery warm-up on the floor, two
seven-minute technical drills, then a six-minute fun finisher, and every session
includes explicit weak-foot work.

That is 175 minutes of home training a week, with no light day in it. It is a
lot for a nine-year-old. If he starts looking tired or bored, open Coach, pick a
day and tick **Rest day** — two taps, and his streak is unaffected.

When the season restarts, put Friday and Saturday back to **Optional** in Coach
(or set `is_optional` on weekdays 4 and 5 in `PLAN_DAYS`) and trim their targets:
academy and match days should carry no required work.

### How the streak works

A day counts once he has ticked **any one drill** — one is enough to keep it
alive. Rest days and any day marked optional are skipped over entirely: they
neither extend the streak nor break it. Preseason there are no optional days, so
every day needs a tick. Today not being done yet doesn't break it either, so it
never reads zero first thing in the morning.

---

## The drills

39 drills across six skills: Ball mastery, Dribbling, Passing, Shooting, First
touch and 1v1. Every one of them:

- can be done **alone**, in a garden or a park — a wall stands in for a passing
  partner;
- needs only a ball, a wall, a few cones and a bit of space;
- is written in plain language for **him** to read, not for you to translate;
- has one coaching cue ("head up", "little touches", "laces, not toes").

Weighted towards ball mastery and first touch, because that is what matters at
nine. There is no strength work, no weights, no plyometrics and no distance
running anywhere in the set — and the test suite fails if anyone adds any.

---

## How it is put together

```
config/           settings, urls
training/
  models.py       Skill, Drill, TrainingPlan, PlanDay, PlanDrill,
                  SessionLog, Badge, EarnedBadge
  progress.py     streaks, stats and badge awarding (pure functions)
  views.py        every screen, function-based
  forms.py        the two coach forms
  management/commands/seed_drills.py   <- the drills and the plan live here
  management/commands/set_pin.py
  management/commands/make_icons.py    <- draws the home-screen icons
  templates/training/
  static/training/
  tests/
```

Will is an ordinary Django user; the code is stored in the password field. If
you ever want the raw tables, `uv run manage.py createsuperuser` gets you into
`/admin/` — that account is separate and never appears on Will's login screen.

### The icon

The home-screen icon is not a picture file anybody drew. It is described as
geometry in `make_icons.py` — a circle, a pentagon and five lines — and drawn
from there into the sizes each phone insists on: 192 and 512 for Android, a
full-bleed 512 that Android is allowed to crop to a circle, and a 180 for iOS,
which ignores the manifest and looks only for `apple-touch-icon.png`. The SVG
is written from the same numbers, so it can never drift from the PNGs.

```bash
uv run manage.py make_icons
```

Run that if you change the colour or the shape, and commit the PNGs. It takes
about eight seconds and needs nothing installed — no Pillow, no build step.

### Colours

White, grey and blue. The greys and the blue were picked against measured
contrast ratios rather than by eye, because he will be reading this outdoors:
body text is 5:1 or better on white, and the blue is 5.5:1. The six skill
colours are checked for colour-blind separation, and every one of them sits
next to a written label — nothing in the app is identified by colour alone.
The Progress chart is one measure across six named categories, so it uses a
single colour rather than six; the skill names are on the bars.

The test suite covers the models, the streak rules, session completion and
access to the coach area — and `tests/test_seed.py` asserts the coaching principles
themselves, so if a future edit sneaks in a drill needing a partner, or lets a
session creep past 30 minutes, or drops the weak-foot work from a day, the tests
say so.
