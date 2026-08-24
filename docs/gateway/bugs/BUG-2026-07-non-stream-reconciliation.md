# Bug report: non-streaming TPM reconciliation never runs behind `BaseHTTPMiddleware`

- Status: resolved. Fix landed under [`03-architecture/06-rate-limit-synchronous-responses.md`](../03-architecture/06-rate-limit-synchronous-responses.md).
- Severity: high. Silently under-charges TPM for every `/converse` and `/invoke` request.
- Component: `backend/app/middleware/rate_limit.py::_update_tokens`.
- Environment: all (dev, test, prod).
- Discovered: 2026-07-30 during local verification of the streaming TPM reconciliation feature.

## Summary

For non-streaming Bedrock endpoints (`/model/{id}/converse`, `/model/{id}/invoke`), the rate-limit middleware wrote only the pre-request estimated input tokens to the Shared_TPM_Key counter. The actual aggregated token count (input + output * burndown + cache-write) reported by Bedrock in the response body was never reconciled into Redis. A single request that Bedrock reported as `totalTokens=177` charged only `~11` tokens against the client quota, an approximately 93 percent under-count.

## Symptom

Three requests against the same client-model combination, TPM limit set to 50,000:

```
request 1 -> x-ratelimit-used-tpm: 11    (Bedrock reports totalTokens=177)
request 2 -> x-ratelimit-used-tpm: 22    (Bedrock reports totalTokens=182)
request 3 -> x-ratelimit-used-tpm: 33    (Bedrock reports totalTokens=177)
```

`used-tpm` grew by exactly the pre-request estimate (`~11`) each request, never by the aggregated total (`~177`). Expected `used-tpm` after 3 requests: approximately 536. Observed: 33.

## Root cause

`RateLimitMiddleware` inherits from `starlette.middleware.base.BaseHTTPMiddleware`. Starlette's `BaseHTTPMiddleware.call_next` wraps every downstream response, streaming and non-streaming alike, in an internal `starlette.middleware.base._StreamingResponse` object. That wrapper class inherits from `starlette.responses.StreamingResponse` and exposes the body only through `response.body_iterator`; `response.body` is never set.

`_update_tokens` used this early-return:

```python
if isinstance(response, StreamingResponse) or not (hasattr(response, "body") and response.body):
    return
```

For **every** response (streaming or non-streaming) reaching this branch:

- `isinstance(response, StreamingResponse)` returned **`True`**. `_StreamingResponse` inherits from `StreamingResponse`. Verified: `issubclass(_StreamingResponse, StreamingResponse) == True` on the installed Starlette version.
- The `or` short-circuited immediately.
- The function returned without reaching any reconciliation logic.

The second condition (`hasattr(response, "body")`) was never evaluated but would also have caused the early return: `_StreamingResponse.__init__` never sets `body`, only `body_iterator`.

Consequence: the code path that reads `usage.total_tokens` from the response body and calls `RateLimiter.check_and_consume` on the Shared_TPM_Key was **unreachable for all response types** — both streaming and non-streaming — in every environment.

The client-visible response body still reached callers because `BaseHTTPMiddleware.__call__` iterates `body_iterator` after `dispatch` returns:

```python
response = await self.dispatch_func(request, call_next)   # _update_tokens ran here
await response(scope, wrapped_receive, send)              # body_iterator consumed here
```

Between these two lines, the response object held an unconsumed async generator. The middleware's view of the response and the client's eventual view of the response were two disjoint snapshots of the same object.

## Why this went undetected

Two independent bugs interacted to mask the problem:

1. **This bug.** Token reconciliation (both streaming and non-streaming) never ran because the `isinstance(response, StreamingResponse)` check unconditionally short-circuited `_update_tokens`. The counter only grew by the pre-request estimate, which appeared to be "working" — it just appeared to work slowly.
2. **A separate bug in the Valkey client factory.** Local dev used `redis:latest` (standalone), but the client factory hardcoded `GlideClusterClient`. The cluster client could not discover a topology on the standalone Redis and silently failed every command. Both the pre-request `check_and_consume_all` write and the missing post-response reconciliation write were dropped. The counter always read `nil`. There was no observable gap between "estimate landed" and "aggregated should have landed" for a local operator to notice.

