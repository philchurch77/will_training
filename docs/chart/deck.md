# Chart: deck

Phil's plan of 3 Oct 2026, "Will's Training: the card deck plan", recorded
here so the next session does not have to ask for it. Words used below are
defined in `CONTEXT.md` at the project root.

## Destination

Will opens the app to a hand of scored challenge cards instead of a fixed
six-drill day, plays any three, and chases medals and his own bests, weak foot
first. Every play is saved on the phone first and backed up to Render, so no
signal never matters and no history is ever lost.

## Why

| The research says | The app did |
| --- | --- |
| He chooses the order and sets the challenge | A fixed six-drill plan, same order each time |
| Mix several moves in short bursts | Five minutes on one drill at a time |
| Scores, targets and personal bests beat counted repetitions | Mostly ticks; only some drills have a score |
| 3 to 4 home sessions a week, plus rest and free play | Six 30-minute sessions a week, and a missed day breaks his streak |
| Juggling is a warm-up or a challenge, not a pillar | One juggling block required in every session |
| Measure weak-foot rebounder passes and slalom time, not hours | Measures minutes and streaks |

Offline has a structural cause: every screen is built by the server, so with
no signal he sees an old saved copy. The deck is drawn on the phone instead.

## Decisions so far

- **Replace the app in place**: same address and home-screen icon, so nothing to reinstall and his history comes with it.
- **Weekly goal of 3 sessions**: the research target for a squad player already training with his club. Rest days never break anything.
- **Dealt 5, play any 3**: confirmed by Phil 3 Oct 2026. The hand is 5 cards from different packs, always one move card and one quick-feet or combo card. He can deal a new hand or pick from the whole deck at any time.
- **Timed cards are an exception to "nothing counts down at him"**: confirmed by Phil 3 Oct 2026. On a "how many in 30 (or 60) seconds" card he taps start himself, a bar fills with no numbers shown, and it buzzes at the end. The limit is the game and he chose to start it, which is not what the rule was written against (a clock running down on a drill he was enjoying). No digits counting down, anywhere. Recorded in `CLAUDE.md`.
- **Scoring without typing**: a stepper with -5, -1, +1, +5. Timed races use a stopwatch on the card he starts and stops.
- **Weak foot first**: per-foot cards ask for the weak foot before the strong. Medals are judged on the weaker foot.
- **Render stays as the backup**: plays carry an id made on the phone, so a repeat send changes nothing; a phone that loses its copy downloads his plays back.
- **Two new tables only** (`Card`, `Play`): no existing table is touched; old logs, bests and badges carry over at the switch-over.
- **Cards are retired, never deleted**: `Play.card` is `PROTECT`; retire via `RETIRED` in `deck_data.py`.
- **Kit**: ball, rebounder, goal, cones. No wall: every rebounder card says rebounder.
- **Naming**: "inside hook" is the existing chop, so it is *Chop turn*. Scissors and step over stay separate moves. Toe taps and foundations come back as 30-second races, not warm-ups. No ballless sprints.
- **Leg 1 decisions** (3 Oct 2026): the stepper starts at 0; free play is a fixed button, never dealt; Phil's trial plays come off with `clear_trial_plays --through DATE --expect N` (plays stay undeletable in the admin, scores read-only there, no Add); the phone resends any play the server no longer has; a weak-foot score is kept on the phone (`will-deck-draft-v1`) until the strong foot is saved; staff accounts get a 403 from `/api/plays/`, because the phone keeps one list of plays whoever is signed in; a 0 is saved but not cheered; the PIN pad honours a same-site `?next`.
- **Rewards are badges and medals, no real-world prizes**, and nothing rewards hours or days in a row on their own: pressure is the main reason children drop out.

## Legs

