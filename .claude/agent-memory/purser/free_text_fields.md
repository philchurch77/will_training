---
name: free-text-fields
description: Which will_training fields hold typed text, and why the coach edit path currently round-trips them intact
metadata:
  type: project
---

Free text in this project is small and is all on `Drill`:

- `Drill.instructions` — `TextField`. Correct: it is sentences. Written by Phil
  for Will to read.
- `Drill.cue` — `CharField(max_length=60)`. Deliberately bounded: it is one
  coaching cue ("head up", "laces, not toes"), not prose. Accepted, not a
  finding.
- `Drill.name` `CharField(60)`, `Drill.slug` `SlugField(60)`.

`SessionLog` holds numbers only (`actual_reps`, `actual_minutes`, `rating`) —
no typed text, so there is no long-form loss risk on Will's own screens. He
never types anything except the PIN.

**Round trip verified sound:** `DrillForm` (`training/forms.py`) renders
`instructions` as a plain `Textarea(attrs={"rows": 4})` — no `maxlength`. No
template anywhere uses `truncatechars`, `truncatewords` or `striptags`
(grepped `training/templates/` and the static JS). `coach_drill_edit`
re-renders the bound form on invalid, so nothing typed is lost on a validation
error. Save / reload / re-save is byte-for-byte.

Re-check this if a `maxlength` ever appears on the textarea or if a drill
description field is added as a `CharField`.
