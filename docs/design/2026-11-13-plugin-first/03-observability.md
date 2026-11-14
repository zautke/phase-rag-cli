# Observability: independent logging and error packages

**Design status:** proposed, 2026-11-13. This specifies behavior, not an existing implementation or a verified deployment. See [architecture](02-architecture.md), [delivery and team gates](04-delivery-and-teams.md), and [research](05-research.md).

## Package boundary and composition

Build two independently installable, reusable Python packages: `phase_rag_logging` for structured logging and `phase_rag_errors` for error reporting. Neither imports the other. Each can operate alone, with no RAG or CLI dependency, and each can simultaneously send its own events to a JSON Lines file, a human-readable standard-error console, and the official OpenTelemetry Protocol (OTLP) exporter. All three are independently enabled and configured. File and console use Python logging or small sink implementations; OTLP uses the official OpenTelemetry Python SDK, not a custom wire client. No sink writes to standard output, which remains reserved for the phase payload.

Both packages depend on `diagnostic_contracts`, a tiny independently reusable package with a sink contract, without depending on each other's concrete implementation: `emit(record)`, `flush(deadline)`, and `close(deadline)`. `emit` accepts an immutable, versioned event envelope; the result reports local acceptance or failure per sink, never claims backend delivery. A host can inject any compliant sink; package-provided sinks implement the same contract. Each package owns its own sink instances and logger namespace; if both are installed, do not attach the same handler twice, propagate to root, or forward an error through both packages. The shared contract itself has no runtime initialization, application configuration, or exporter dependency. A sink's failure cannot prevent other sinks receiving an event or replace the application's result or original exception.

The host explicitly constructs configuration, resources, sinks, and lifecycle once per process; imports do not create files, threads, network connections, handlers, or global providers. A context manager or explicit `start`/`close` supports both standalone library use and plugin-runner injection. Never shut down a provider or sink borrowed from the host: ownership is explicit. Use namespaced loggers with `propagate=False`, and ensure initialization is idempotent for a given instance. Standalone decorators wrap ordinary synchronous or asynchronous callables without requiring the plugin runner. The runner adds run/phase context at its boundary, calls plugins through the same interfaces, and closes only resources it created.

The public APIs below use the shared contract types `EventContext`, `Sink`, `EmitResult`, and `DiagnosticEvent`; `Exception` means the actual Python exception instance. Construction does not start sinks. Context is immutable and may be extended for each operation; decorators preserve function signature metadata, return values, and sync/async behavior.

```python
# diagnostic_contracts
class Sink(Protocol):
    def emit(self, event: DiagnosticEvent) -> EmitResult: ...
    def flush(self, deadline: float | None = None) -> bool: ...
    def close(self, deadline: float | None = None) -> None: ...

# phase_rag_logging
def create_logger(*, sinks: Sequence[Sink], context: EventContext) -> Logger: ...
def log(self, severity: str, message: str, *, attributes: Mapping[str, object] | None = None) -> EmitResult: ...
def log_operation(logger: Logger, *, operation: str) -> Callable: ...

# phase_rag_errors
def create_reporter(*, sinks: Sequence[Sink], context: EventContext) -> ErrorReporter: ...
def report(self, error: BaseException, *, code: str, retryable: bool, attributes: Mapping[str, object] | None = None) -> EmitResult: ...
def report_errors(reporter: ErrorReporter, *, code: str, retryable: bool) -> Callable: ...
```

`deadline` is an absolute monotonic-clock deadline and expresses caller intent; a `False` flush or sink failure is reported without changing the wrapped operation. Decorators emit operation metadata or report escaping failures, respectively; error decorators re-raise the same exception and do not report cancellation by default. `EmitResult` maps sink identity to `accepted`, `rejected`, or `failed`; accepted means only accepted locally. Lifecycle construction, replay command and concrete sink factories are package entry points, not implicit behavior on import. Any stronger deadline behavior requires the isolation described below.

## Event and error contracts

Use UTF-8, one complete JSON object per file line. Version `1` fields below are mandatory unless marked optional; unknown extension attributes live only in `attributes`, and sinks preserve the same event ID across copies. Scalars are strings, booleans, finite numbers or null; attributes may also contain arrays of those scalar types. Reject or safely stringify unsupported values at the caller boundary, without crashing application work. Reserve the standard field names. Use UTC RFC 3339 timestamps with an offset, and generate unique event IDs; never use wall-clock time alone for identity.

