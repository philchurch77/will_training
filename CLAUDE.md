# CLAUDE.md

Guidance for Claude Code when working in this repository.

## What this is

A daily football training app for **Will, aged 9**, who plays for an academy
elite squad. He opens it on his phone, sees the day's session, ticks off drills
as he does them, and watches his streak and badges build. Phil (his dad) is the
only maintainer and the only other user.

The whole point is that it can be **handed over**: Will uses it without help.
That constraint decides most arguments about design and scope.

## Commands

Always use `py -3.13`. The bare `python` on this machine is the broken Windows
Store stub and will fail with a launch error.

```bash
uv sync                          # install
uv run manage.py runserver       # http://127.0.0.1:8000
uv run manage.py migrate
uv run manage.py seed_drills     # drills, plan, badges, Will's profile
uv run manage.py seed_drills --reset   # rebuild drills and plan from scratch
uv run manage.py set_pin will 4321
uv run manage.py make_icons        # redraw the PWA icons (only if the icon changes)
uv run pytest                    # 147 tests, ~50s
uv run pytest training/tests/test_seed.py -q    # just the coaching rules
```

`uv` lives at `C:\Users\philc\AppData\Local\Programs\Python\Python313\Scripts`
and may not be on PATH; add it to `$env:Path` first in a fresh shell.

## Architecture

Django 5.2 + SQLite. One app, `training`. Server-rendered templates and a little
vanilla JS. **No SPA framework and no build step** — this is deliberate, do not
introduce one.

```
config/settings.py    dev defaults; every production knob is an env var
training/models.py    Skill, Drill, TrainingPlan, PlanDay, PlanDrill,
                      SessionLog, Badge, EarnedBadge
training/progress.py  streaks, stats, badge awarding — pure functions
training/throttle.py  login rate limiting, cache-backed
training/views.py     every screen, function-based
training/management/commands/seed_drills.py   the drills and the weekly plan
```

Function-based views on purpose: one maintainer, re-read in a year.

### Things that will bite you

- **`Drill` is minutes XOR reps**, enforced by a `CheckConstraint` and by
  `clean()`. Creating one with both or neither raises `IntegrityError`.
- **`SessionLog` is unique on `(athlete, date, drill)`.** This is what makes
  completion idempotent, which is what lets a tick queued offline be replayed
  safely. Do not relax it without replacing the offline queue.
- **Rest days and optional days never break a streak.** `progress.day_state()`
  returns `rest` for them and the streak walk skips over them. Today not being
  done yet also does not break the streak. Preseason there are no optional days
  in the seeded plan, but the machinery stays — it is how Fri/Sat go back to
  bonus days when the season restarts.
- **Streak functions take the date explicitly.** Never call `date.today()`
  inside `progress.py` — the tests pin dates.
- **One profile only.** `get_athlete()` returns the single non-staff user. The
  coach screens sit behind the same code and are kept off Will's tab bar, not
  behind a second account.
- **`{# #}` template comments are single-line.** Spread one over two lines and
  it is no longer a comment — the text renders onto the page, and the response
  is still a 200 so nothing looks wrong. `TestTemplateComments` guards this.
- **Test fixtures use `test-` prefixed slugs** so they compose with the
  `seeded` fixture, which creates the real drills.

## The seed data is the product

`seed_drills.py` is the most important file. It holds 39 drills and the weekly
plan, and the coaching brief is encoded as **assertions in
`training/tests/test_seed.py`**. Those tests fail if someone:

- adds a drill needing a partner, a goalkeeper or a teammate;
- adds strength work, weights, plyometrics or running drills;
- lets a session drift outside 20–30 minutes or 3–4 drills, or off the flat
  25 minutes a day the preseason plan is balanced to;
- drops the weak-foot work or the fun finisher from a day;
- breaks the warm-up-first shape, or the 30–40 drill count.

When editing drills, keep the principles:

- **Ball mastery and first touch are the priority.** Technique over fitness.
- Every drill doable **alone** in a garden with a ball, a wall and a few cones.
- **Both feet explicitly**, with weak-foot work in every session.
- Instructions are **two or three short sentences written for Will to read
  himself** — second person, present tense, no jargon. Not notes for Phil to
  interpret.
