# Branch changes: streaming TPM reconciliation and related fixes

This document catalogues every file changed on this branch and explains why. It exists to help reviewers scope the diff and to help engineers pull equivalent changes into a forked repository.

Grouped by area. Test files listed alongside the production code they cover.

## New feature: streaming TPM reconciliation

Adds a post-stream reconciliation path for `/converse-stream` and `/invoke-with-response-stream`. Full architecture: [`03-architecture/07-rate-limit-stream-responses.md`](03-architecture/07-rate-limit-stream-responses.md).

### `backend/app/core/rate_limit/eventstream_parser.py` (new, ~530 lines)

- Pure decode/encode of the AWS EventStream wire format. Stateless. No I/O.
- Exposes `EventStreamParser.decode_all(buf)`, `encode(msg)`, `encode_many(msgs)`.
- Data model: `HeaderType` enum (10 wire types), `Header`, `EventStreamMessage`, `ParseError` with `ErrorKind`.
- Two Terminal_Usage_Event classifiers: `is_converse_metadata` and `is_invoke_metrics_chunk`. Both return `False` (never raise) on payloads that fail UTF-8 or JSON decode.
- Buffer bound: 16,777,216 bytes. Prelude and message CRC-32 validated via `zlib.crc32`.
- Uses `match/case` for HeaderType dispatch in decode and encode paths.

### `backend/app/core/rate_limit/stream_reconciler.py` (new, ~480 lines)

- `StreamTokenReconciler` wraps the upstream async byte iterator. Yields each chunk to the client before parsing it, then feeds the chunk into the EventStream parser to collect terminal usage candidates.
- `_finalize` runs on stream termination. Applies the signed delta `aggregated - estimated` to Shared_TPM_Key via a single `RateLimiter.check_and_consume` call, emits `stream_reconciliation_applied` / `stream_reconciliation_skipped` / `redis_failure_stream_reconciliation` structured logs, records `rate_limit_stream_reconciliation_delta` and `rate_limit_tokens_consumed_total`.
- Three-layer exception isolation: install-time in the middleware, chunk-forwarding in the async generator, finalize-time around the Redis call and telemetry emitters. All wrapped in `_safe_emit` so a broken logger or metric backend cannot surface.
- Data models: `StreamOutcome` (5 values), frozen `TerminalUsage` with int32 clamping, frozen `ReconciliationContext` captured at install time.

### `backend/app/observability/rate_limit_metrics.py` (+24 lines)

- New histogram `rate_limit_stream_reconciliation_delta`. Signed distribution of `aggregated - estimated`, tagged `{client_id, model_id, endpoint}`. Recorded once per successful streaming reconciliation.
- New helper `record_stream_reconciliation_delta(client_id, model_id, endpoint, delta)`.

## Fix: non-streaming TPM reconciliation unreachable behind `BaseHTTPMiddleware`

Fixes a pre-existing bug documented in [`bugs/BUG-2026-07-non-stream-reconciliation.md`](bugs/BUG-2026-07-non-stream-reconciliation.md). Full architecture: [`03-architecture/06-rate-limit-synchronous-responses.md`](03-architecture/06-rate-limit-synchronous-responses.md).

### `backend/app/middleware/rate_limit.py` (+202 lines, -~119 replaced)

Core structural changes:

- Add module-level `_detect_stream_endpoint(path)` classifier that returns `"converse-stream"`, `"invoke-with-response-stream"`, or `None`. Shared by both reconcilers.
- Store `request.state.estimated_tokens = estimated_tokens` in `dispatch` after the pre-request token estimate is computed. Consumed by both reconcilers when they later compute the delta.
- Rewrite `_update_tokens` to route by URL path via `_detect_stream_endpoint`, then dispatch to either `_reconcile_stream` (streaming) or `_reconcile_non_stream` (everything else). Type-based routing is unreliable because `BaseHTTPMiddleware` wraps every response, streaming or not, in `starlette.responses._StreamingResponse`.
- New method `_reconcile_stream(request, response)` installs a `StreamTokenReconciler` on `response.body_iterator`. All install-time errors are captured and logged as `redis_failure_stream_reconciliation` without touching the iterator.
- New method `_reconcile_non_stream(request, response)` drains `body_iterator` into a `bytes` buffer, parses the JSON, applies the signed `delta = aggregated - estimated` via `RateLimiter.check_and_consume`, and reassigns `body_iterator` to a single-shot replay of the buffered bytes so Starlette still forwards the response to the client. Emits `rate_limit_reconciled` / `rate_limit_reconciled_skipped` / `redis_failure_token_update`.

