# Glossary

The words the app and its code use, so a word means one thing everywhere.
The deck words come from `docs/chart/deck.md`.

## The deck

- **Card** - one challenge with a score, e.g. "Toe tap race: taps in 30 seconds". Model `Card`. Retired, never deleted.
- **Pack** - the group a card belongs to: Moves, Combos, Rebounder, Quick feet, Finishing, Keepy-ups, Dribbling, Free play. `Card.pack`.
- **Hand** - the 5 cards he is dealt. Always one Moves card and one Quick feet or Combos card, the rest from other packs.
- **Deal** - draw a new hand. He can deal again whenever he likes.
- **Play** - one go at one card, with what he scored. Model `Play`; its id is made on the phone.
- **Session (deck)** - three plays on one day. Not the same thing as the old 30-minute session that `SessionClock` times; say "deck session" where both are in reach.
- **Weekly goal** - 3 deck sessions in a Mon-Sun week. Free play counts.
- **Scoring** - how a card's number is read: `count` (more is better), `time` (tenths of a second on the card's stopwatch, less is better), `none` (free play).
- **Per foot** - the card is scored twice, weak foot first. `weak_score` and `score` (the strong foot).
- **Timed card** - a card with `timer_seconds`: "how many in 30 seconds". He starts it; a bar fills with no numbers and it buzzes at the end.
- **Stopwatch** - on a `time` card: he starts it and stops it. Counts up.
- **Stepper** - the -5 / -1 / +1 / +5 control he enters a score with. No typing.
- **Medal** - bronze, silver or gold target on a card, judged on the weaker foot.
- **Move** - one of the eight moves (chop turn, drag back, scissors, Matthews, outside hook, Cruyff turn, elastico, body feint).
- **Move level** - one of a move's three cards: 1 on the spot, 2 cone run, 3 beat the cone. `Card.level`. Not the same as player level.
- **Player level** - Grassroots, Academy, First Team, Captain, Legend, from points (leg 2).
- **Personal best** - his best score on a card; for a per-foot card, per foot.
- **Skill of the week** - the featured move worth double points (leg 2).
- **Test week** - every fourth week, six self-tests (leg 2).
- **Stamp** - the `points`, `medal` and `bests` worked out on the phone when a play is saved, stored on the play, and never worked out again. Null means an unstamped play, worth nothing.
- **Locked / open** - a move level he cannot play until he has gold on the level below. Level 1 is always open.
- **Sticker album** - the 8 moves x 3 levels grid at `#album`, empty and locked slots included.
- **Test card** - the test-week button that opens the six self-tests (2b). Not a Card row.
- **Goal week** - a Mon-Sun week with 3 deck sessions (2b).
- **Legend** - the tag on a retired badge he earned and keeps (2b).
- **Kept badge** - an old-app badge that carries on with the deck: First session, 10/50/100 drills, All rounder, Two footed, Keepy-up king. Counts ticks and card plays together (3b). `Badge.KEPT_KINDS`.
- **Card-day** - one card played on one day, however many times. What a play counts as toward a kept badge, the same as one tick.
- **Sync** - the phone sending plays it has not sent yet to `/api/plays/`, and downloading them back if it has lost its copy.

## The existing app

- **Drill** - one item of the fixed plan. Minutes XOR reps.
- **Plan / plan day** - the fixed fortnight of six-drill days, week A and week B.
- **Tick** - marking a drill done on Today. A `SessionLog` row.
- **Session clock** - the one count-up clock on Today. `SessionClock`.
- **Streak** - required plan days in a row. Replaced by weeks-in-a-row at the switch-over.
- **Retired** - `is_active=False`; the row and every score pointing at it stay.
