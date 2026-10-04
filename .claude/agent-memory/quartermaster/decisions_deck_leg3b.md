---
name: decisions-deck-leg3b
description: Leg 3b of docs/chart/deck.md (badges in one place) as planned 2026-10-04 - KEPT_KINDS, card-day unit, both award paths share one values function, clear_trial_plays delete scope must stay DECK_KINDS, deploy only after the clear
metadata:
  type: project
---

Planned 2026-10-04 on `deck-step-3`. Recommendations; check the chart for what
was accepted before building on them.

**Kept kinds** (Badge.KEPT_KINDS, new constant, no migration): TOTAL_DRILLS
(first-session 1, drills-10/50/100), SKILLS_TRIED (all-skills 7), WEAK_FOOT
(weak-foot-25), JUGGLING (juggling-25). STREAK/TOTAL_MINUTES/PERFECT_WEEKS stay
tick-only and retire in 3c.

**Unit recommended:** a distinct (date, card) - mirrors SessionLog's one row per
drill per day and resists stepper farming. Sum with old ticks for drills / weak
foot (per_foot or WEAK_FOOT_CARDS - the points-bonus set) / keepy-ups pack.
All rounder = max(old skills tried, scored packs played); 7 scored packs, free
play excluded. Scores never enter a kept badge.

**One values function, two award paths.** progress.kept_badge_values(athlete)
feeds _badge_values (Today tick + old Progress) and award_deck_badges (sync).
award_badges must adopt the savepoint+IntegrityError pattern: a race inside
drill_complete's atomic would otherwise roll back the tick. Row namedtuple gains
pack, per_foot with defaults so test_deck_rules row() helper still works.

**Data-loss trap:** "ending the DECK_KINDS split" must NOT reach
clear_trial_plays' delete filter. Widening it to kept kinds rewrites earned_on
and drops any kept badge whose value has since fallen (drill_uncomplete deletes
rows). DECK_KINDS stays as a constant; only the display filters lose it.

**Blocker:** render.yaml deploys main (autoDeploy). 3b must not reach main until
clear_trial_plays has run on the 2b/3a code; build 3b on a branch off ac8db55.
After the clear, nobody plays /deck/ on Render under his account until 3c.

See [[decisions-deck-leg3]], [[decisions-deck-leg2b]].