## Local dev enablement: standalone Valkey client

Adds the ability to run the gateway against a standalone `redis:latest` or `valkey/valkey:latest` container. Production is unaffected because the default keeps the existing cluster client.

### `backend/app/services/valkey_service.py` (+34 lines)

- Import `GlideClient` and `GlideClientConfiguration` from `glide` alongside the existing cluster types.
- `create_valkey_client()` now branches on `config.valkey_cluster_mode`. When `True` (production default), constructs the pre-existing `GlideClusterClient` with the same configuration as before. When `False` (local dev opt-in), constructs a standalone `GlideClient`. Both paths share credential handling and TLS flags.
- Client type annotation widened from `GlideClusterClient` to `GlideClient | GlideClusterClient`. `RateLimiter` uses only methods present on both types (`get`, `incrby`, `expire`, `custom_command`), so no downstream changes were required.

### `backend/app/config.py` (+10 lines)

- New env-var-backed setting `valkey_cluster_mode`, defaults to `"true"`. Read from `VALKEY_CLUSTER_MODE`.
- Production infrastructure (`infrastructure/modules/gateway/compute/ecs-task-definition.tf`) does not set this variable, so production continues to use the cluster client. The standalone branch is unreachable in production without an explicit override.

## Fix: JWT scope check blocks Cognito ID tokens in local dev

Adds an opt-in escape hatch for local development against Cognito user pools. Production behavior is unchanged because the flag defaults to off.

### `backend/app/config.py` (part of the +19 lines above)

- New setting `jwt_skip_scope_check`, defaults to `False`. Read from `JWT_SKIP_SCOPE_CHECK`.

### `backend/app/core/auth/jwt_validator.py` (+30 lines)

- When `config.jwt_skip_scope_check` is `True`, `validate_jwt_claims` bypasses both the "scope claim present" and "scope in allowed list" checks. Substitutes an empty scope string for the returned client context so downstream code that reads `scope_context` continues to work.
- Emits a warning log on every request where the bypass fires so the deviation from the resource-server contract stays visible in logs. Production must keep this flag unset.

### `test/unit/core/auth/test_auth_jwt_validator.py` (+58 lines)

- Existing scope-validation tests updated to explicitly set `mock_config.jwt_skip_scope_check = False` so they continue to exercise the strict path (a `MagicMock` attribute defaults to a truthy `Mock`, which would otherwise silently enable the bypass).
- Two new tests cover the bypass: one for a token with no `scope` claim (ID token shape), one confirming an out-of-allowlist scope is also ignored when the flag is on.

## Fix: `ContextLogger` duplicate `exc_info`

Pre-existing bug surfaced when the streaming error path attempted to log traces during a 4xx from Bedrock.

### `backend/app/observability/context_logger.py` (+11 lines)

- `_log_with_caller_info` now pops `exc_info` and `stack_info` out of `**kwargs` before calling `Logger.makeRecord`. The previous code passed `None` positionally to `makeRecord` AND unpacked `**kwargs` on top, causing `TypeError: got multiple values for argument 'exc_info'` when callers used `logger.error(msg, exc_info=True)`.
- `stack_info` is applied to the returned record directly, matching Python's `Logger._log` behaviour, because `Logger.makeRecord` does not accept it as a keyword.

### `test/unit/observability/test_observability_context_logger.py` (+39 lines)

- Existing test that asserted `stack_info` passes through as a kwarg is updated to reflect the correct behaviour: `stack_info` is applied to the record, not to `makeRecord`'s kwargs.
- New regression test `test_log_error_with_exc_info_true` locks in that `logger.error(msg, exc_info=True)` no longer raises `TypeError`.

## Fix: `httpx.ResponseNotRead` when logging Bedrock streaming errors

Pre-existing bug that turned any non-2xx from Bedrock into a confusing stack trace instead of a clean error message to the client.

### `backend/app/routes/bedrock_routes.py` (+104 lines, -~36)

