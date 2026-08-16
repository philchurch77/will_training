---
name: pre-deploy
description: Run only the Azure deployment checklist (no Les pass, no commit stage). The checklist itself lives in wheels-up.md — this command runs its Stage 2 so the two never drift.
allowed-tools: Read, Grep, Glob, Bash
disable-model-invocation: true
---

# Pre-Deploy (checklist only)

Read `.claude/commands/wheels-up.md` and execute **Stage 2 — Deployment
checklist** exactly as written there, reporting pass/fail per item. Skip
Stages 1 and 3. Wheels Up is the single source of truth for the checklist —
do not maintain a separate copy here.

Finish with the same one-line verdict: **Ready to deploy** or
**Fix before deploying**, listing any failures.