| # | Leg | Blocked by | Delivers | Crew | Status |
|---|---|---|---|---|---|
| 1 | The deck, saved on the phone | — | Phil, from the coach screen, opens /deck/, is dealt a hand, plays cards with the stepper, stopwatch and timed bar, sees records update - all with no signal, synced to Render when signal returns | Quartermaster, Carpenter, Bosun, Master-at-Arms (new API), Purser (migration 0008, plays), Gunner, Lookout | built 3 Oct 2026 on `deck-step-1`; to try on Render (offline needs HTTPS), then `clear_trial_plays` before hand-over |
| 2 | The game layer | 1 | Points, player levels, medals and unlocks, the weekly goal bar, skill of the week, test week, the new badges | Quartermaster, Carpenter, Bosun, Purser, Gunner, Lookout | open |
| 3 | Switch over | 2 | The deck becomes the home screen; old history shown read-only and converted into starting points and personal bests; the fixed plan screens retired | Full crew; Purser and a disk backup before deploy | open |

### Leg 2 detail, from the plan

- **Points and levels.** Base points for a card, a bonus for weak foot first, a big bonus for beating his own best, double on the skill of the week. Player levels: Grassroots, Academy, First Team, Captain, Legend.
- **Medals.** Bronze, silver, gold per card, judged on the weaker foot. Each move climbs three levels (on the spot, cone run, beat the cone); gold on one opens the next. A moves page shows every card like a sticker album, empty slots included.
- **Skill of the week.** One featured move worth double, on four-week blocks: chop turn, drag back, scissors, Matthews; then outside hook, Cruyff turn, elastico, body feint.
- **Test week.** Every fourth week a Test card opens six self-tests: toe taps, foundations, rebounder passes, slalom, corners, keepy-ups.
- **Badges.**

| Badge | What happens to it |
| --- | --- |
| First session, drill counts (now card counts), All rounder, Two footed, Keepy-up king | Kept; already earned stays earned |
| Day streaks (3 in a row, Full week, Month machine) | Replaced by weeks in a row hitting the goal: 3 weeks, 10 weeks, Season |
| Perfect week, 500 minutes, Century | Retired; any already earned stay with a Legend tag |
| Gold medal | New: first move at gold |
| Weak foot closer | New: weak-foot test score within 20% of the strong foot |
| Record breaker | New: 10 personal bests |
| Test week done | New |
| Free player | New: logged free play or a garden 1v1 |

## The deck

51 cards in eight packs, in `training/deck_data.py`:

| Pack | Cards | What they are |
| --- | --- | --- |
| Moves | 24 | 8 moves x 3 levels: on the spot (30 s, per foot), cone run (timed), beat the cone (clean beats out of 8) |
| Combos | 6 | The existing warm-up combinations, clean combos in 30 s, per foot |
| Rebounder | 5 | Two-touch and one-touch passes in 60 s, receive and turn, touch into space, catch the egg |
| Quick feet | 4 | Toe taps, foundations, one-foot inside-outside, pull-push, all in 30 s |
| Finishing | 4 | Pick your corner, laces on the move, set and finish, volley it in; 5 shots per foot |
| Keepy-ups | 4 | Best run, weak foot only, left-right, thighs |
| Dribbling | 3 | Slalom race, speed dribble race, slow-slow-fast |
| Free play | 1 | "I played football": no score, counts toward the week |

## Not yet charted

- Medal targets are first guesses; adjust after his first test week.
- Points per card and the score for each player level (leg 2).
- Which date the four-week skill blocks and the test week count from (leg 2).
- How old minutes, ticks and per-drill counts convert into starting points and personal bests (leg 3).
- What `CLAUDE.md` rules retire with the fixed plan at the switch-over, and the `test_seed.py` assertions that go with them (leg 3).
- `clear_trial_plays` must be deleted in leg 3, once every play is his.
- A coach-facing view of plays the server refused, with the reason; today only a count shows on the phone.
- Whether the phone's plays should be keyed per user; for now the staff 403 stands in for it.
- Paging `GET /api/plays/` after a few seasons of plays.
- A real-phone check of the buzz: iPhones cannot vibrate and the silent switch mutes the beep, so "Stop!" on screen carries it.

## Out of scope

- Real-world prizes.
- Rewards for hours, or for days in a row on their own.
- A second athlete, or a second account for Phil.
- An SPA framework or a build step: the deck is plain JavaScript.
