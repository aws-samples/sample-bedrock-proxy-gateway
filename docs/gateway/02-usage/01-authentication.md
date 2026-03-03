# Authentication

Get OAuth access tokens to authenticate with the gateway.

All requests to the gateway require OAuth 2.0 authentication using Bearer tokens in the Authorization header.

## How authentication works

The gateway uses OAuth 2.0 with JWT tokens:

1. Your application requests an access token from your OAuth provider
2. The OAuth provider validates your credentials and returns a JWT token
3. Your application includes the token in the Authorization header
4. The gateway validates the token signature and claims
5. If valid, the gateway processes your request

## Get an access token

Use the OAuth 2.0 client credentials flow to get a token.

### Auth0 example

```bash
curl -X POST https://<tenant>.us.auth0.com/oauth/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=client_credentials" \
  -d "client_id=<CLIENT_ID>" \
  -d "client_secret=<CLIENT_SECRET>" \
  -d "audience=bedrockproxygateway"
```

Response:

```json
{
  "access_token": "eyJraWQiOiJ...",
  "expires_in": 86400,
  "token_type": "Bearer"
}
```

### Other OAuth providers

The exact request format varies by provider. Check your provider's documentation for the client credentials flow.

**Okta:**

```bash
curl -X POST https://<domain>.okta.com/oauth2/default/v1/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=client_credentials" \
  -d "client_id=<CLIENT_ID>" \
  -d "client_secret=<CLIENT_SECRET>" \
  -d "scope=<SCOPES>"
```

**Azure Active Directory:**

```bash
curl -X POST https://login.microsoftonline.com/<tenant-id>/oauth2/v2.0/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=client_credentials" \
  -d "client_id=<CLIENT_ID>" \
  -d "client_secret=<CLIENT_SECRET>" \
  -d "scope=<SCOPE>"
```

## Use the token

Include the token in the Authorization header:

```bash
curl -X POST https://<gateway-url>/model/anthropic.claude-3-5-sonnet-20241022-v2:0/converse \
  -H "Authorization: Bearer eyJraWQiOiJ..." \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": [{"text": "Hello"}]}
    ]
  }'
```

## Token validation

The gateway validates your token by checking:

1. **Signature** - Verifies the token was signed by your OAuth provider
2. **Expiration** - Ensures the token has not expired
3. **Issuer** - Confirms the token came from the configured OAuth provider
4. **Audience** - Verifies the token is intended for this gateway
5. **Scopes** - Checks the token has required permissions

If validation fails, you receive a 403 error.

## Required scopes

Your token must include at least one of these scopes:

- `bedrockproxygateway:invoke` - Invoke Amazon Bedrock models
- `bedrockproxygateway:read` - Read-only access (health checks)
- `bedrockproxygateway:admin` - Administrative operations

The exact scope names depend on your OAuth provider configuration.

## Token expiration

Access tokens typically expire after 1 hour (check the `expires_in` field).

### Handle expiration

Your application should:

1. Cache the access token
2. Track when it expires
3. Request a new token before expiration
4. Retry requests with a new token if you get a 403 error

### Example in Python

```python
import requests
import time

class TokenManager:
    def __init__(self, token_url, client_id, client_secret):
        self.token_url = token_url
        self.client_id = client_id
        self.client_secret = client_secret
        self.token = None
        self.expires_at = 0

    def get_token(self):
        # Return cached token if still valid
        if self.token and time.time() < self.expires_at - 60:
            return self.token

        # Request new token
        response = requests.post(
            self.token_url,
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "audience": "bedrockproxygateway"
            }
        )

        data = response.json()
        self.token = data["access_token"]
        self.expires_at = time.time() + data["expires_in"]

        return self.token
```

## Mutual TLS (optional)

If mTLS is configured, you must also provide a client certificate.

### Use mTLS

```bash
curl -X POST https://<gateway-url>/model/anthropic.claude-3-5-sonnet-20241022-v2:0/converse \
  -H "Authorization: Bearer eyJraWQiOiJ..." \
  -H "Content-Type: application/json" \
  --cert client-cert.pem \
  --key client-key.pem \
  -d '{
    "messages": [
      {"role": "user", "content": [{"text": "Hello"}]}
    ]
  }'
```

With mTLS enabled:

- The ALB validates your certificate before forwarding the request
- Your certificate must be signed by the configured CA
- Both the certificate and OAuth token are required

For mTLS setup, refer to [Advanced Configuration](../01-setup/07-advanced.md#mutual-tls-mtls).

## Error responses

### Missing token

```json
{
  "__type": "AccessDenied",
  "message": "Invalid Token"
}
```

HTTP Status: 403

**Solution:** Include the Authorization header with a valid token.

### Invalid or expired token

```json
{
  "__type": "AccessDenied",
  "message": "Invalid Token"
}
```

HTTP Status: 403

**Solution:** Request a new token from your OAuth provider.

### Missing required scope

```json
{
  "__type": "AccessDenied",
  "message": "Insufficient permissions"
}
```

HTTP Status: 403

**Solution:** Ensure your OAuth client is authorized for the required scopes.

## Next steps

- Learn about making requests in [Making Requests](02-making-requests.md)
- See code examples in [Code Examples](03-code-examples.md)
- Configure OAuth providers in [OAuth Configuration](../01-setup/03-oauth.md)
- Monitor token usage
- Set up alerts for authentication failures

## Troubleshooting

### Cannot get token

**Check:**

- Client ID and secret are correct
- Token URL is correct
- Client is authorized for the required scopes
- Network connectivity to OAuth provider

### Token validation fails

**Check:**

- Token has not expired
- `OAUTH_ISSUER` matches token issuer
- `JWT_AUDIENCE` matches token audience
- Token includes required scopes

For more help, refer to [TROUBLESHOOTING.md](../TROUBLESHOOTING.md#authentication-issues).

## Next steps

- Learn about making requests in [Making Requests](02-making-requests.md)
- See code examples in [Code Examples](03-code-examples.md)
- Configure OAuth providers in [OAuth Configuration](../01-setup/03-oauth.md)
