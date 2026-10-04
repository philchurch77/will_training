# CLAUDE.md

Guidance for Claude Code when working in this repository.

## What this is

A football training app for **Will, aged 9**, who plays for an academy elite
squad. He opens it on his phone to a hand of scored challenge cards, plays any
three, and chases medals, levels and his own bests, weak foot first. Phil (his
dad) is the only maintainer and the only other user.

The whole point is that it can be **handed over**: Will uses it without help.
That constraint decides most arguments about design and scope.

It began as a fixed six-drill daily plan. That was replaced by the cards in
legs 1-3 of `docs/chart/deck.md` and retired in leg 3d; what he did on it is
kept, read-only, as **Before the cards**. Read the chart and `CONTEXT.md`
before changing anything about the game.

## Commands

Always use `py -3.13`. The bare `python` on this machine is the broken Windows
Store stub and will fail with a launch error.

```bash
uv sync                          # install
uv run manage.py runserver       # http://127.0.0.1:8000
uv run manage.py migrate
uv run manage.py seed_drills     # skills, drills (inactive), badges, cards, Will's profile
uv run manage.py set_pin will 4321
uv run manage.py make_icons      # redraw the PWA icons (only if the icon changes)
uv run pytest                    # a few minutes
```

`uv` lives at `C:\Users\philc\AppData\Local\Programs\Python\Python313\Scripts`
and may not be on PATH; add it to `$env:Path` first in a fresh shell.

## Architecture

Django 5.2 + SQLite. One app, `training`. One page that draws itself on the
phone, a few server-rendered pages, and vanilla JS. **No SPA framework and no
build step** — this is deliberate, do not introduce one.

```
config/settings.py         dev defaults; every production knob is an env var
training/models.py         Card, Play (the deck); Badge, EarnedBadge; Skill, Drill,
                           SessionLog, SessionClock (his history); the retired
                           TrainingPlan, PlanDay, PlanDrill (rows kept, unread)
training/deck_data.py      the 51 cards and seed_deck(); called by seed_drills
training/deck_rules.py     every game number, history rules, deck badges
training/deck_views.py     / (the deck shell) and /api/plays/ (the backup)
training/views.py          login, Before the cards, the coach screens, PWA plumbing
training/progress.py       his history from before the cards; the award step
training/throttle.py       login rate limiting, cache-backed
static/training/js/deck.js everything he sees and does on /, Progress included
static/training/js/app.js  service worker registration, connection banner
```

Function-based views on purpose: one maintainer, re-read in a year.

## The deck

- **`/` is the deck and must render, never redirect.** The icon opens `/`,
  and the service worker refuses to keep a redirected page, so a redirect
  leaves the icon blank offline. `/deck/`, `/progress/`, `/today/` and
  `/library/` redirect *to* it for old links, and `/coach/logs/` to `/coach/`. His tab bar is **Cards** and
  **Progress**; Progress is `/#progress` (`#badges` is an alias), drawn on the
  phone so it adds up the same plays as the hand, and `route()` lights the
  tab and sets the top-bar title.
- **The deck is drawn on the phone.** `/` is a shell with every active card
  baked in; `deck.js` deals, scores, and keeps every play in localStorage
  (`will-deck-plays-v1`) before sending it to `/api/plays/`. A play's id is
  made on the phone, so a resend changes nothing. No server answer removes a
  play from the phone, and `savePlays` refuses a list that is shorter or
  missing an id. The CSRF token is read from the `csrftoken` cookie at send
  time, because a cached page's token goes stale at the next sign-in. The
  service worker never touches `/api/`. The date is the phone's local date,
  never UTC - `toISOString().slice(0, 10)` puts a play at 00:30 in summer on
  yesterday.
- **Nothing deletes a play.** `Play.card` and `Play.athlete` are `PROTECT`,
  the admin refuses delete and add, and there is no command for it. The
  trial clear-out was deleted in 3d, never run: Render held 0 plays on
  4 Oct 2026, so no trial play ever reached his record. Every play on his
  account is his: never test by saving one on Render.
- **A card is retired, never deleted, and its meaning never changes.** New
  wording or medal targets are fine in place. A change to `scoring`,
  `per_foot`, `timer_seconds` or `out_of` changes what the plays against it
  mean, so it is a new slug with the old one put in `RETIRED` in
  `deck_data.py`. `api_plays` accepts plays on retired cards: the phone has
  no other copy to send.
- **A card's slug, move and level never change.** Unlocks look up the gate
  card by move and level and read its stamped medals by slug, so moving
  either re-locks a level he opened. `FROZEN_MEANINGS` in `test_deck.py`
  holds them.
