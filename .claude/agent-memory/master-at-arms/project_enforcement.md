---
name: project-enforcement
description: How will_training enforces access (single child account, request.user filtering, deck API), settings decisions, stamp trust decision, and what was audited clean
metadata:
  type: project
---

Single-child app. No school/org link; ownership is `athlete = request.user` (FK to AUTH_USER_MODEL). Coach screens share the child's session by design (CLAUDE.md "One profile only"); admin needs is_staff.

**Why:** declared nothing sensitive, but treated as a child's data at the dispatcher's request.
**How to apply:** audit ownership as `filter(athlete=request.user)`; there is no org layer to check.

Deck API (`training/deck_views.py` `api_plays`, docs/chart/deck.md):
- `api_login_required` -> 401 JSON anon, 403 JSON staff; GET filters by request.user; POST refuses ids owned by another user ("id in use"); resend = first copy wins (no update path at all, only force_insert); `_no_store` on 200s. CSRF enforced.
- Leg 1 open items now FIXED (verified 2026-10-03 leg 2a): played_at overflow caught + window-checked; IntegrityError race re-checks owner.
- Leg 2a (2026-10-03): stamps points/medal/bests via `STAMP_CEILINGS` in `_parse_play`, int-not-bool, in range, None allowed. Scratch probe (ran, 8/8): huge ints, negatives, floats, NaN/Infinity, strings, lists, dicts, bools all -> per-play refusal, never 500; cross-user and resend cannot change a stored stamp. `/deck/` bakes `deck_rules.rules_json` (constants + skill calendar, no personal data).
- DECISION (Phil, chart "Leg 2 decisions"): server does NOT re-judge stamps; self-inflation only cheats his own account. Accepted. Re-judging medal against current targets would wrongly refuse plays after a target rise, so do not recommend it.
- WATCH for 2b: badges awarded at sync must not be minted from stamps alone (Gold medal <- medal, Record breaker <- bests). Prefer server derivation from score + Card targets/history, or record explicit acceptance. EarnedBadge is permanent.
- At 2a no tests existed for stamps, and `test_deck_rules.py` (named in deck_rules.py docstring) did not exist.
- `clear_trial_plays` deletes ALL Play rows with --confirm; must be removed in leg 3. Not in startCommand.
- deck.js builds DOM via `el()` helper (textContent only); card data and rules via `json_script`.
- sw.js skips /api/ and non-GET; precache uses fetch + keep() (rejects redirected/non-200).

Settings (config/settings.py): DEBUG defaults True locally (env WILL_DEBUG=0 on Render via render.yaml); prod guard raises if SECRET_KEY is the dev key or no hosts. CSRF_COOKIE_HTTPONLY unset on purpose (deck.js reads the cookie). AUTH_PASSWORD_VALIDATORS empty on purpose (4-digit PIN, throttled per IP + global). SQLite on Render disk is a stated decision, not a finding. Session 1 year, rolling, by design.