| Common field | Contract |
| --- | --- |
| `schema_version` | Integer `1`. |
| `event_id` | UUID identifying this occurrence, stable across the three sinks and any replay. |
| `timestamp` | UTC event creation time. |
| `kind` | `log` or `error`. |
| `severity` | `TRACE`, `DEBUG`, `INFO`, `WARN`, `ERROR`, or `FATAL`; map to corresponding OpenTelemetry severity. |
| `message` | Short human-readable summary. |
| `service.name`, `service.version` | Host-provided resource identity; version may be absent. |
| `run_id`, `phase`, `attempt`, `operation` | Optional execution identifiers: run ID shared across a run, phase name, nonnegative attempt number, and operation name. |
| `plugin.id`, `plugin.version`, `plugin.instance_id` | Optional plugin identity, version, and UUID instance for plugin events; all three required when an event originates from a plugin. |
| `branch` | Optional execution branch identifier; required when an event is associated with a branch. |
| `artifact.commit_state`, `artifact.delivery_state` | Optional controlled state values when applicable: commit `pending`, `committed`, `failed`, or `unknown`; delivery `not_attempted`, `pending`, `accepted`, `failed`, or `unknown`. Accepted describes a named hop only, never end-to-end delivery. |
| `trace_id`, `span_id` | Optional valid active OpenTelemetry trace/span IDs; absent when no context exists. |
| `attributes` | Flat, namespaced event details; empty object by default. |

The error package adds mandatory `error_id` (UUID, stable for the logical error across handoffs), `error.code` (stable host-defined classification string), `retryable` (boolean for the operation at this boundary), `error.type` (dynamic fully qualified exception class), `exception.type`, `exception.message`, and `exception.stacktrace`. When an error wraps another, use one report at the chosen handling boundary and preserve Python's `__cause__`, unsuppressed `__context__`, notes, and exception groups in the natural stacktrace via `traceback.format_exception(exc, chain=True)`. A meaningful inner type may classify `error.type`; preserve the outer exception in the stacktrace. Optional `caused_by_error_id` links separately reported causal occurrences; never infer equality from message text. `event_id` denotes a report; `error_id` denotes the logical failure; neither is an exactly-once delivery key. Truncation, if configured, must set an explicit `stacktrace_truncated` attribute and preserve the beginning and end; test nested groups and chained exceptions. See [exception conventions](https://opentelemetry.io/docs/specs/semconv/exceptions/exceptions-logs/) and [Python traceback](https://docs.python.org/3.11/library/traceback.html).

Default events contain operational metadata only. Raw documents, retrieved passages, queries, prompts, answers, and model payloads are excluded unless the host explicitly opts in for the specific field. The host controls attribute selection and size limits; the sink must not silently add payload data. This is a data-volume and intended-observability policy, not a claim that arbitrary exception messages contain no payload.

## Error and span semantics

