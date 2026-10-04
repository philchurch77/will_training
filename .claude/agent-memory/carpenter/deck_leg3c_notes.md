---
name: deck-leg3c-notes
description: Leg 3c switch-over review (2026-10-04) - what is dead now, what 3d removes, flagged items
metadata:
  type: project
---

Layout after 3c: `/` = deck_views.deck (tab "deck"); Progress is a deck.js route (#progress, #badges alias, lightTab); /before/ = views.before_cards (tab "progress", read-only); /deck/ and /progress/ are RedirectViews in urls.py (progress keeps name but nothing reverses it); old Today at /today/ off the tab bar, linked from coach plan.

Dead after 3c, remove now: progress.badge_progress (only tests call it; docstring stale), its two tests; unused imports in tests/test_deck.py (timedelta, CommandError, award_deck_badges, Badge, EarnedBadge); CSS .badge-grid, .badge-nm, .ic-cone*/ic-rock keyframes (Drills tab icon gone); stale comments in models.py ~378, CLAUDE.md ~240/254, README Progress screen lines.

Dead, leave for 3d (goes with Today): progress.current_streak/sessions_this_month still live via Today + coach_logs; .flame CSS used by today.html; _badge_values still computes streak, minutes, perfect_weeks on every tick for badges that are all retired; award_badges old_kinds path; session.js/drill.js/clockchip gating in base.html.

Flagged: Sticker album route lights Cards tab though reached from Progress; Cards tab href "/" reloads page when on a hash (use "#"); no test for the two redirects; test_views ?next=/deck/ now goes via redirect; CONTEXT.md lacks Before the cards, Progress tab, Cards tab, head start, and Streak entry says replaced at switch-over; BLOCKS_START (2026-10-05) must move if 3c deploys after Sun 11 Oct (Quartermaster note).

No shell tool: read-only review.