- **A play is stamped once, on the phone, when he saves it**: `points`,
  `medal`, `bests` on `Play`, never worked out again. Totals, his level and
  which move levels are open are sums and maxes of stamps, so a change to
  points or medal targets never takes back what he earned. Null is an
  unstamped play and is worth nothing. A bad stamp is dropped, never a reason
  to refuse the play: a real score must not be lost over what it was worth.
  `restore()` fills a missing stamp from the server, nulls only.
- **Every game number lives in `deck_rules.py`** and reaches the phone as the
  `deck-rules` block; `deck.js` keeps none of its own beyond the game's shape
  (three medals, three levels per move). **Level thresholds may go down,
  never up** - raising one takes a level off him, and `test_deck_rules.py`
  holds the ceilings. The skill of the week starts on `BLOCKS_START` and is
  None before it, so nothing is stamped double early.
- **Gold on a move level opens the next.** A locked card is never dealt and
  cannot be played; it shows "Locked" and what opens it. The Moves card in his
  hand is always the skill of the week at its highest open level.
- **A deck session is 3 different cards on one day, free play included; a
  goal week is 3 sessions Mon-Sun.** One of only two rules written twice -
  `deck_rules.session_dates` and `weekStatus` in `deck.js`. Change both. The
  current week never breaks a run; weeks in a row is shown only from 1. The
  other is the player level: `deck_rules.player_level` (the coach page) and
  `levelFor` in `deck.js`, both reading `LEVELS`.
- **The hand** is five cards from five packs: always one Moves card and one
  Quick feet or Combos card. It is the same all day until he deals again.
  Free play is a button, not a card in the hand.
- **The stepper starts at 0**, never at his best: one tap would put a number
  he did not reach on his record for good.
- **The phone resends what the server has lost.** `restore()` marks unsent
  any play the server's list no longer holds - a disk restored from backup,
  say - so `sync()` sends it again. The flip side: deleting plays on the
  server does nothing on its own while a phone still holds them.
- **A weak-foot score is on the phone before the strong foot starts**
  (`will-deck-draft-v1`), so a page thrown away mid-card resumes rather than
  losing the go he just counted.
- **`will-deck-server-v1`** caches what only the server knows - every badge
  he has earned (only ever added), the goal-week run to last week, and badges
  not yet celebrated. It is not the plays list, and nothing in it is a record.
- **Scores are read-only in the admin and on the coach page.** The phone's
  copy wins on the phone, so a correction anywhere else would leave his bests
  showing the old number.
- **His cards** (`/coach/`, `coach_cards`) is Dad's read-only view of what has
  backed up: points (stamps plus the head start), level, goal weeks, best per
  card (`deck_rules.card_bests`, one query: on a time card the fastest above 0)
  and his plays, 50 a page. Old ticks are at `/coach/before/`. Read it signed
  in as **staff** (`/admin/login/?next=/coach/`): `/api/plays/` refuses staff,
  so Dad's phone can never put a play on Will's record. Signed in with Will's
  PIN, any opening of `/` syncs that phone's plays onto him for good - so the
  coach screens never lead to the PIN pad: signed out they go to the staff
  sign-in (`COACH_SIGN_IN`), and their Sign out returns there. Staff get no
  tab bar and no link to the deck. An old best on a card he has not played
  yet is listed too, as on his phone.