- `async_stream_generator` in both `converse_stream_httpx` and `invoke_stream_httpx` used to call `resp.raise_for_status()` inside `async with stream_cm as resp:` and then read `e.response.text[:200]` in the outer `except`. That access failed with `httpx.ResponseNotRead` because the `async with` had already closed the response.
- Both generators now inspect `resp.status_code` inside the `async with` block. On non-2xx status, `await resp.aread()` runs while the connection is still open, decodes the first 200 bytes for logging, and yields a `create_aws_error_json(...)` error to the client. The outer `except httpx.HTTPStatusError` branch is retained as defence-in-depth but is no longer the primary error path.
- Both streaming generators now propagate the actual Bedrock error message (e.g. `ValidationException: model not found`) into the log line and the error response, instead of the previous `<unable to read body: HTTPStatusError>` fallback.

## Test infrastructure

### `test/unit/middleware/test_middleware_rate_limit.py` (+291 lines, -~120)

- Two module-level helpers `_make_non_stream_request` and `_make_non_stream_response` shape a `Request` mock and a `_StreamingResponse`-like mock (only `body_iterator`, no `body`) so tests match real runtime shape.
- Rewrote four `_update_tokens` tests (`unlimited_tpm`, `limited_tpm`, `redis_failure`, `non_redis_exception`) around the new URL-routed non-streaming path.
- Two rewritten JSON-decode-error tests use the buffered-body helpers and assert the guard short-circuits before `extract` and `record_tokens_consumed` are called.
- Two new URL-routing regression tests: streaming URL dispatches to `_reconcile_stream`; non-streaming URL dispatches to `_reconcile_non_stream`.
- New body-replay regression test: after `_reconcile_non_stream` runs, `response.body_iterator` yields the same bytes that were buffered.
- New signed-delta regression test: `check_and_consume` is called with `aggregated - estimated`, not `aggregated`, so the pre-request estimate is not double-counted.

### `pyproject.toml` (+1 line) and `uv.lock` (+49 lines)

- Add `hypothesis` to `[dependency-groups.dev]`. Enables the property-based tests in the streaming spec (`test_tokens.py`, `test_eventstream_parser.py`, `test_stream_reconciler.py` when those optional test tasks are implemented).

## Documentation

### `docs/gateway/03-architecture/06-rate-limit-synchronous-responses.md` (new)

Architecture doc for the non-streaming reconciler. Describes the URL-based routing, `body_iterator` buffering, signed delta semantics, error isolation layers, and observability signals. Appendix walks a fresh branch through the implementation step by step.

### `docs/gateway/03-architecture/07-rate-limit-stream-responses.md` (new)

Architecture doc for the streaming reconciler. Includes a sequence diagram, an explanation of Starlette's response lifecycle, the yield-before-parse discipline, the three isolation layers, EventStream framing details, and observability signals. Appendix mirrors the 06 structure for the streaming implementation.

### `docs/gateway/03-architecture/README.md` (+3 lines)

- Add links to 06 and 07 in the architecture index.

### `docs/gateway/bugs/BUG-2026-07-non-stream-reconciliation.md` (new)

Bug report describing the pre-existing non-streaming reconciliation gap. Explains root cause (Starlette's `_StreamingResponse` wrapper), why the bug went undetected (interaction with the Valkey cluster-client mismatch in local dev), production impact assessment, and how the fix in 06 addresses it.

## Files not changed but worth calling out

- `infrastructure/**`. No infrastructure changes. Production continues to run against `aws_elasticache_serverless_cache` with the same `VALKEY_URL` and IAM authentication env vars. `VALKEY_CLUSTER_MODE` is not set, so the code inherits the safe cluster-mode default.
- `backend/app/core/rate_limit/limiter.py`. `RateLimiter.check_and_consume` and `check_and_consume_all` are unchanged. Both reconcilers use the existing signed `INCRBY`-backed Lua script.
- `backend/app/core/rate_limit/tokens.py`. `TokenCounter.calculate_aggregated_tokens` and `extract` are unchanged. Both reconcilers reuse the existing aggregation formula and burndown rates.
- `backend/app/routes/bedrock_routes.py::converse_stream_httpx` and `invoke_stream_httpx`. The route handlers are unchanged apart from the streaming-error logging fix noted above. Reconciliation is installed by the middleware at response-return time.

## Test suite

Before this branch: 399 unit tests.

After this branch: 438 unit tests. All pass.

New tests added by this branch:

- Two JWT scope-bypass tests in `test_auth_jwt_validator.py`.
- One `exc_info` regression test in `test_observability_context_logger.py`.
- Four middleware regression tests in `test_middleware_rate_limit.py` (streaming URL routing, non-streaming URL routing, body replay, signed delta).
