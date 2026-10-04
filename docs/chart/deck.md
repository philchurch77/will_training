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
- **Leg 2 split in two** (3 Oct 2026, Phil agreed): 2a scores, 2b goals and badges. Too much for one passage.
- **Leg 2 decisions** (3 Oct 2026, Phil took every recommendation):
  - *Where the rules live.* A play is **stamped** once, on the phone, when he saves it: `points`, `medal`, `bests`, stored on the play and never worked out again. Totals, levels and unlocks are sums and maxes of stamps, so a later rule change never takes anything back. Every number lives in `training/deck_rules.py` and reaches the phone as the `deck-rules` block. History rules (weeks in a row, badges) are worked out on the server from Play rows (2b). There is no JS test runner, so no rule is written twice except "a deck session is 3 different cards on one day" (2b).
  - *Points.* 10 for any card, free play included; +5 on per-foot cards and Weak foot keepy-ups; +20 per foot that beats his best; the whole card doubled on the skill of the week's move.
  - *A first-ever score is not a personal best*, for the bonus or Record breaker.
  - *Levels.* Grassroots 0, Academy 300, First Team 1000, Captain 2500, Legend 5000. Thresholds may be lowered, never raised.
  - *Medals* judge the worse foot of the play. A medal won is kept if a target is later raised. Shown as a word and stars (Bronze one, Silver two, Gold three), never colour alone.
  - *Skill blocks* count from Monday 5 Oct 2026: one move a week in the order chop turn, drag back, scissors, Matthews, outside hook, Cruyff turn, elastico, body feint, repeating; every fourth week is test week, and its move still counts double.
  - *Unlocks.* Gold on a move level opens the next. Locked cards are never dealt or played; they show a lock and the words. The Moves card in his hand is always the skill of the week, at its highest open level.
  - *Test week* (2b) is a button in test weeks listing toe-taps-30, foundations-30, rebounder-two-touch, slalom-race, corners, keepy-ups-best; all six in one test week earns Test week done.
  - *Weak foot closer* (2b): rebounder-two-touch in a test week, weak foot at least 80% of strong, strong above 0.
  - *Free play* (2b) is one of a session's three cards, not a session on its own.
  - *Season* (2b) is 30 goal weeks in total; 3 weeks and 10 weeks are in a row.
  - *Old badges retire at the switch-over* (leg 3), not before; leg 2b builds the Legend tag with nothing retired yet.
- **Leg 2a decisions forced in build** (3 Oct 2026): a bad stamp is dropped, never a reason to refuse a play; a medal with no score is dropped; a best of 0 is no best; the skill of the week is None before `BLOCKS_START`; `restore()` fills a missing stamp from the server, nulls only; stamps are read-only in the admin; a card's slug, move and level are frozen; free play shows what it earned. For 2b: "Done today" does not yet count free play - 2b's session rule (free play is one of the three) fixes it.
- **Rewards are badges and medals, no real-world prizes**, and nothing rewards hours or days in a row on their own: pressure is the main reason children drop out.

## Legs

| # | Leg | Blocked by | Delivers | Crew | Status |
|---|---|---|---|---|---|
| 1 | The deck, saved on the phone | — | Phil, from the coach screen, opens /deck/, is dealt a hand, plays cards with the stepper, stopwatch and timed bar, sees records update - all with no signal, synced to Render when signal returns | Quartermaster, Carpenter, Bosun, Master-at-Arms (new API), Purser (migration 0008, plays), Gunner, Lookout | built 3 Oct 2026 on `deck-step-1`; to try on Render (offline needs HTTPS), then `clear_trial_plays` before hand-over |
| 2a | Scores that mean something | 1 | Points on every play, player levels, medals, move levels that unlock on gold, the sticker album, skill of the week - all offline | Quartermaster, Carpenter, Bosun, Master-at-Arms (API accepts more), Purser (0009), Gunner, Lookout | built 3 Oct 2026 on `deck-step-2`; deploy carries migration 0009 (back up first) |
| 2b | Goals and badges | 2a | The weekly goal bar, weeks in a row, test week, the new badges awarded at sync, the Legend tag on retired badges | Carpenter, Bosun, Master-at-Arms, Purser (0010 rebuilds the badge table), Gunner, Lookout | open |
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
- **For 2b, decide before building:** the Gold medal and Record breaker badges would naturally read the phone's stamps (`medal`, `bests`), which the server stores but does not re-judge. A badge is permanent, so either work those two out on the server from scores, Card targets and earlier plays, or record here that trusting the stamps was accepted. Master-at-Arms, leg 2a.
- **For leg 3:** converting his old history must stamp medals as well as points, or his past gold never opens a level. Plays saved before 2a are unstamped and count for nothing.
- A coach-facing view of plays the server refused, with the reason; today only a count shows on the phone.
- Whether the phone's plays should be keyed per user; for now the staff 403 stands in for it.
- Paging `GET /api/plays/` after a few seasons of plays.
- A real-phone check of the buzz: iPhones cannot vibrate and the silent switch mutes the beep, so "Stop!" on screen carries it.

## Out of scope

- Real-world prizes.
- Rewards for hours, or for days in a row on their own.
- A second athlete, or a second account for Phil.
- An SPA framework or a build step: the deck is plain JavaScript.
