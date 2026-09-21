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
uv run manage.py seed_drills --reset   # rebuild from scratch; DEBUG only, see below
uv run manage.py set_pin will 4321
uv run manage.py make_icons        # redraw the PWA icons (only if the icon changes)
uv run pytest                    # 261 tests, ~3 min
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
- **Adopting the server's banked seconds must rebase `startedAt`.** `read()` in
  `session.js` takes the server's figure when it beats the phone's, for a
  cleared `localStorage` or a tick from another device. Two rules, and getting
  either wrong double-counts the session: compare the banked value against
  `accumulated + running(state)`, never against `accumulated` alone, which is
  stale by the whole running portion while the clock runs; and when adopting,
  set `startedAt = Date.now()`, because the banked figure *already contains*
  the time since the start. This was broken from the day the clock landed - a
  tick banks the elapsed time and reloads Today, so every tick added the whole
  session again and a real 30 minutes banked as 105. `TestSessionClockScript`
  in `test_views.py` guards it by reading the source, because the bug happens
  in the browser before the POST and no server-side test can see it.
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
- **A day holds two sessions and alternates between them.** `PlanDrill.week`
  is `WEEK_A`, `WEEK_B` or `EVERY_WEEK`, and `progress.week_of(date)` says
  which half of the fortnight a date is in - Monday-aligned and continuous, so
  a Mon-Sun week is never split and a 53-week year never repeats a session.
  Anything reading a day's drills must go through `session_for()` or
  `PlanDay.drills_for_week()`; `day.items` is both weeks at once and is only
  right on the coach screens, which show one week at a time via `?week=`.
- **`test_seed.py` asserts every rule against all twelve sessions**, not six -
  see the `sessions()` helper. A rule checked against `day.items` would be
  checking both weeks jammed together and would miss a week B that had drifted.
- **The fortnight uses every active drill**, and a test says so. That is the
  whole reason the second week exists: one week can only reach 36 of them.
  Currently 58 active of 66 rows - a drill added to the library must be given a
  slot in the plan, or retired.
- **Two things that can delete his history are held shut, deliberately.**
  `seed_drills --reset` raises `CommandError` unless `DEBUG` is on, and
  `SkillAdmin`/`DrillAdmin` refuse delete permission via `NoDeleteMixin`. Both
  guard the same cascade: `Drill.skill` and `SessionLog.drill` are `CASCADE`, so
  removing one skill in the admin, or one careless `--reset` in a Render shell,
  takes every session he has ever logged. `test_seed.py` and `test_admin.py`
  both fail if either guard is removed. Note `--reset` on SQLite is also how
  `migrate` rebuilds a table: an `AddField` emits `CREATE new / INSERT SELECT /
  DROP TABLE / RENAME`, which is safe only because Django wraps it in
  `PRAGMA foreign_keys = OFF`. Back the disk up before migrating anyway.
- **A deploy rebuilds the plan and discards coach edits.** `_seed_plan` does
  `day.items.all().delete()` and rebuilds from `PLAN_DAYS` on every run, and
  `seed_drills` runs on every Render start. Changing a day's running order on
  Coach -> the plan screen is for trying something out; to keep it, put it in
  `seed_drills.py`. The screen says so.
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
- **A tick must never wipe a count.** `drill_complete` writes only the fields
  the request actually carried: the tick on the Today list posts no count and
  no rating, and it would otherwise blank the 30 he counted on the drill page
  ten minutes earlier - which is what his record is made of. A rep drill still
  gets its `actual_minutes` cleared and vice versa; that part is deliberate.
- **Counts are editable on Coach -> His sessions.** `coach_log_edit` changes
  the number or blanks it, and never deletes the row: saying he did not do the
  drill would move his streak and his badges. Per-drill *minutes* are not
  editable - nothing writes them any more, and old rows still feed his
  lifetime minutes through the `_minutes_per_log` fallback.
- **His own score is the thing to beat.** `progress.personal_best()` reads the
  best `actual_reps` for a drill; `drill_complete` reads it *before* the tick
  overwrites today's row, and counts anything already logged today, or ticking
  the same number twice claims a second record. Rep targets are what the drill
  ships with; the record is what he actually did, and it wins.
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
- **A drill is retired, never deleted and never rewritten.** `SessionLog.drill`
  is `CASCADE`, so deleting a drill takes every session he logged against it
  with it - which is what `seed_drills --reset` does, and why that flag must
  never reach Render. Rewriting a slug's content in place loses no rows but is
  worse in its own way: his June logs would silently start claiming he did a
  three-move combination. So the tuple stays in `DRILLS`, the slug goes in
  `RETIRED`, and `is_active=False` takes it out of his library, the plan and
  the precache while leaving the row - and his history - alone. `RETIRED` is an
  explicit list on purpose: drills can be added by hand on the coach screens,
  and "deactivate anything not in `DRILLS`" would switch those off on the next
  deploy. One caveat for the next retirement: `progress.best_scores()` iterates
  `Drill.objects.active()`, so retiring a *rep* drill takes its personal best
  off the Progress board even though every row survives. Both drills retired so
  far are minutes-based, where `personal_best()` returns `None` anyway, so
  nothing is affected yet.
- **Test fixtures use `test-` prefixed slugs** so they compose with the
  `seeded` fixture, which creates the real drills.

## The seed data is the product

`seed_drills.py` is the most important file. It holds 66 drills and the weekly
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
- breaks the warm-up-first shape, or the 36–80 drill count (rows, including
  retired ones - the bound counts rows, retirement never deletes one, so it
  ratchets up and raising it after a batch retires is expected);
