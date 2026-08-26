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
uv run pytest                    # 204 tests, ~77s
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
                      SessionLog, SessionClock, Badge, EarnedBadge
training/progress.py  streaks, stats, badge awarding — pure functions
training/throttle.py  login rate limiting, cache-backed
training/views.py     every screen, function-based
training/management/commands/seed_drills.py   the drills and the weekly plan
```

Function-based views on purpose: one maintainer, re-read in a year.

### Things that will bite you

- **`Drill` is minutes XOR reps**, enforced by a `CheckConstraint` and by
  `clean()`. Creating one with both or neither raises `IntegrityError`.
- **The session is timed, never the drill.** One clock on Today counts *up*
  for the whole session (`static/training/js/session.js`, state in
  `localStorage` so it survives navigating into a drill and back). Per-drill
  countdowns were removed on purpose: a clock running down on the drill he was
  enjoying is what made him stop. Do not put one back.
- **A by-hand figure is the only thing that may lower the clock.**
  `record_session_seconds(..., exact=True)`, reached by posting `minutes`
  rather than `seconds` to `session_time`. Everything else takes the larger
  value so a tick queued offline cannot rewind a session that has run on. The
  entry point is a minus/plus stepper in fives on Today - no typing on his
  screens - and `session.js` writes the number into `localStorage` before the
  form posts, or the stale local value puts the old number straight back.
- **`SessionClock` is the source of truth for minutes, when it exists.**
  `progress._minutes_per_log()` is the only place that knows the rule: a day he
  clocked is worth what the clock says, shared across the drills he ticked; a
  day he did not is worth the sum of the drills' planned lengths, which is what
  every day before the clock existed still computes. Never make the clock
  authoritative for days without one - that would silently rewrite his history.
  Clock seconds only ever move up, and a day with no ticks is worth nothing.
- **Every session carries exactly one juggling block**, flagged by
  `Drill.is_juggling` and asserted in `test_seed.py`. Keepy-ups are the thing
  he will do for the fun of it and they are pure touch work.
- **`SessionLog` is unique on `(athlete, date, drill)`.** This is what makes
  completion idempotent, which is what lets a tick queued offline be replayed
  safely. Do not relax it without replacing the offline queue.
- **Ticks happen from the Today list, not just the drill page.** Each undone
  row is a form posting to `drill_complete`; the drill page is for reading the
  instructions. Every one of those forms carries `session_seconds`, so the
  clock is banked even if he never taps Finish. Done rows show a plain tick and
  no button - unticking is on the drill page, where it cannot happen by
  accident in his pocket.
- **Rest days and optional days never break a streak.** `progress.day_state()`
  returns `rest` for them and the streak walk skips over them. Today not being
  done yet also does not break the streak. Preseason there are no optional days
  in the seeded plan, but the machinery stays — it is how Fri/Sat go back to
  bonus days when the season restarts.
- **A streak and a perfect week are different bars.** One drill keeps a streak
  alive; the `perfect-week` badge needs every drill of every required day for a
  whole Mon-Sun week. Both read the plan as it stands *today*, not as it stood
  back then - there is no plan history and rebuilding one is not worth it.
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

`seed_drills.py` is the most important file. It holds 45 drills and the weekly
plan, and the coaching brief is encoded as **assertions in
`training/tests/test_seed.py`**. Those tests fail if someone:

- adds a drill needing a partner, a goalkeeper or a teammate;
- adds strength work, weights, plyometrics or endurance running;
- writes a drill longer than five minutes;
- lets a session drift off six drills, or off the flat 30 minutes a day the
  preseason plan is balanced to;
- drops the weak-foot work or the fun finisher from a day;
- puts speed on more or fewer than three days, doubles it up in one session, or
  lets it take the warm-up slot;
- breaks the warm-up-first shape, or the 36–50 drill count.

When editing drills, keep the principles:

- **Ball mastery and first touch are the priority.** Technique over fitness.
- **Speed work is football speed, not athletics.** Mostly with the ball — a
  first touch and a burst after it, a dribble at full pelt — with a couple of
  plain short sprints. Every one says when to stop and get his breath back.
  `TestSpeedWork` enforces the ball-majority, the length and the recovery.
- Every drill doable **alone** in a garden with a ball, a wall and a few cones.
- **Both feet explicitly**, with weak-foot work in every session.
- Instructions are **two or three short sentences written for Will to read
  himself** — second person, present tense, no jargon. Not notes for Phil to
  interpret.
- One coaching cue each ("head up", "laces, not toes").

### The weekly plan

**Currently preseason: seven full sessions of exactly 30 minutes.** No academy
and no matches over the summer, so Friday and Saturday are ordinary training
days and every day counts towards the streak. 210 minutes a week. Phil chose
this knowingly after being told it is a high load; do not quietly reduce it.

**Every drill is five minutes, so a day is six of them:** a ball-mastery
warm-up, four technical drills, a fun finisher - and one of those six is
always juggling. Five minutes is now a planning figure rather than something he
is held to: the session clock is what he actually runs against. Rep-based drills count as five
minutes too (`Drill.estimated_minutes`), so the sum is 30 whatever mix a day is
built from and rebalancing means swapping a drill, not doing arithmetic. That
is the whole reason for the five-minute cap — keep it.

**Speed is on weekdays 1, 3 and 5 only, one block per session.** Sprinting is
the one thing here that tires him rather than teaches him. It never goes in the
warm-up slot either: cold sprinting is how something gets pulled.

**In season**, academy and matches are Friday and Saturday: set `is_optional`
on weekdays 4 and 5 and cut their targets back, so those two carry no required
work and skipping them never breaks the streak.

## Design rules

Built for a 9-year-old on a phone, outdoors:

- Large tap targets (64px minimum), high contrast, minimal text.
- **No dropdowns and no typing anywhere except the PIN pad** on Will's screens.
- **Nothing counts down at him, and no drill shows a length.** The one clock in
  the app counts up and he decides when it stops. `Drill.target_label` is for
  the rep drills and the coach screens only - `TestDrillAndLibrary` guards it
  on Today, All drills and the drill page. The minutes stay in the data because
  the plan is balanced on them.
  Coach screens may use ordinary form controls.
- Palette is white, grey and blue. Contrast ratios were measured, not eyeballed:
  body text ≥5:1, accent `#1667c9` at 5.5:1 on white. Keep it that way — he
  reads this in bright sun.
