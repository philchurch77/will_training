---
name: seeder-runs-on-render
description: seed_drills runs on every Render deploy against the live database - what that makes safe and unsafe when changing the drill library
metadata:
  type: project
---

`render.yaml` `startCommand` is `migrate && seed_drills && gunicorn`, with no
`--reset`. So every seeder edit is a production data change on Will's real
database, applied automatically.

**Why it matters:** `--reset` calls `Drill.objects.all().delete()`, and
`SessionLog.drill` is `on_delete=CASCADE`. One `--reset` on Render destroys
his entire history, streak and badges. `migrate` runs there too, so a schema
migration for a seed-data change applies without anyone watching it.

**How to apply:** when planning any seed change, state explicitly that
`--reset` must never reach `render.yaml` or `build.sh`, and treat an added
model field as a production migration (Purser). Safe operations:
`update_or_create` on a slug, a new slug, and flipping `is_active`.
`PlanDrill` rows are torn down and rebuilt every run by design - they hold no
history.

See [[decisions-seed-data]].
