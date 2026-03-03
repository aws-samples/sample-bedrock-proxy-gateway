# Code examples

Python code examples for using the gateway.

## Basic request with requests library

```python
import requests

# Configuration
GATEWAY_URL = "https://your-gateway-url.com"
TOKEN = "your-oauth-token"

# Make request
response = requests.post(
    f"{GATEWAY_URL}/model/anthropic.claude-3-5-sonnet-20241022-v2:0/converse",
    headers={
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json"
    },
    json={
        "messages": [
            {
                "role": "user",
                "content": [{"text": "What is Amazon Bedrock?"}]
            }
        ],
        "inferenceConfig": {
            "maxTokens": 500,
            "temperature": 0.7
        }
    }
)

# Handle response
if response.status_code == 200:
    data = response.json()
    message = data["output"]["message"]["content"][0]["text"]
    print(f"Response: {message}")
    print(f"Tokens used: {data['usage']['totalTokens']}")
else:
    print(f"Error: {response.status_code}")
    print(response.json())
```

## Token management

```python
import requests
import time
from typing import Optional

class TokenManager:
    """Manages OAuth token lifecycle with automatic refresh."""

    def __init__(self, token_url: str, client_id: str, client_secret: str, audience: str):
        self.token_url = token_url
        self.client_id = client_id
        self.client_secret = client_secret
        self.audience = audience
        self.token: Optional[str] = None
        self.expires_at: float = 0

    def get_token(self) -> str:
        """Get valid token, refreshing if necessary."""
        # Return cached token if still valid (with 60s buffer)
        if self.token and time.time() < self.expires_at - 60:
            return self.token

        # Request new token
        response = requests.post(
            self.token_url,
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "audience": self.audience
            }
        )
        response.raise_for_status()

        data = response.json()
        self.token = data["access_token"]
        self.expires_at = time.time() + data["expires_in"]

        return self.token

# Usage
token_manager = TokenManager(
    token_url="https://your-tenant.us.auth0.com/oauth/token",
    client_id="your-client-id",
    client_secret="your-client-secret",
    audience="bedrockproxygateway"
)

token = token_manager.get_token()
```

## Gateway client class

```python
import requests
from typing import Dict, List, Optional

class BedrockGatewayClient:
    """Client for interacting with the Bedrock Gateway."""

    def __init__(self, gateway_url: str, token_manager: TokenManager):
        self.gateway_url = gateway_url.rstrip("/")
        self.token_manager = token_manager

    def converse(
        self,
        model_id: str,
        messages: List[Dict],
        max_tokens: int = 500,
        temperature: float = 0.7
    ) -> Dict:
        """Send a conversation request to a model."""
        response = requests.post(
            f"{self.gateway_url}/model/{model_id}/converse",
            headers={
                "Authorization": f"Bearer {self.token_manager.get_token()}",
                "Content-Type": "application/json"
            },
            json={
                "messages": messages,
                "inferenceConfig": {
                    "maxTokens": max_tokens,
                    "temperature": temperature
                }
            }
        )
        response.raise_for_status()
        return response.json()

    def converse_stream(
        self,
        model_id: str,
        messages: List[Dict],
        max_tokens: int = 500,
        temperature: float = 0.7
    ):
        """Stream a conversation response from a model."""
        response = requests.post(
            f"{self.gateway_url}/model/{model_id}/converse-stream",
            headers={
                "Authorization": f"Bearer {self.token_manager.get_token()}",
                "Content-Type": "application/json"
            },
            json={
                "messages": messages,
                "inferenceConfig": {
                    "maxTokens": max_tokens,
                    "temperature": temperature
                }
            },
            stream=True
        )
        response.raise_for_status()

        # Parse server-sent events
        for line in response.iter_lines():
            if line:
                line = line.decode('utf-8')
                if line.startswith('data: '):
                    yield line[6:]  # Remove 'data: ' prefix

# Usage
client = BedrockGatewayClient(
    gateway_url="https://your-gateway-url.com",
    token_manager=token_manager
)

# Non-streaming request
response = client.converse(
    model_id="anthropic.claude-3-5-sonnet-20241022-v2:0",
    messages=[
        {"role": "user", "content": [{"text": "Hello!"}]}
    ]
)
print(response["output"]["message"]["content"][0]["text"])

# Streaming request
for chunk in client.converse_stream(
    model_id="anthropic.claude-3-5-sonnet-20241022-v2:0",
    messages=[
        {"role": "user", "content": [{"text": "Count to 5"}]}
    ]
):
    print(chunk, end="", flush=True)
```

