---
name: deck-sync
description: How deck plays move between phone localStorage and /api/plays/, and the loss paths found in leg 1 (2026-10-03) to re-check next passage
metadata:
  type: project
---

Plays live in localStorage `will-deck-plays-v1`; `synced` is set from the POST
answer and from `restore()` (GET). Free text: none - Play is numbers only;
Card text is seeded, all fields well under max_length (checked all 51).

**Open at leg 1 review (2026-10-03), re-check before re-raising:**
- `restore()` only ever sets `synced=true`. A play the server no longer has
  (disk backup restored, `clear_trial_plays`) is never resent, and the status
  line says "Every score is backed up". CLAUDE.md claimed the phone "sends
  them back"; it does not.
- Per-foot cards hold the weak-foot score in memory only until the strong
  foot is saved.
- `updatePlays` ignores `savePlays` refusing; the play is dropped from memory too.
- `api_plays` IntegrityError branch reports saved without checking the row exists.
- No deck tests existed at all; docstrings named `TestDeckScript`/`test_deck.py`
  before they were written.
- `clear_trial_plays` deletes every Play with only `--confirm`.

**Why:** the deck's whole promise is "the phone and Render together never lose
a play", and these are the places that promise rests on one side only.
**How to apply:** next deck passage, check each item is fixed or has a stated
decision, then rewrite this note to what remains. See [[cascades]].
