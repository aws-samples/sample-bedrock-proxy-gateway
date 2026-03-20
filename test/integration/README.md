# Bedrock Gateway Integration Tests

Comprehensive integration tests for all Bedrock models and APIs in Python and Java.

## Structure

```
repo-root/
├── .env.template                # Environment configuration template
├── .env.dev                     # Your dev environment config (gitignored)
├── client_cert.pem              # mTLS certificate (optional, gitignored)
├── client_key.pem               # mTLS private key (optional, gitignored)
└── test/integration/
    ├── config.json              # Model configuration
    ├── python/                  # Python tests
    │   ├── main.py              # Main test runner
    │   └── bedrock_client.py    # Gateway authentication client
    ├── java/                    # Java tests
    │   ├── src/main/java/
    │   │   ├── BedrockTester.java   # Main test runner
    │   │   └── BedrockClient.java   # Gateway authentication client
    │   ├── pom.xml              # Maven dependencies
    │   └── client.p12           # PKCS12 keystore (generated)
    ├── results/                 # Test results (timestamped)
    ├── run_python_tests.sh      # Python test runner script
    ├── run_java_tests.sh        # Java test runner script
    └── README.md
```

## Tested Models

### Python Tests

- Anthropic Claude Sonnet 4
- Amazon Nova Lite
- Meta Llama 3 8B
- Amazon Titan Embed Text v1

### Java Tests

- Amazon Nova Lite (inference)
- Amazon Titan Embed Text v1 (embedding)

## Tested APIs

- Converse
- Converse Stream
- InvokeModel
- InvokeModelWithResponseStream

## Framework Integrations

- **Langchain**: Tests ChatBedrock integration with custom Bedrock client
- **Langgraph**: Tests graph-based workflows using Langchain + Langgraph
- **Strands**: Tests agent-based workflows
- **LiteLLM**: Tests LiteLLM proxy integration with Bedrock models
- **Spring AI**: Tests Spring AI Bedrock integration with gateway-authenticated Bedrock client (Java)

## Prerequisites

### Certificate Files

Create required certificate files in the **repository root** directory (only if mTLS is enabled):

- `client_cert.pem` (Client certificate for mTLS authentication)
- `client_key.pem` (Private key for mTLS authentication)

### Environment Configuration

Copy `.env.template` to create an environment-specific file at the **repository root**:

```bash
cp .env.template .env.dev
# Edit .env.dev with your environment values:
#   AWS_PROFILE, AWS_REGION, GATEWAY_API_URL, GATEWAY_SECRET_ID
```

The `GATEWAY_SECRET_ID` must reference a Secrets Manager secret containing:
`client_id`, `client_secret`, `token_url`, `audience`

## Running Tests

### Python Only

```bash
./run_python_tests.sh
```

### Java Only

One-time setup:

```bash
cd test/integration/java
openssl pkcs12 -export -in ../../../client_cert.pem -inkey ../../../client_key.pem -out client.p12 -name "client" -passout pass:
cd ../../..
```

Run the test:

```bash
./run_java_tests.sh
```

## TeamCity Integration

The pipeline automatically runs after shared account deployment for dev, qa, and preprod environments. It:

1. Triggers after successful shared account deployment
2. Runs both Python and Java test suites
3. Collects and publishes results
4. Fails the build if any tests fail

## Test Results

Tests generate detailed reports showing:

- Success/failure status for each model and API
- Framework integration test results
- Error messages for failures
- Summary statistics
- Comprehensive markdown reports (Python)

## Framework Dependencies

The tests verify gateway compatibility with popular AI frameworks:

### Python

- `langchain-aws`: LangChain Bedrock integration
- `langgraph`: Graph-based workflow framework
- `litellm`: Universal LLM proxy library
- `strands`: Agent-based workflow framework

### Java

- Spring AI Bedrock Converse (1.0.0-M5)