- **A refused play is logged** (`play refused: '<id>' (<reason>)`, a warning in
  Render's logs) and kept on the phone. No score goes in the log. A stored,
  viewable list is in the chart's fog.

## Badges

- **Every badge is awarded at sync, on the server.** `award_deck_badges`
  runs when a POST to `/api/plays/` saves plays, and awards through
  `progress.award` - the one award step, each award in its own savepoint, so
  two syncs racing to one badge leave one row and no error. A badge going
  wrong is logged, never a 500: it must not cost a play.
- **Deck badges** (`Badge.DECK_KINDS`) come from his plays,
  `deck_rules.deck_badge_values` over every Play row, retired cards included.
  Gold medal and Record breaker trust the phone's stamps; `_parse_stamp`
  holds the checks that stay true whatever the targets become.
- **Kept badges** (`Badge.KEPT_KINDS`: First session, 10/50/100 drills, All
  rounder, Two footed, Keepy-up king) count his old ticks and card plays
  together. `progress.kept_badge_values` is the one place that adds them up.
  One go on a card is a *card-day* (`deck_rules.kept_counts_from_plays`): a
  different card on a day, free play included, never the score. All rounder
  is the larger of skills tried and packs played, never the sum.
- **A badge is retired, never deleted.** `EarnedBadge.badge` is CASCADE, so
  both badge admins refuse delete. `RETIRED_BADGES` in `seed_drills.py` is an
  explicit list (the day streaks, Perfect week, 500 minutes); a retired badge
  is never awarded again, and one he earned shows tagged Legend. Already
  earned stays earned: nothing removes an award.

## His history, before the cards

Nothing writes to it any more. Everything here is about keeping it exactly as
it is and reading it the same way every time.

- **SessionLog, SessionClock and the drills are his record from the fixed
  plan.** Nothing adds or removes a SessionLog: the tick endpoints went in
  3d, and `SessionLogAdmin` refuses add and delete with the date, drill and
  athlete read-only. Each row is worth 5 head-start points and a step toward
  a kept badge, so a row added or removed moves both.
- **Never delete a drill or a skill.** `Drill.skill` and `SessionLog.drill`
  are `CASCADE`: removing one skill takes every drill under it and every
  session he logged against them. `SkillAdmin`/`DrillAdmin` refuse delete via
  `NoDeleteMixin`, and `seed_drills` has no `--reset` any more. Never rewrite
  a drill's text either - his June logs would start claiming he did
  something else. Every drill is seeded with `is_active=False` and kept.
  `JUGGLING` and `COMBINATIONS` stay in `seed_drills.py`: Keepy-up king counts
  `is_juggling` ticks.
- **His head start** is worked out from his SessionLog rows on every deck
  load by `deck_rules.history_for`, and written nowhere: 5 points per drill
  he ticked, capped at 1000, and his old best on the three drills that are
  the same exercise as a card (`HISTORY_CARDS`). Per user - `request.user`,
  never `get_athlete()`. The per-tick figure and the cap may go up, never
  down. No medals come from old scores.
- **Counts are editable on Coach -> Before the cards** (`/coach/before/`). `coach_log_edit` changes
  the number or blanks it, and never deletes the row. A value that is not a
  count changes nothing - never wipes one. A count moves only his
  records on Before the cards and the three "from before" keepy-up bests -
  never points or badges, which count rows, not reps.
- **His best streak is frozen to the plan's last rule**: Monday to Saturday
  required, Sunday rest (`progress.REST_WEEKDAYS`). It used to read the
  active plan, and with no plan every missed day would read as rest - his
  best streak would quietly join every day he ever trained into one run.
- **`SessionClock` decides what a clocked day was worth.**
  `progress._minutes_per_log()` is the only place that knows the rule: a day
  he clocked is worth what the clock says, shared across the drills he
  ticked; a day he did not is worth the sum of the drills' planned lengths.
  Never make the clock authoritative for days without one.
- **`progress.best_scores()` reads every rep drill**, inactive ones included,
  so every record stays on Before the cards.
- **The plan tables are retired, not dropped.** `TrainingPlan`, `PlanDay` and
  `PlanDrill` rows stay as they were; nothing reads or writes them, and their
  admins are gone. Dropping them is a later leg with its own backup.
- **His phone may still hold `will-training-queue`, `-pending` and `-clock`**
  from the old app. `app.js` leaves them alone on purpose: never read, never
  removed.

## Moves are named once

A move is described the same way on every card - a chop is always cut back
with the inside of the foot, a step over is always stepped with one foot and
pushed away with the outside of the other - because he is alone in a garden
and cannot look one up. **There is one chop**: cut back with the inside of the
foot, in front of him; the deck calls it *Chop turn* (an "inside hook" is the
same move). The behind-the-standing-leg inside cut is the **Cruyff turn**, and
two moves under one word is exactly what this rule stops. A **scissor**
circles the ball and pushes away with the *same* foot, a **step over** pushes
away with the *other* one. Keep them apart in any wording.

## Things that will bite you

- **One profile only.** `get_athlete()` returns the single non-staff user.
  The coach screen sits behind the same code and is kept off Will's tab bar,
  not behind a second account. Staff get a 403 from `/api/plays/`: the phone
  keeps one list of plays whoever is signed in. Don't sign into `/admin/` on
  his phone.
- **`{# #}` template comments are single-line.** Spread one over two lines
  and it is no longer a comment — the text renders onto the page, and the
  response is still a 200 so nothing looks wrong. `TestTemplateComments`
  guards this.
- **Functions that read history take the date explicitly.** Never call
  `date.today()` inside `progress.py` or `deck_rules.py` — the tests pin dates.
- **Test fixtures use `test-` prefixed slugs** so they compose with the
  `seeded` and `deck` fixtures, which create the real drills and cards.

## The cards are the product

`deck_data.py` holds the cards. `TestDeckContent` in `test_deck.py` asserts
what it can: two or three sentences a card, no wall and no other person (the
rebounder does a wall's job), kit flags that agree with the text, and timed
cards of 30 or 60 seconds. The rest of the brief is kept by hand: both feet,
weak foot first on per-foot cards; no ballless sprints; instructions written
for Will to read himself - second person, present tense, no jargon - with one
cue about the result. Ball mastery and first touch are the priority:
technique over fitness.

## Design rules

Built for a 9-year-old on a phone, outdoors:

- Large tap targets (64px minimum), high contrast, minimal text.
- **No dropdowns and no typing anywhere except the PIN pad** on Will's
  screens. Scores are entered with the stepper (-5, -1, +1, +5). Coach
  screens may use ordinary form controls.
- **Nothing counts down at him** - with one exception. On a card with
  `timer_seconds` ("how many in 30 seconds") he taps Start himself, a bar
  fills with no numbers, and it buzzes and says "Stop!" at the end. Agreed
  by Phil, 3 Oct 2026: the limit is the game and he chose to start it. No
  digits counting down, anywhere - not in the text, not in `aria-valuenow`
  or `aria-valuetext`. `TestDeckScript` reads `runTimedBar` in `deck.js` to
  guard it. Time-scored cards use a stopwatch that counts up and he stops.
- Palette is white, grey and blue. Contrast ratios were measured, not
  eyeballed: body text ≥5:1, accent `#1667c9` at 5.5:1 on white. Keep it that
  way — he reads this in bright sun.
- **Nothing is identified by colour alone.** Medals are a word and stars, the
  lit tab has a bar and heavier type, and every coloured dot sits beside a
  written label. Skill colours are validated for colour-blind separation.
- The chart on Before the cards is one measure across seven named
  categories, so it uses **one colour, not seven**. Do not rainbow it.
- **Anything that scrolls sideways must be a shortcut, never the only door.**
- **Rewards are badges and medals, never real-world prizes, and nothing
  rewards hours or days in a row on their own** - pressure is the main reason
  children drop out.
- Bold and sporty, not cutesy.

## Offline

The service worker is served from `/sw.js` (root scope, rendered by Django so
the precache list is built in `_precache_urls`). It precaches the deck at
`/`, `deck.js`, `app.js`, Before the cards, the offline page, the manifest
and the icons. It only stores a clean same-origin 200 (`keep()`) - caching the
login redirect would strand him on a login screen he cannot get past with no
signal, and `cache.add` would follow a redirect and store the login page
under `/`.

Service workers only register over **HTTPS or on localhost**. On a plain-http
LAN address the app works but caches nothing. On Render it is HTTPS, so
offline works there.

Bump `CACHE` in `training/templates/training/sw.js` when static assets change
— filenames are not content-hashed. `test_switch_over.py` holds the current
name.

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
  is a once-ever job for Phil, done from Safari's Share sheet or Chrome's menu.

## Deployment

Render, via `render.yaml` + `build.sh`, deploying `main` - merging is
deploying. SQLite lives on a **persistent disk** at `/var/data`; without it
Render wipes the database on every deploy and Will loses his history. The disk
is mounted only at runtime, so `migrate` and `seed_drills` run from
`startCommand`, not `build.sh` - during the build `/var/data` does not exist
and sqlite fails with "unable to open database file". `seed_drills` writes to
his database on every start (skills, inactive drills, badges, cards, profile),
always by `update_or_create`, never by delete. Regenerate `requirements.txt`
from the lock after changing deps:

```bash
uv export --no-dev --no-hashes --no-emit-project -o requirements.txt
```

Production settings refuse to start without `WILL_SECRET_KEY` and `WILL_HOSTS`
— that guard is intentional, do not soften it. Run **one gunicorn worker**: the
login throttle keeps counters in local memory.

**Back the disk up before any deploy that carries a migration.** The file at
`/var/data/db.sqlite3` is the only copy of his history. From the Render shell
(paste one line at a time):

```bash
python -c "import sqlite3,datetime; s=sqlite3.connect('/var/data/db.sqlite3'); d=sqlite3.connect('/var/data/db-backup-%s.sqlite3'%datetime.datetime.now().strftime('%Y-%m-%d-%H%M')); s.backup(d); d.close(); s.close()"
ls -l /var/data
```

The time is in the name so a second deploy on the same day never overwrites
the first backup. That is SQLite's online backup API - safe while gunicorn is serving, no lock
held, and it does not need the `sqlite3` CLI, which is not on the image. Check
it is real rather than a zero-byte file, and write down the row counts for
`training_sessionlog`, `training_sessionclock`, `training_earnedbadge` and
`training_play` so you have something to compare against afterwards. The
backup lands on the same disk, so it survives a bad migration but not a lost
disk; pull it off the box if you want a real one.

Worth knowing: `startCommand` is `migrate && seed_drills && gunicorn`, so a
migration that fails takes the app down rather than serving a half-migrated
database. That is the right failure, but it is a failure - check
`PRAGMA foreign_key_check` comes back clean before deploying a migration that
rebuilds a table. On SQLite an `AddField` rebuilds the table (`CREATE new /
INSERT SELECT / DROP / RENAME`), safe only because Django wraps it in
`PRAGMA foreign_keys = OFF`.

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
