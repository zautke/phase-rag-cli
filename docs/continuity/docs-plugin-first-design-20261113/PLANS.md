# Plans

## Goal and delivered state

2026-11-13: deliver durable evidence-backed audit and plugin-first redesign, not further chat-only summaries. [Dossier](../../design/2026-11-13-plugin-first/README.md) delivered in commit `33972cb`, draft PR #6 and canonical KB.

## Accepted design direction

- Multiple plugins within phases via ordered chains and branches with explicit reducers.
- Reusable capabilities across phases; externally installed plugin packages; one entry-point group.
- Versioned schema migration allowed; numbered command names retained. Explicit migration, not silent reinterpretation.
- Separate reusable logging and error-reporting packages, each supporting file, stderr console and official OpenTelemetry exporter independently and simultaneously.
- Metadata default; bounded payload capture opt-in. Existing organization remote stack reused only after current health and receipt verification.
- Luna/xhigh and Terra/high teams, disjoint ownership, independent review and monitored deadlines.

## Planned product sequence after approval

1. Reconcile current feature baseline and freeze contract fixtures.
2. Prove external plugin composition and cross-phase reuse.
3. Implement runtime and diagnostics with typed contracts and explicit failures.
4. Migrate providers, storage-space identity and section references.
5. Review; run real-corpus Windows/Linux batteries and diagnostic lane fault tests.
6. Verify actual remote records and visible walkthrough; release only after review-bot and version gates.

No product deployment or model tests are authorized merely by completing this continuity update. See [delivery plan](../../design/2026-11-13-plugin-first/04-delivery-and-teams.md) for team ownership and acceptance.