## Multi-turn conversation

```python
def chat_session(client: BedrockGatewayClient, model_id: str):
    """Interactive chat session with conversation history."""
    messages = []

    print("Chat session started. Type 'quit' to exit.")

    while True:
        # Get user input
        user_input = input("\nYou: ")
        if user_input.lower() == 'quit':
            break

        # Add user message to history
        messages.append({
            "role": "user",
            "content": [{"text": user_input}]
        })

        # Get response
        response = client.converse(
            model_id=model_id,
            messages=messages
        )

        # Extract assistant message
        assistant_message = response["output"]["message"]
        assistant_text = assistant_message["content"][0]["text"]

        # Add assistant message to history
        messages.append(assistant_message)

        # Display response
        print(f"\nAssistant: {assistant_text}")
        print(f"Tokens: {response['usage']['totalTokens']}")

# Usage
chat_session(
    client=client,
    model_id="anthropic.claude-3-5-sonnet-20241022-v2:0"
)
```

## Error handling

```python
import requests
from requests.exceptions import RequestException

def make_request_with_retry(
    client: BedrockGatewayClient,
    model_id: str,
    messages: List[Dict],
    max_retries: int = 3
) -> Optional[Dict]:
    """Make request with automatic retry on rate limits."""
    for attempt in range(max_retries):
        try:
            return client.converse(model_id=model_id, messages=messages)

        except requests.HTTPError as e:
            if e.response.status_code == 429:
                # Rate limit exceeded
                retry_after = int(e.response.headers.get('Retry-After', 60))
                print(f"Rate limited. Retrying in {retry_after}s...")
                time.sleep(retry_after)
            elif e.response.status_code == 403:
                # Token expired, refresh and retry
                print("Token expired. Refreshing...")
                client.token_manager.token = None
            else:
                # Other error, don't retry
                print(f"Error: {e.response.status_code}")
                print(e.response.json())
                return None

        except RequestException as e:
            print(f"Request failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # Exponential backoff
            else:
                return None

    return None
```

## Using boto3

```python
import boto3
import json

# Create Bedrock client pointing to gateway
bedrock = boto3.client(
    'bedrock-runtime',
    endpoint_url='https://your-gateway-url.com',
    region_name='us-east-1'
)

# Add OAuth token to requests
def add_auth_header(event_name, **kwargs):
    if 'headers' not in kwargs['request']:
        kwargs['request'].headers = {}
    kwargs['request'].headers['Authorization'] = f'Bearer {token_manager.get_token()}'

bedrock.meta.events.register('before-call', add_auth_header)

# Make request
response = bedrock.converse(
    modelId='anthropic.claude-3-5-sonnet-20241022-v2:0',
    messages=[
        {
            'role': 'user',
            'content': [{'text': 'Hello!'}]
        }
    ]
)

print(response['output']['message']['content'][0]['text'])
```

## Streaming with boto3

```python
# Stream response
response = bedrock.converse_stream(
    modelId='anthropic.claude-3-5-sonnet-20241022-v2:0',
    messages=[
        {
            'role': 'user',
            'content': [{'text': 'Count to 5'}]
        }
    ]
)

# Process stream
for event in response['stream']:
    if 'contentBlockDelta' in event:
        delta = event['contentBlockDelta']['delta']
        if 'text' in delta:
            print(delta['text'], end='', flush=True)
```

## Rate limit monitoring

