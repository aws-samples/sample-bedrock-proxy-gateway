# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for bedrock_routes1 (httpx) endpoints."""

from unittest.mock import AsyncMock, Mock, patch

import httpx
import orjson
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from routes.bedrock_routes1 import create_bedrock_httpx_router
from services.bedrock_service_httpx import BedrockHttpxService
from starlette.middleware.base import BaseHTTPMiddleware

CREDS = {"AccessKeyId": "AK", "SecretAccessKey": "SK", "SessionToken": "ST"}


@pytest.fixture
def mock_service():
    """Create mock BedrockHttpxService with default return values."""
    svc = Mock(spec=BedrockHttpxService)
    svc.get_credentials = AsyncMock(return_value=CREDS)
    svc.converse = AsyncMock(
        return_value={
            "output": {"message": {"content": [{"text": "hi"}]}},
            "usage": {"inputTokens": 10, "outputTokens": 5},
            "metrics": {"latencyMs": 100},
            "stopReason": "end_turn",
        }
    )
    svc.invoke_model = AsyncMock(return_value=orjson.dumps({"result": "ok"}))
    svc.apply_guardrail = AsyncMock(return_value={"action": "NONE", "outputs": []})
    return svc


@pytest.fixture
def telemetry():
    """Create mock telemetry dict."""
    return {"tracer": Mock(), "meter": Mock(), "logger": Mock()}


@pytest.fixture
def app(mock_service, telemetry):
    """Create test FastAPI app with httpx router."""
    test_app = FastAPI()
    test_app.include_router(create_bedrock_httpx_router(mock_service, telemetry))
    return test_app


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)