- Skill colours are validated for colour-blind separation, and **nothing is
  identified by colour alone** — every coloured dot sits beside a written label.
- The Progress chart is one measure across seven named categories, so it uses
  **one colour, not seven**. Do not rainbow it.
- **Anything that scrolls sideways must be a shortcut, never the only door.**
  The drill filter strip on All drills scrolls horizontally, which a nine-year-old
  will not go hunting for; it is only allowed because that list is also grouped
  under skill headings, so every skill is reachable by scrolling down. Do not
  remove the headings and keep the strip.
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

`session.js` and `drill.js` are both precached (see `_precache_urls`).

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
- **There is no in-app install button, on purpose.** Adding to the home screen
  is a once-ever job for Phil, done from Safari's Share sheet or Chrome's menu,
  so it does not earn space in Will's top bar. The `beforeinstallprompt`
  handler and its chip were removed; do not put them back.

## Deployment

Render, via `render.yaml` + `build.sh`. SQLite lives on a **persistent disk** at
`/var/data`; without it Render wipes the database on every deploy and Will loses
his streak. The disk is mounted only at runtime, so `migrate` and
`seed_drills` run from `startCommand`, not `build.sh` - during the build
`/var/data` does not exist and sqlite fails with "unable to open database
file". Regenerate `requirements.txt` from the lock after changing deps:

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
