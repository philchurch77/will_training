---
name: gauntlet
description: The Gauntlet — mandatory Victor + Vera review for any change touching assessment data, permissions, snapshots, or the trust-wide dashboards. Blocks completion on unresolved concerns.
disable-model-invocation: true
---

# The Gauntlet — Access & Assessment Data Review

You are running The Gauntlet: the mandatory review for any change that touches assessment data, permissions, snapshots, or the trust-wide dashboards.

This workflow exists because this platform holds a whole trust's quality-assurance judgements — staff-authored SEF narratives, tier judgements, and immutable snapshots for every school in the Anglian Learning Trust. The core risk here is **cross-school leakage and role escalation**: a school leader must only ever reach their own school's assessment, while trust roles (Reviewer/ELT, Governor, Trust Admin) have deliberately wide read access that must not become unintended write access. No change to the `assessments`, `csat`, or `home` apps — or to `assessments/permissions.py` — ships without passing this workflow.

---

## Stage 1 — Victor: access-control and data-protection audit

Spawn Victor on all files changed in this feature. Ask Victor to confirm:

- **No cross-school access.** Every queryset returning a school's assessment, judgements, results, or snapshots is scoped through `get_current_school` / `can_view_school`. A school leader is confined to their `UserSchoolAccess` schools plus the session school — they cannot reach another school by guessing a PK or slug.
- **Central permission helpers are used, not hand-rolled.** New views go through `@csat_enabled` and `@require_school()`, and defer to `can_edit_assessment` / `can_moderate` / `can_view_school` / `can_view_trust_dashboard` in `assessments/permissions.py` — permission logic is not duplicated inline.
- **Write paths honour the role matrix.** Governor is read-only everywhere; Reviewer (ELT) may only record agreed/moderated tiers (`can_moderate`) and is rejected on judgement/narrative POSTs; editing an assessment requires `can_edit_assessment`. No change silently widens a role's write surface.
- **Snapshot immutability is preserved.** No new code path writes to `Snapshot.data` after creation; the snapshot admin stays read-only; only superusers can delete. Frozen JSON (with embedded statement texts) is never rewritten from live content.
- **Middleware exemptions stay honest.** Trust-wide pages (`csat_dashboard`, `csat_dashboard_csv`, `csat_school_history`, `snapshot_detail`, `snapshot_docx`) enforce their own access and must not be made to leak by, or bypass, the school-selection middleware.
- **No sensitive assessment data leaks into URLs, logs, or error messages.** `AuditLog` stays append-only, and narrative autosaves log length only — never SEF content.
- Permissions are enforced in views and querysets — not only in templates.

---

## Stage 2 — Vera: end-to-end QA

Spawn Vera to test the changed feature as a real user would, exercising it under `CSAT_ASSESSMENT_ENABLED=True`. Vera should specifically check:

- The core assessment workflow completes without errors: judge a statement → derived tier updates live → SEF narrative autosaves → snapshot submits against the current window.
- A logged-in **school leader cannot reach another school's** assessment, register, or snapshot by guessing a URL, PK, or school slug.
- The feature behaves correctly from a **logged-out** state, a **wrong-role** state (Governor and Reviewer are read-only where they should be), and the **correct-role** state.
- Flag dispatch still holds: with the flag off, `/<slug>/` falls back to the old standards pages; with it on, the domain pages and Register render.

---

## Report

Summarise:
- What Victor flagged and how it was resolved
- What Vera found
- Whether the change is safe to ship

**If either agent raises an unresolved concern, do not mark the task complete.** Surface it clearly to the developer for a human decision — especially anything that could expose one school's data to another, or turn a read-only role into a writer.
