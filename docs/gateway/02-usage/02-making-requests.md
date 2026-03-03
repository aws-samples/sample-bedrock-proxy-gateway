# Making requests

Make requests to Amazon Bedrock through the gateway.

The gateway provides a transparent proxy to Amazon Bedrock. Request and response formats match the Bedrock API exactly.

## Base URL

```
https://<gateway-url>
```

Replace `<gateway-url>` with your ALB DNS name or custom domain.

## Endpoints

### Converse API (recommended)

Unified interface for all models.

**Converse:**

```
POST /model/{model_id}/converse
```

**Converse Stream:**

```
POST /model/{model_id}/converse-stream
```

### Invoke API

Legacy API with model-specific formats.

**Invoke Model:**

```
POST /model/{model_id}/invoke
```

**Invoke with Response Stream:**

```
POST /model/{model_id}/invoke-with-response-stream
```

### Health and monitoring

**Health Check:**

```
GET /health
```

**Valkey Health:**

```
GET /health/valkey
```

## Basic request

```bash
curl -X POST https://<gateway-url>/model/anthropic.claude-3-5-sonnet-20241022-v2:0/converse \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {
        "role": "user",
        "content": [{"text": "What is Amazon Bedrock?"}]
      }
    ]
  }'
```

Response:

```json
{
  "output": {
    "message": {
      "role": "assistant",
      "content": [
        {"text": "Amazon Bedrock is a fully managed service..."}
      ]
    }
  },
  "usage": {
    "inputTokens": 15,
    "outputTokens": 87,
    "totalTokens": 102
  },
  "stopReason": "end_turn"
}
```

## Streaming requests

Stream responses in real-time using server-sent events.

```bash
curl -N -X POST https://<gateway-url>/model/anthropic.claude-3-5-sonnet-20241022-v2:0/converse-stream \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": [{"text": "Count to 5"}]}
    ]
  }'
```

Response (server-sent events):

```
event: messageStart
data: {"role":"assistant"}

event: contentBlockDelta
data: {"delta":{"text":"1"}}

event: contentBlockDelta
data: {"delta":{"text":", 2"}}

event: contentBlockDelta
data: {"delta":{"text":", 3"}}

event: messageStop
data: {"stopReason":"end_turn"}
```

### Streaming benefits

- Lower time-to-first-token
- Better user experience for long responses
- Reduced memory usage
- Real-time feedback

## Different models

### Claude 3.5 Sonnet

```bash
curl -X POST https://<gateway-url>/model/anthropic.claude-3-5-sonnet-20241022-v2:0/converse \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": [{"text": "Explain quantum computing"}]}
    ],
    "inferenceConfig": {
      "maxTokens": 500,
      "temperature": 0.7
    }
  }'
```

### Claude 3 Haiku (faster, cheaper)

```bash
curl -X POST https://<gateway-url>/model/anthropic.claude-3-haiku-20240307-v1:0/converse \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": [{"text": "Quick summary of AI"}]}
    ]
  }'
```

### Amazon Nova

```bash
curl -X POST https://<gateway-url>/model/amazon.nova-pro-v1:0/converse \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": [{"text": "Hello"}]}
    ]
  }'
```

## Multi-turn conversations

Include conversation history:

```bash
curl -X POST https://<gateway-url>/model/anthropic.claude-3-5-sonnet-20241022-v2:0/converse \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {
        "role": "user",
        "content": [{"text": "What is 2+2?"}]
      },
      {
        "role": "assistant",
        "content": [{"text": "2+2 equals 4."}]
      },
      {
        "role": "user",
        "content": [{"text": "What about 3+3?"}]
      }
    ]
  }'
```

## Rate limit headers

The gateway includes rate limit information in response headers:

```bash
curl -i -X POST https://<gateway-url>/model/anthropic.claude-3-5-sonnet-20241022-v2:0/converse \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": [{"text": "Hi"}]}]}'
```

Headers:

```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 99
X-RateLimit-Reset: 1737408000
```

- `X-RateLimit-Limit` - Total quota
- `X-RateLimit-Remaining` - Remaining quota
- `X-RateLimit-Reset` - Unix timestamp when quota resets

## Error responses

### Rate limit exceeded

```json
{
  "__type": "ThrottlingException",
  "message": "Rate limit exceeded"
}
```

HTTP Status: 429

**Solution:** Wait and retry, or increase quota.

### Invalid token

```json
{
  "__type": "AccessDenied",
  "message": "Invalid Token"
}
```

HTTP Status: 403

**Solution:** Get a new access token.

### Model not found

```json
{
  "__type": "ResourceNotFoundException",
  "message": "Model not found"
}
```

HTTP Status: 404

**Solution:** Check model ID and ensure Bedrock access is enabled.

## Supported models

The gateway supports all Amazon Bedrock models:

**Anthropic Claude:**

- `anthropic.claude-3-5-sonnet-20241022-v2:0`
- `anthropic.claude-3-5-haiku-20241022-v1:0`
- `anthropic.claude-3-opus-20240229-v1:0`

**Amazon Nova:**

- `amazon.nova-pro-v1:0`
- `amazon.nova-lite-v1:0`
- `amazon.nova-micro-v1:0`

**Meta Llama:**

- `meta.llama3-2-90b-instruct-v1:0`
- `meta.llama3-1-70b-instruct-v1:0`

**Cross-region inference:**

- `us.anthropic.claude-3-5-sonnet-20241022-v2:0`
- `eu.anthropic.claude-3-5-sonnet-20241022-v2:0`

For the complete list, refer to [Amazon Bedrock model IDs](https://docs.aws.amazon.com/bedrock/latest/userguide/model-ids.html).

## Request format

The gateway accepts the same request format as Amazon Bedrock. No modifications needed.

For Converse API format, refer to [Converse API Reference](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_Converse.html).

## Response format

The gateway returns responses unchanged from Amazon Bedrock. No modifications.

## Troubleshooting

### Connection timeout

**Check:**

- Gateway URL is correct
- Network connectivity
- ALB health checks passing

### High latency

**Check:**

- First request to a model is slower (credential caching)
- Subsequent requests should be faster
- Check CloudWatch metrics for latency

### Streaming not working

**Check:**

- Using `-N` flag with curl
- Client supports server-sent events
- ALB idle timeout is sufficient (default 60s)

For more help, refer to [TROUBLESHOOTING.md](../TROUBLESHOOTING.md).

## Next steps

- See Python examples in [Code Examples](03-code-examples.md)
- Learn about authentication in [Authentication](01-authentication.md)
- Configure rate limiting in [Rate Limiting](../01-setup/04-rate-limiting.md)
