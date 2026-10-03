---
name: project-enforcement
description: How will_training enforces access (single child account, request.user filtering, deck API), settings decisions, and what was audited clean
metadata:
  type: project
---

Single-child app. No school/org link; ownership is `athlete = request.user` (FK to AUTH_USER_MODEL). Coach screens share the child's session by design (CLAUDE.md "One profile only"); admin needs is_staff.

**Why:** declared nothing sensitive, but treated as a child's data at the dispatcher's request.
**How to apply:** audit ownership as `filter(athlete=request.user)`; there is no org layer to check.

Deck API (audited 2026-10-03, leg 1 of docs/chart/deck.md):
- `training/deck_views.py` `api_plays`: `api_login_required` -> 401 JSON; GET filters by request.user; POST refuses ids owned by another user ("id in use"); `_no_store` on 200s. Probed with a scratch pytest (ran): anon 401, cross-user GET empty, id reuse refused, CSRF 403 without token / 200 with cookie token, 3 MB body 400 (DATA_UPLOAD_MAX_MEMORY_SIZE default), batch capped at 500.
- Known open at that audit: `played_at` not range-checked -> OverflowError 500 on extreme offsets (ran); IntegrityError race path reports "saved" without re-checking owner (read); no project tests for api_plays at all.
- `clear_trial_plays` deletes ALL Play rows with --confirm; must be removed in leg 3. Not in startCommand.
- deck.js builds DOM via `el()` helper (textContent only); card data via `json_script`.
- sw.js skips /api/ and non-GET; precache uses fetch + keep() (rejects redirected/non-200).

Settings (config/settings.py): DEBUG defaults True locally (env WILL_DEBUG=0 on Render via render.yaml); prod guard raises if SECRET_KEY is the dev key or no hosts. CSRF_COOKIE_HTTPONLY unset on purpose (deck.js reads the cookie). AUTH_PASSWORD_VALIDATORS empty on purpose (4-digit PIN, throttled per IP + global). SQLite on Render disk is a stated decision, not a finding. Session 1 year, rolling, by design.
