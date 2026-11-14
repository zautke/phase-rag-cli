# Remember

## Durable decisions — 2026-11-13

- Plugin-first means capability identity is independent of numbered phases. Backend selection alone is not multi-plugin composition.
- External packages and chains/branches are required now. Do not substitute repository-only registries or remove branching for simplicity.
- Logging and errors are independent reusable packages; BOTH must have file, stderr console and official OpenTelemetry exporter lanes. Host owns initialization/lifecycle; no global side effects at import.
- A successful SDK flush is not proof of backend receipt. Python Logs API/SDK maturity and commit-specific timeout behavior require pinning and actual verification.
- Strict JSON stdout and atomic artifacts remain. Broken stdout after artifact commit means nonzero exit may coexist with committed artifact and partial stdout.
- Historical 184-chunk memory failure and repaired evidence extraction are historical KB evidence; current status must be reproduced at actual implementation HEAD.
- Main contains unrelated dirty work. Never commit/reset it as documentation cleanup. This scope lives only in isolated design worktree.
- Canonical KB is `mcp__kb`, project `master-kb`; dossier path `projects/phase-rag-cli/design-2026-11-13/`.
- Release branches use exactly three numbers: development MINOR bump, main MAJOR bump. No new version metadata invented for this docs-only branch.

## Limits to preserve

No current product, exporter, backend or deployment verification was performed. No independent final curator signoff; curator worker hit usage limit. Detailed limitations and chronology are in [delivery evidence](../../design/2026-11-13-plugin-first/06-delivery-evidence.md).
