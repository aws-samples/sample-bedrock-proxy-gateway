# Unit Tests for Bedrock Gateway

This directory contains comprehensive unit tests for the Bedrock Gateway application, targeting 80% code coverage.

## Test Structure

### Core Modules

- `test_config.py` - Configuration management tests
- `test_main.py` - Application initialization tests

### Authentication & Security

- `test_auth_jwks.py` - JWKS key management and caching
- `test_auth_jwt_validator.py` - JWT token validation and claims processing
- `test_middleware_auth.py` - Authentication middleware functionality

### Caching & Storage

- `test_cache_sts_credential_cache.py` - STS credential caching operations
- `test_cache_valkey_client.py` - Valkey client management and connection handling

### Observability & Monitoring

- `test_observability_logging_filter.py` - Context-aware logging filters
- `test_observability_context_logger.py` - Logger wrapper with caller info preservation
- `test_observability_metrics.py` - Metrics collection and business intelligence
- `test_observability_telemetry.py` - OpenTelemetry setup and instrumentation

### API Routes & Handlers

- `test_routes_health.py` - Health check endpoint functionality
- `test_routes_general_routes.py` - General API routes and responses

### Services & Utilities

- `test_services_aws_client_factory.py` - AWS client creation and credential management
- `test_util_exception_handler.py` - Global exception handling

### Mock & Testing Infrastructure

- `test_mock_synthetic_data.py` - Synthetic data generation for load testing

## Test Coverage Goals

The test suite aims for 80% code coverage across all modules, focusing on:

- **Business Logic**: Core functionality and edge cases
- **Error Handling**: Exception scenarios and graceful degradation
- **Integration Points**: External service interactions and mocking
- **Security**: Authentication, authorization, and input validation
- **Performance**: Caching mechanisms and resource management

## Running Tests

### Quick Test Run

```bash
cd /path/to/bedrock-proxy-gateway/test/unit
./run_tests.sh
```

### Manual Test Execution

```bash
cd /path/to/bedrock-proxy-gateway/backend/app
uv sync --extra test
uv run pytest ../../test/unit/ --cov=. --cov-report=html --cov-fail-under=80
```

### Coverage Report

After running tests, view the HTML coverage report:

```bash
open test/unit/htmlcov/index.html
```

## Test Configuration

- **pytest.ini**: Test discovery and coverage configuration
- **conftest.py**: Shared fixtures and test setup
- **run_tests.sh**: Automated test execution script

## Key Testing Patterns

### Async Testing

```python
@pytest.mark.asyncio
async def test_async_function():
    result = await async_function()
    assert result is not None
```

### Mocking External Dependencies

```python
@patch("module.external_dependency")
def test_with_mock(mock_dependency):
    mock_dependency.return_value = "expected_value"
    result = function_under_test()
    assert result == "expected_result"
```

### Context Variable Testing

```python
def test_context_isolation():
    set_user_context("user1", "org1")
    assert user_id_context.get() == "user1"
    clear_user_context()
    assert user_id_context.get() is None
```

## Coverage Exclusions

The following are intentionally excluded from coverage requirements:

- Import statements and module-level constants
- Exception handling for truly exceptional cases
- Development/debugging code paths
- External library integration points that cannot be easily mocked

## Continuous Integration

These tests are designed to run in CI/CD pipelines with:

- Fail-fast on coverage below 80%
- Detailed coverage reporting
- Async test support
- Mock isolation between tests