def _req(client, url, body=None, **state_overrides):
    """Make a POST request with request.state attributes set via middleware.

    Args:
    ----
        client: TestClient instance
        url: Request URL path
        body: JSON body dict
        **state_overrides: Additional request.state attributes to set
    """
    state = {
        "jwt_claims": {"client_id": "test-client", "sub": "test-sub"},
        "rate_ctx": ("test-client", "model", "123456789012", 1000, "converse"),
        "parsed_body": body,
    }
    state.update(state_overrides)

    class _MW(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            """Set request state for testing."""
            for k, v in state.items():
                setattr(request.state, k, v)
            return await call_next(request)

    app = client.app
    app.add_middleware(_MW)

    with patch(
        "routes.bedrock_routes1.get_parsed_body", new_callable=AsyncMock, return_value=body or {}
    ):
        return TestClient(app).post(url, json=body or {}, headers={"Authorization": "Bearer jwt"})


class TestConverseEndpoint:
    """Test cases for /model/{model_id}/converse."""

    def test_success(self, client, mock_service):
        """Verify successful converse returns 200 with response body."""
        resp = _req(
            client,
            "/model/nova/converse",
            {"messages": [{"role": "user", "content": [{"text": "hi"}]}]},
        )
        assert resp.status_code == 200
        assert resp.json()["output"]["message"]["content"][0]["text"] == "hi"
        mock_service.converse.assert_called_once()

    def test_missing_auth_returns_403(self, client):
        """Verify missing Authorization header returns 403."""
        assert client.post("/model/test/converse", json={}).status_code == 403

    def test_bedrock_error_returns_status(self, client, mock_service):
        """Verify Bedrock HTTP error is forwarded with correct status code."""
        err_resp = Mock(
            status_code=400,
            text="bad",
            json=Mock(return_value={"message": "bad", "__type": "ValidationException"}),
        )
        mock_service.converse = AsyncMock(
            side_effect=httpx.HTTPStatusError("400", request=Mock(), response=err_resp)
        )
        assert _req(client, "/model/test/converse", {"messages": []}).status_code == 400

    def test_internal_error_returns_500(self, client, mock_service):
        """Verify unexpected exception returns 500."""
        mock_service.converse = AsyncMock(side_effect=RuntimeError("boom"))
        assert _req(client, "/model/test/converse", {"messages": []}).status_code == 500


class TestInvokeEndpoint:
    """Test cases for /model/{model_id}/invoke."""

    def test_success(self, client, mock_service):
        """Verify successful invoke returns 200."""
        resp = _req(client, "/model/test/invoke", {"prompt": "hello"})
        assert resp.status_code == 200
        mock_service.invoke_model.assert_called_once()

    def test_with_guardrail(self, client):
        """Verify invoke works with guardrail config in request state."""
        resp = _req(
            client,
            "/model/test/invoke",
            {"prompt": "hello"},
            guardrail_config={"guardrailIdentifier": "g1", "guardrailVersion": "1"},
        )
        assert resp.status_code == 200

    def test_bedrock_403_returns_403(self, client, mock_service):
        """Verify Bedrock 403 is forwarded with descriptive message."""
        err_resp = Mock(
            status_code=403,
            text="",
            json=Mock(return_value={"message": "", "__type": "AccessDeniedException"}),
        )
        mock_service.invoke_model = AsyncMock(
            side_effect=httpx.HTTPStatusError("403", request=Mock(), response=err_resp)
        )
        assert _req(client, "/model/test/invoke", {"prompt": "hi"}).status_code == 403


class TestApplyGuardrailEndpoint:
    """Test cases for /guardrail/{id}/version/{ver}/apply."""

    def test_success(self, client, mock_service):
        """Verify successful apply guardrail returns 200."""
        resp = _req(
            client,
            "/guardrail/baseline/version/1/apply",
            {"content": [{"text": {"text": "test"}}], "source": "INPUT"},
            resolved_guardrail={"guardrailIdentifier": "g-real", "guardrailVersion": "1"},
        )
        assert resp.status_code == 200
        assert resp.json()["action"] == "NONE"
        mock_service.apply_guardrail.assert_called_once()

    def test_not_found_returns_404(self, client):
        """Verify missing resolved_guardrail returns 404."""
        resp = _req(
            client,
            "/guardrail/unknown/version/1/apply",
            {"content": [], "source": "INPUT"},
            resolved_guardrail=None,
        )
        assert resp.status_code == 404

    def test_bedrock_error_returns_status(self, client, mock_service):
        """Verify Bedrock error is forwarded."""
        err_resp = Mock(
            status_code=400,
            text="invalid",
            json=Mock(return_value={"message": "invalid", "__type": "ValidationException"}),
        )
        mock_service.apply_guardrail = AsyncMock(
            side_effect=httpx.HTTPStatusError("400", request=Mock(), response=err_resp)
        )
        resp = _req(
            client,
            "/guardrail/test/version/1/apply",
            {"content": [], "source": "INPUT"},
            resolved_guardrail={"guardrailIdentifier": "g1", "guardrailVersion": "1"},
        )
        assert resp.status_code == 400


class TestRequestContext:
    """Test cases for _get_request_context auth validation."""

    def test_no_bearer_token_returns_403(self, client):
        """Verify request without Bearer token returns 403."""
        assert client.post("/model/test/converse", json={}).status_code == 403

    def test_no_account_id_returns_403(self, client):
        """Verify request without rate_ctx account_id returns 403."""
        assert (
            _req(client, "/model/test/converse", {"messages": []}, rate_ctx=None).status_code
            == 403
        )

    def test_failed_credentials_returns_403(self, client, mock_service):
        """Verify failed STS credentials returns 403."""
        mock_service.get_credentials = AsyncMock(return_value=None)
        assert _req(client, "/model/test/converse", {"messages": []}).status_code == 403


class TestRouterStructure:
    """Test cases for router configuration."""

    def test_has_5_post_routes(self, app):
        """Verify router registers exactly 5 POST routes."""
        routes = [r for r in app.routes if hasattr(r, "methods") and "POST" in r.methods]
        assert len(routes) == 5

    def test_expected_paths(self, app):
        """Verify all expected route paths are registered."""
        paths = {r.path for r in app.routes if hasattr(r, "methods")}
        expected = {
            "/model/{model_id}/converse",
            "/model/{model_id}/converse-stream",
            "/model/{model_id}/invoke",
            "/model/{model_id}/invoke-with-response-stream",
            "/guardrail/{guardrail_identifier}/version/{guardrail_version}/apply",
        }
        assert expected.issubset(paths)