```python
def make_request_with_monitoring(
    client: BedrockGatewayClient,
    model_id: str,
    messages: List[Dict]
) -> Dict:
    """Make request and monitor rate limits."""
    response = requests.post(
        f"{client.gateway_url}/model/{model_id}/converse",
        headers={
            "Authorization": f"Bearer {client.token_manager.get_token()}",
            "Content-Type": "application/json"
        },
        json={"messages": messages}
    )

    # Check rate limit headers
    if 'X-RateLimit-Remaining' in response.headers:
        remaining = int(response.headers['X-RateLimit-Remaining'])
        limit = int(response.headers['X-RateLimit-Limit'])
        utilization = ((limit - remaining) / limit) * 100

        print(f"Rate limit: {remaining}/{limit} ({utilization:.1f}% used)")

        # Warn if approaching limit
        if utilization > 80:
            print("Warning: Approaching rate limit!")

    response.raise_for_status()
    return response.json()
```

## Complete example

```python
import requests
import time
from typing import Dict, List, Optional

# Token manager
class TokenManager:
    def __init__(self, token_url: str, client_id: str, client_secret: str, audience: str):
        self.token_url = token_url
        self.client_id = client_id
        self.client_secret = client_secret
        self.audience = audience
        self.token: Optional[str] = None
        self.expires_at: float = 0

    def get_token(self) -> str:
        if self.token and time.time() < self.expires_at - 60:
            return self.token

        response = requests.post(
            self.token_url,
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "audience": self.audience
            }
        )
        response.raise_for_status()

        data = response.json()
        self.token = data["access_token"]
        self.expires_at = time.time() + data["expires_in"]

        return self.token

# Gateway client
class BedrockGatewayClient:
    def __init__(self, gateway_url: str, token_manager: TokenManager):
        self.gateway_url = gateway_url.rstrip("/")
        self.token_manager = token_manager

    def converse(self, model_id: str, messages: List[Dict], **kwargs) -> Dict:
        response = requests.post(
            f"{self.gateway_url}/model/{model_id}/converse",
            headers={
                "Authorization": f"Bearer {self.token_manager.get_token()}",
                "Content-Type": "application/json"
            },
            json={"messages": messages, "inferenceConfig": kwargs}
        )
        response.raise_for_status()
        return response.json()

# Main
if __name__ == "__main__":
    # Initialize
    token_manager = TokenManager(
        token_url="https://your-tenant.us.auth0.com/oauth/token",
        client_id="your-client-id",
        client_secret="your-client-secret",
        audience="bedrockproxygateway"
    )

    client = BedrockGatewayClient(
        gateway_url="https://your-gateway-url.com",
        token_manager=token_manager
    )

    # Make request
    response = client.converse(
        model_id="anthropic.claude-3-5-sonnet-20241022-v2:0",
        messages=[
            {"role": "user", "content": [{"text": "What is Amazon Bedrock?"}]}
        ],
        maxTokens=500,
        temperature=0.7
    )

    # Print response
    print(response["output"]["message"]["content"][0]["text"])
    print(f"\nTokens used: {response['usage']['totalTokens']}")
```

## Jupyter notebook examples

For interactive examples and advanced use cases, refer to the Jupyter notebooks in the [examples/](../../../examples/) directory:

| Notebook | Description |
|----------|-------------|
| [00_onboarding.ipynb](../../../examples/00_onboarding.ipynb) | Getting started with the gateway |
| [01_fundamentals.ipynb](../../../examples/01_fundamentals.ipynb) | Basic API usage and patterns |
| [03_embedding.ipynb](../../../examples/03_embedding.ipynb) | Using embedding models |
| [04_rag.ipynb](../../../examples/04_rag.ipynb) | Retrieval-Augmented Generation (RAG) |
| [05_thinking_and_tools.ipynb](../../../examples/05_thinking_and_tools.ipynb) | Extended thinking and tool use |
| [06_image_gen.ipynb](../../../examples/06_image_gen.ipynb) | Image generation with Stable Diffusion |
| [06_rate_limit.ipynb](../../../examples/06_rate_limit.ipynb) | Rate limiting behavior and testing |
| [07_guardrail.ipynb](../../../examples/07_guardrail.ipynb) | Using Amazon Bedrock Guardrails |
| [08_operations.ipynb](../../../examples/08_operations.ipynb) | Monitoring and operational patterns |

These notebooks provide hands-on examples for common use cases with the gateway.

## Next steps

- Learn about authentication in [Authentication](01-authentication.md)
- See API details in [Making Requests](02-making-requests.md)
- Configure rate limiting in [Rate Limiting](../01-setup/04-rate-limiting.md)