- lets a single move on repeat back into the warm-up slot, grades a warm-up
  easy, or repeats a warm-up inside a fortnight.

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

**Currently preseason: six sessions of exactly 30 minutes, Sunday off.** No
academy and no matches over the summer, so Friday and Saturday are ordinary
training days. 180 minutes a week. Sunday is a real rest day, added
deliberately: seven days out of seven left him nowhere to recover, and the
streak - which breaks on a missed required day - was pushing him to train
anyway. Do not quietly put the seventh session back, and do not cut the other
six either.

**Every drill is five minutes, so a day is six of them:** a ball-mastery
warm-up, four technical drills, a fun finisher - and one of those six is
always juggling. **All twelve warm-ups are combination work** - a sequence of
moves joined into one flow, step over into Cruyff, body feint into Cruyff -
because a single move on repeat is autopilot by nine on an elite squad, and
the first block is where close control is actually built. Four openers used to
stay single moves, on the argument that the parts of a combination are worth
five minutes of their own; he is a confident dribbler now and that argument
ran out, so `toe-taps`, `sole-rolls`, `foundations` and `rollovers` are
retired and the parts survive inside the pairs. Twelve sessions, twelve
different openings: the warm-up is the one slot he meets every single day, so
it is the one that goes stale first. `Drill.is_combination` flags it, fed by
the `COMBINATIONS` slug set. `test_seed.py` asserts all twelve chain moves and
that none is graded easy - `is_combination` says the moves are joined up, not
that they are hard, so the difficulty bar is a separate assertion.

A move is described the same way wherever it appears - a chop is always cut
back with the inside of the foot, a step over is always stepped with one foot
and pushed away with the outside of the other, matching the `step-over` drill
in Dribbling - and every move a combination names is described in that drill,
because he is alone in a garden and cannot look one up. Two pairs that look
alike are told apart out loud, and this is the part a future change will get
wrong. **There is one chop and it is the existing one**: cut back with the
inside of the foot, in front of him. A "Ronaldo chop" is deliberately *not*
added under that name - the behind-the-standing-leg inside cut is already in
the library as the Cruyff turn, and two moves under one word is exactly what
this rule exists to stop. The Cruyff and the L-turn (`drag-back-l-turn`) both
cut behind the standing leg with the inside of the foot; the Cruyff spins him
away, the L-turn brings him out facing square. Because the touch is the same,
the L-turn drill says "do not spin all the way round" out loud **and** the two
are kept in different sessions - they were in the same one, one slot apart,
and it read as two contradictory instructions for the same move. A **scissor**
circles the ball and pushes away with the *same* foot, a **step over** pushes
away with the *other* one, and the `scissors` drill says so in as many words.

One more trap, learned the hard way: `is_combination` is a hand-kept set, so a
single move dropped into a warm-up slot passes every test while claiming to be
a chain. `double-scissor-push` is two circles and an exit precisely because one
circle and an exit is already the `scissors` drill. Count the touches before
adding a warm-up.

Every day has two such sessions, week A and week B, with the
same shape and the same skills so the balance holds whichever week it is. Five minutes is now a planning figure rather than something he
is held to: the session clock is what he actually runs against. Rep-based drills count as five
minutes too (`Drill.estimated_minutes`), so the sum is 30 whatever mix a day is
built from and rebalancing means swapping a drill, not doing arithmetic. That
is the whole reason for the five-minute cap — keep it.

**Speed is on weekdays 1, 3 and 5 only, one block per session.** Sprinting is
the one thing here that tires him rather than teaches him. It never goes in the
warm-up slot either: cold sprinting is how something gets pulled.

**Every session carries at least one shooting or dribbling drill.** They are
the two things he loves and will do for the fun of it, and a session with
neither is a session he has to be talked into. Four days already had one;
Monday and Thursday carry the rule deliberately in slot 5, dribbling in week A
and shooting in week B. Swapping that slot out means swapping another of the
two in. Both skills must stay on at least five of the twelve sessions, so the
rule cannot be satisfied by turning the whole fortnight into shooting -
`test_seed.py` asserts the rule and the balance. One of each *per session* was
considered and rejected: it claims 24 of the 72 slots for 11 distinct drills,
which strands a drill and breaks the fortnight-uses-every-active-drill rule.

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

**Back the disk up before any deploy that carries a migration.** The file at
`/var/data/db.sqlite3` is the only copy of his history. From the Render shell,
before triggering the deploy:

```bash
python -c "import sqlite3,datetime; s=sqlite3.connect('/var/data/db.sqlite3'); d=sqlite3.connect('/var/data/db-backup-%s.sqlite3'%datetime.date.today().isoformat()); s.backup(d); d.close(); s.close()"
```

That is SQLite's online backup API - safe while gunicorn is serving, no lock
held, and it does not need the `sqlite3` CLI, which is not on the image. Check
it is real rather than a zero-byte file, and write down the row counts for
`training_sessionlog`, `training_sessionclock` and `training_earnedbadge` so
you have something to compare against afterwards. The backup lands on the same
disk, so it survives a bad migration but not a lost disk; pull it off the box
if you want a real one.

Worth knowing: `startCommand` is `migrate && seed_drills && gunicorn`, so a
migration that fails takes the app down rather than serving a half-migrated
database. That is the right failure, but it is a failure - check
`PRAGMA foreign_key_check` comes back clean before deploying a migration that
rebuilds a table.

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