- One coaching cue each ("head up", "laces, not toes").

### The weekly plan

**Currently preseason: seven full sessions of exactly 25 minutes.** No academy
and no matches over the summer, so Friday and Saturday are ordinary training
days and every day counts towards the streak. 175 minutes a week. Phil chose
this knowingly after being told it is a high load; do not quietly reduce it.

25 minutes lands exactly on 5 + 7 + 7 + 6 — a five-minute ball-mastery warm-up,
two seven-minute technical drills, a six-minute fun finisher. Given the drill
durations that is the only four-drill shape that hits 25, so a rebalance means
picking drills at those lengths, not inventing a new shape.

**In season**, academy and matches are Friday and Saturday: set `is_optional`
on weekdays 4 and 5 and cut their targets back, so those two carry no required
work and skipping them never breaks the streak.

## Design rules

Built for a 9-year-old on a phone, outdoors:

- Large tap targets (64px minimum), high contrast, minimal text.
- **No dropdowns and no typing anywhere except the PIN pad** on Will's screens.
  Coach screens may use ordinary form controls.
- Palette is white, grey and blue. Contrast ratios were measured, not eyeballed:
  body text ≥5:1, accent `#1667c9` at 5.5:1 on white. Keep it that way — he
  reads this in bright sun.
- Skill colours are validated for colour-blind separation, and **nothing is
  identified by colour alone** — every coloured dot sits beside a written label.
- The Progress chart is one measure across six named categories, so it uses
  **one colour, not six**. Do not rainbow it.
- Bold and sporty, not cutesy.

## Offline

The service worker is served from `/sw.js` (root scope, rendered by Django so
the precache list matches the real drills). Ticks made offline queue in
`localStorage` and replay when signal returns. The service worker only stores a
clean same-origin 200 — caching the login redirect would strand him on a login
screen he cannot get past with no signal.

Service workers only register over **HTTPS or on localhost**. On a plain-http
LAN address the app works but caches nothing. On Render it is HTTPS, so offline
works there.

Bump `CACHE` in `training/templates/training/sw.js` when static assets change —
filenames are not content-hashed.

## Installing to a home screen

`manifest.json` and `/sw.js` are both Django views, not static files. Things
that matter:

- **The icons are generated, not drawn.** `make_icons.py` holds the geometry
  and rasterises the PNGs (pure Python, no Pillow, no build step) and rewrites
  `icon.svg` from the same numbers. Edit the constants there, rerun it, commit
  the PNGs. Never hand-edit `icon.svg` — the next run overwrites it.
- **`id` and `start_url` are both `/` and must stay that way.** Changing either
  reads as a different app and orphans the icon already on Will's phone.
- **`theme_color` in the manifest must match the `theme-color` meta tag** in
  `base.html`. They differed once, which put a blue bar above the app's white
  top bar in standalone mode.
- **iOS ignores the manifest.** It only reads `apple-touch-icon` and
  `apple-mobile-web-app-title`, so both stay in `base.html`.
- The install chip in the top bar (`#install-go`) is only unhidden for
  `beforeinstallprompt`, which never fires on iOS — there it is the Share
  sheet, and the chip correctly stays hidden. It is deliberately tiny: 26px
  tall, with a `::after` overlay putting the tap target back to 44px.

## Deployment

Render, via `render.yaml` + `build.sh`. SQLite lives on a **persistent disk** at
`/var/data`; without it Render wipes the database on every deploy and Will loses
his streak. Regenerate `requirements.txt` from the lock after changing deps:

```bash
uv export --no-dev --no-hashes --no-emit-project -o requirements.txt
```

Production settings refuse to start without `WILL_SECRET_KEY` and `WILL_HOSTS`
— that guard is intentional, do not soften it. Run **one gunicorn worker**: the
login throttle keeps counters in local memory.

## Before finishing any change

```bash
uv run manage.py check
uv run manage.py makemigrations --check --dry-run
uv run pytest
```

For UI changes, actually look at the app — start the server and drive it, don't
just trust the tests. Cosmetic bugs (wrapped rows, duplicated links) do not show
up in pytest.

If you restart the dev server to check a fix, remember `--noreload` means it
serves the code it started with. A stale server has already produced one false
"not fixed" reading in this project.