In production against ElastiCache Serverless Valkey (which speaks cluster protocol), the pre-request write did land. The counter grew each request, but only by the estimate. The under-count would show up as steady linear TPM growth with no jumps for large responses. Only cross-checking against Bedrock's own usage metrics would reveal the discrepancy. No existing dashboard performed that cross-check.

## Impact

- Clients could consume up to approximately 15x their configured TPM budget without the shared counter noticing. The aggregated-to-estimate ratio for typical Bedrock responses ranges from 5x (short completion) to 30x or more (long completion with reasoning tokens).
- The `x-ratelimit-used-tpm` header the gateway returned to callers was not a faithful representation of real usage.
- Downstream analytics that consumed the `rate_limit_tokens_consumed_total` counter emitted by `record_tokens_consumed` missed non-streaming aggregated tokens, because that helper was called from the same unreachable branch.

## Scope

Both the streaming path (`/converse-stream`, `/invoke-with-response-stream`) and the non-streaming path (`/converse`, `/invoke`) were affected by the same bug. Since `_StreamingResponse` inherits from `StreamingResponse`, the `isinstance` check returned `True` for every response, making the entire `_update_tokens` body unreachable regardless of endpoint type. The [streaming-tpm-reconciliation](../../.kiro/specs/streaming-tpm-reconciliation) feature landed a URL-based routing fix on 2026-07-30 which correctly dispatches streaming responses through the `StreamTokenReconciler` and non-streaming responses through `_reconcile_non_stream`. The key insight: route by URL path (`_detect_stream_endpoint`), not by response type.

## Fix

See [`03-architecture/06-rate-limit-synchronous-responses.md`](../03-architecture/06-rate-limit-synchronous-responses.md) for the design and implementation walkthrough. Summary:

1. Detect streaming vs non-streaming by URL path (`_detect_stream_endpoint`), not by response type. Every `BaseHTTPMiddleware`-wrapped response has `body_iterator` set.
2. For non-streaming responses, drain `body_iterator` into a buffer, parse the JSON body, run the existing `TokenCounter.extract` and `RateLimiter.check_and_consume` logic, then replace `body_iterator` with a single-shot yield of the buffered bytes so the client still receives the response.

## Verification

After the fix, three requests against `us.amazon.nova-lite-v1:0` with prompt "Hi" (input=14, output around 163) produce:

- `x-ratelimit-used-tpm` on the third response header approximately `2 x 177 = 354`. The header reflects state at admission, which reflects the previous two reconciliations.
- Final Shared_TPM_Key value approximately `3 x 177 = 531`.
- One `rate_limit_reconciled` log line per non-streaming request with `aggregated_tokens`, `estimated_tokens`, `reconciliation_delta` fields. Mirrors the `stream_reconciliation_applied` event for streaming.

## Regression prevention

- Unit test that asserts `_update_tokens` reads the body from `body_iterator` (not `body`) when the response is a `_StreamingResponse`-shaped mock.
- Unit test that asserts the non-streaming reconciler is invoked exactly once with the signed aggregated delta.
- The 2026-07-30 duck-typing regression test in `test_middleware_rate_limit.py` covers the isinstance vs URL-routing distinction for the streaming path.

## Related

- [streaming-tpm-reconciliation](../../.kiro/specs/streaming-tpm-reconciliation). The streaming counterpart, already resolved.
- [`03-architecture/06-rate-limit-synchronous-responses.md`](../03-architecture/06-rate-limit-synchronous-responses.md). Architecture doc for the non-streaming reconciler.
- [`03-architecture/07-rate-limit-stream-responses.md`](../03-architecture/07-rate-limit-stream-responses.md). Architecture doc for the streaming path.