Report a propagated failure once at the selected ownership boundary. Error reports are OTLP log records correlated with the active span when available. Set failed operation span status to `ERROR` and `error.type`; do not mark an enclosing operation failed when it recovered successfully. Configure existing instrumentation and span context managers to avoid creating a second exception event for the same exception when the error reporter emits it; also avoid invoking both packages for the same occurrence. Distinct events for distinct operations remain allowed. Cancellation and process interrupts retain their original semantics: clean up in `finally`, do not swallow or convert them to success, and re-raise cancellation. Expected cancellation is not automatically an application error; report only when the host explicitly classifies it as such. [OpenTelemetry error guidance](https://opentelemetry.io/docs/specs/semconv/general/recording-errors/) discourages recording the same exception repeatedly; exception conventions support logs and document migration from span events.

## Configuration, process boundaries, and lifecycle

The deployed project's authoritative `.env` template defines all settings and the values below; runtime environment supplies those values, then explicit host configuration overrides them. Validate overrides before creating sinks. Libraries imported or constructed without sinks have no side effects and emit nowhere. The deployed project explicitly enables all three sinks for each package; its endpoint, file paths, and resource identity come from that environment template and deployment configuration, with no code fallback. Defaults apply independently to each package:

| Setting | Default / valid bounds |
| --- | --- |
| Console / file / OTLP | deployed project: enabled / enabled / enabled; OTLP requires explicitly configured endpoint and protocol. Standalone library: no sinks until injected. |
| File path | host-supplied writable per-package path; no repository or working-directory assumption. |
| File rotation | 10 MiB per file, 5 backups; configure positive sizes and bounded backup count, including zero to disable backups. Use separate files per process or a proven multiprocess-safe writer; stdlib rotation alone is not a cross-process lock. |
| Event / stacktrace limit | 64 KiB / 32 KiB per event, with explicit truncation marker; do not split JSON Lines records. |
| Batch queue / batch size | 2,048 / 512 records; positive and batch size no larger than queue. Bound both event size and queue to bound memory approximately. |
| Schedule delay / network timeout | 1 second / 5 seconds; positive, finite values. Configure the selected exporter timeout, not merely the batch processor timeout. |
| Shutdown budget | host target 5 seconds; best effort without process isolation, never a hard deadline guarantee. |

The project selects HTTP/protobuf package `opentelemetry-exporter-otlp-proto-http`, with `opentelemetry-api` and `opentelemetry-sdk` at mutually compatible pinned versions. Set the service resource, transport, endpoint and exporter settings from configuration. HTTP signal-specific endpoints must match the receiver's `/v1/logs` path; do not guess whether a configured value already includes it. The organization gateway and Grafana are candidate destination and viewer, **not verified live**. No exporter starts unless enabled and configured. Follow [official Python exporter guidance](https://opentelemetry.io/docs/languages/python/exporters/).

For a subprocess, copy the environment, inject the active W3C trace context into that copy, pass it only to that child, then extract and attach it on startup; detach after use. Generate or pass the run ID separately. Do not mutate global environment for concurrent children. Independent shell pipeline siblings cannot infer a shared parent trace; their launcher must supply context explicitly. Use [Python propagation](https://opentelemetry.io/docs/languages/python/propagation/); [environment propagation](https://opentelemetry.io/blog/2026/environment-variable-context-propagation/) is evolving, so verify support in pinned libraries before relying on automated behavior.

At normal completion, stop accepting events, request flush, then close owned sinks and providers. Document returned acceptance and per-sink failures independently. Exporter errors are reported once, rate-limited, to an isolated stderr diagnostic channel, never fed back into the failing OTLP handler. A broken file or console is similarly isolated; count drops and failures through an independent observable channel where available. Do not turn telemetry failure into CLI failure by default. A host that requires auditing must explicitly choose stronger semantics and a durable system designed for it.

## Delivery and recovery limits

SDK batching is bounded and in-memory. Queue overflow, serialization or size failure, network outage, retry exhaustion, abrupt process termination, and shutdown before export can lose events. Retrying after an unacknowledged request can duplicate events. Local file write does not mean `fsync`, backend receipt, or automatic replay. Rotation can delete old events. No exactly-once, end-to-end at-least-once, persistence across crashes, or strict shutdown deadline is promised. If the host requires a hard shutdown bound, run the remote exporter in a separate owned worker process, stop accepting work, request drain, and terminate that process at the deadline; queued or in-flight telemetry may be lost. A thread, async timeout, or `force_flush` parameter alone cannot guarantee that bound.

Provide an explicit bounded replay command in each package: `phase-rag-logs-replay --input-file PATH --checkpoint-file PATH --max-records N` and `phase-rag-errors-replay --input-file PATH --checkpoint-file PATH --max-records N`. Both use named switches only, take destination from the same host configuration, validate the event schema, and preserve original `event_id` and `error_id`. Each run reads at most `N` complete records from the selected retained file, records file identity and byte offset in an atomically replaced checkpoint after a confirmed exporter response for a batch, and stops with a nonzero status on parse, identity, or export failure. If the file was rotated, replaced, truncated, or cannot be matched to the checkpoint, fail visibly instead of silently skipping data. Retry from the previous checkpoint after ambiguous failure, accepting duplicates. Replay yields at-least-once **attempts** for checkpointed input while retained and accessible, not guaranteed backend delivery; an acknowledged collector hop may still lose data. It does not automatically run, extend retention, reconstruct deleted records, or promise `fsync` durability. Keep replay stderr diagnostics out of stdout payloads.

The official SDK's documented `OTEL_BLRP_EXPORT_TIMEOUT` currently has no effect. At upstream source commit [`6aa7221`](https://github.com/open-telemetry/opentelemetry-python/blob/6aa7221a6a99b4a4512479d31c71c8f57d63e66a/opentelemetry-sdk/src/opentelemetry/sdk/_shared_internal/__init__.py), the batch processor drops the oldest queued item on overflow, `force_flush` ignores its timeout and returns success after a blocking export without establishing backend delivery. **This is source evidence for that commit, not a claim about any installed or released version.** Pin a release, inspect and test its behavior; do not depend on `force_flush` for a hard deadline or delivery acknowledgment. The [SDK environment reference](https://opentelemetry-python.readthedocs.io/en/stable/sdk/environment_variables.html) documents the timeout limitation.

A Collector can add a bounded persistent `sending_queue` using the `file_storage` extension, retry/backoff and monitoring; verify configuration and disk persistence in the actual deployment. Persistence begins only after successful queue admission. Full queue, storage errors, retry expiry, Collector or backend misconfiguration, and loss before admission remain loss paths. Acknowledgment is hop-specific, not proof of backend indexing. Monitor queue size/capacity, enqueue failures, export failures and SDK drop diagnostics separately; ensure monitoring does not rely exclusively on the failing lane. See [Collector exporter helper](https://go.opentelemetry.io/collector/exporter/exporterhelper), [Collector resiliency](https://opentelemetry.io/docs/collector/resiliency/), and [OTLP duplicate-data limitation](https://opentelemetry.io/docs/specs/otlp/).

## Acceptance and fault matrix

### Project error catalogue and replay switches

RAG host defines stable codes: `CONFIG_INVALID`, `PLUGIN_MISSING`, `PLUGIN_INCOMPATIBLE`, `INPUT_INVALID`, `OUTPUT_INVALID`, `PROVIDER_UNAVAILABLE`, `PROVIDER_TIMEOUT`, `INDEX_INCOMPATIBLE`, `ARTIFACT_WRITE_FAILED`, `STDOUT_DELIVERY_FAILED`, and `INTERNAL_ERROR`. Packages accept other namespaced application codes without importing RAG. Configuration/usage errors map to existing exit 2; unexpected/provider/write failures map to exit 1; cancellation maps to exit 130; existing explicit partial/empty exits remain 3/4. Retry eligibility is metadata only: reporter never retries business operations. Only bounded controller policies may retry operations whose side effects are understood.

Replay commands provide short aliases: `--input-file/-i`, `--checkpoint-file/-c`, `--max-records/-n`, and `--help/-h`, plus documented `Usage()`. Replay uses the official exporter synchronously for bounded batches; do not checkpoint based on SDK `force_flush()`. A successful exporter result acknowledges only its receiver hop. Rejected/partial-success counts reported by the receiver must be surfaced where the pinned exporter exposes them; when not exposed, record that limitation rather than claim every record accepted. Existing checkpoints include file identity and digest of consumed prefix. Never silently advance past corrupt/truncated records.

The three lanes are independent outputs, not fallback priorities. A failed file lane cannot prevent console or OTLP attempts; a failed remote lane cannot delay local emission. File output is flushed on each error and normal run shutdown; stable-storage guarantees require explicit fsync policy. `plugin.instance_id` is the configured instance key plus invocation UUID, so it maps back to topology while distinguishing concurrent/repeated calls. Report plugin lifecycle and batch boundaries, not each token/vector by default.

Tests use isolated destinations and never contaminate stdout. For every row exercise logging alone, errors alone, and both together where applicable; assert one event per intended sink, matching IDs and schema, and no extra root handlers. Run against the exact pinned SDK and record versions, elapsed time and drop/failure observations.

| Case | Required evidence |
| --- | --- |
| Standalone sync/async decorator and runner | Success, raised exception, nested/wrapped exception, exception group, and cancellation preserve original result or exception; one report per logical boundary. |
| File and console | Valid complete JSON Lines, correct rotation/retention, stderr output, no stdout bytes; file permission or full-disk error leaves other sinks and original operation working. |
| Exporter disabled / unreachable / slow | Local outputs remain available, exporter failures are visible without recursive log storms, application completion and actual shutdown latency are measured. |
| Saturation / oversized event | Bounded memory, measured drop behavior, explicit truncation or rejection, surviving records valid, failure counters/diagnostics visible. |
| Flush / close / crash | Record actual flush result and duration, repeated close, host-owned provider protection, abrupt termination; assert no unsupported durability claim. |
| Replay | Bounded record count, stable IDs, checkpoint restart, ambiguous acknowledgement and duplicate attempt, malformed or partial lines, replaced/truncated file, rotation and exporter failure. Assert no skipped checkpointed record and no claim of backend delivery. |
| Parent and subprocess | Shared run ID and expected parent/trace IDs; concurrent child contexts stay isolated; independent shell pipeline behavior documented. |
| Collector | In an isolated test deployment, restart with queued data, fill storage/queue, expire retry, reject invalid data, and verify observed loss/recovery; compare event IDs and account for duplicates. |
| Real destination | Only after destination configuration and appropriate authorization, emit uniquely tagged test events from each package, query the actual backend/viewer for each event, and record destination, IDs, time window, screenshots or query results, and any missing/duplicate records. A local mock or successful request alone is not proof of remote visibility. |

No live remote destination, collector persistence, replay, or delivery guarantee has been verified as part of this document.
