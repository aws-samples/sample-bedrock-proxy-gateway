# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for bedrock_service_httpx module."""

from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest
from services.bedrock_service_httpx import BedrockHttpxService, _get_httpx_client


@pytest.fixture(autouse=True)
def _reset_httpx_client():
    """Reset the module-level httpx client between tests."""
    import services.bedrock_service_httpx as mod

    mod._httpx_client = None
    yield
    mod._httpx_client = None


@pytest.fixture
def service():
    """Create a BedrockHttpxService with mocked config."""
    with patch("services.bedrock_service_httpx.config") as mock_config:
        mock_config.aws_region = "us-east-1"
        mock_config.shared_role_name = "test-role"
        mock_config.sts_vpc_endpoint_dns = ""
        mock_config.bedrock_runtime_vpc_endpoint_dns = ""
        mock_config.environment = "dev"
        mock_config.app_hash = "abc123"
        yield BedrockHttpxService(Mock())


CREDS = {"AccessKeyId": "AK", "SecretAccessKey": "SK", "SessionToken": "ST"}

STS_XML = """<AssumeRoleWithWebIdentityResponse xmlns="https://sts.amazonaws.com/doc/2011-06-15/">
  <AssumeRoleWithWebIdentityResult><Credentials>
    <AccessKeyId>AKIA</AccessKeyId><SecretAccessKey>secret</SecretAccessKey>
    <SessionToken>token</SessionToken><Expiration>2099-01-01T00:00:00Z</Expiration>
  </Credentials></AssumeRoleWithWebIdentityResult>
</AssumeRoleWithWebIdentityResponse>"""


class TestGetHttpxClient:
    """Test cases for _get_httpx_client singleton."""

    def test_creates_client(self):
        """Verify client is created as httpx.AsyncClient."""
        assert isinstance(_get_httpx_client(), httpx.AsyncClient)

    def test_returns_same_client(self):
        """Verify singleton returns same instance."""
        assert _get_httpx_client() is _get_httpx_client()


class TestGetCredentials:
    """Test cases for get_credentials method."""

    @pytest.mark.asyncio
    async def test_returns_cached_credentials(self, service):
        """Verify cached credentials are returned without STS call."""
        with patch(
            "services.bedrock_service_httpx.get_cache", new_callable=AsyncMock, return_value=CREDS
        ):
            result = await service.get_credentials("c", "123", "jwt")
        assert result == CREDS

    @pytest.mark.asyncio
    async def test_calls_sts_on_cache_miss(self, service):
        """Verify STS is called and result cached on cache miss."""
        mock_resp = Mock(text=STS_XML, raise_for_status=Mock())
        mock_client = AsyncMock(post=AsyncMock(return_value=mock_resp))

        with (
            patch(
                "services.bedrock_service_httpx.get_cache",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch("services.bedrock_service_httpx.set_cache", new_callable=AsyncMock) as mock_set,
            patch("services.bedrock_service_httpx._get_httpx_client", return_value=mock_client),
        ):
            result = await service.get_credentials("c", "123", "jwt")

        assert result["AccessKeyId"] == "AKIA"
        mock_set.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_none_on_sts_http_error(self, service):
        """Verify None returned when STS returns HTTP error."""
        mock_resp = Mock()
        mock_resp.raise_for_status = Mock(
            side_effect=httpx.HTTPStatusError(
                "403", request=Mock(), response=Mock(text="forbidden")
            )
        )
        mock_client = AsyncMock(post=AsyncMock(return_value=mock_resp))

        with (
            patch(
                "services.bedrock_service_httpx.get_cache",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch("services.bedrock_service_httpx._get_httpx_client", return_value=mock_client),
        ):
            assert await service.get_credentials("c", "123", "jwt") is None

    @pytest.mark.asyncio
    async def test_returns_none_on_sts_exception(self, service):
        """Verify None returned when STS request raises exception."""
        mock_client = AsyncMock(post=AsyncMock(side_effect=Exception("fail")))

        with (
            patch(
                "services.bedrock_service_httpx.get_cache",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch("services.bedrock_service_httpx._get_httpx_client", return_value=mock_client),
        ):
            assert await service.get_credentials("c", "123", "jwt") is None


class TestParseStsResponse:
    """Test cases for _parse_sts_response."""

    def test_parses_valid_xml(self, service):
        """Verify valid STS XML is parsed correctly."""
        result = service._parse_sts_response(STS_XML)
        assert result["AccessKeyId"] == "AKIA"
        assert isinstance(result["Expiration"], datetime)

    def test_returns_none_for_missing_credentials(self, service):
        """Verify None for XML without Credentials element."""
        xml = '<AssumeRoleWithWebIdentityResponse xmlns="https://sts.amazonaws.com/doc/2011-06-15/"><AssumeRoleWithWebIdentityResult></AssumeRoleWithWebIdentityResult></AssumeRoleWithWebIdentityResponse>'
        assert service._parse_sts_response(xml) is None

    def test_returns_none_for_invalid_xml(self, service):
        """Verify None for malformed XML."""
        assert service._parse_sts_response("not xml") is None


class TestSignRequest:
    """Test cases for _sign_request."""

    def test_returns_signed_headers(self, service):
        """Verify SigV4 headers are added."""
        headers = service._sign_request(
            "POST",
            "https://bedrock-runtime.us-east-1.amazonaws.com/model/test/converse",
            {"Content-Type": "application/json"},
            b"{}",
            CREDS,
        )
        assert "Authorization" in headers
        assert "X-Amz-Security-Token" in headers


class TestConverse:
    """Test cases for converse method."""

    @pytest.mark.asyncio
    async def test_converse_success(self, service):
        """Verify successful converse call returns parsed response."""
        import orjson

        mock_resp = Mock(content=orjson.dumps({"output": "ok"}), raise_for_status=Mock())
        mock_client = AsyncMock(post=AsyncMock(return_value=mock_resp))

        with patch("services.bedrock_service_httpx._get_httpx_client", return_value=mock_client):
            result = await service.converse("model", {"messages": []}, CREDS)
        assert result["output"] == "ok"

    @pytest.mark.asyncio
    async def test_converse_raises_on_http_error(self, service):
        """Verify HTTPStatusError propagates from converse."""
        mock_resp = Mock()
        mock_resp.raise_for_status = Mock(
            side_effect=httpx.HTTPStatusError("400", request=Mock(), response=Mock())
        )
        mock_client = AsyncMock(post=AsyncMock(return_value=mock_resp))

        with (
            patch("services.bedrock_service_httpx._get_httpx_client", return_value=mock_client),
            pytest.raises(httpx.HTTPStatusError),
        ):
            await service.converse("model", {}, CREDS)


class TestInvokeModel:
    """Test cases for invoke_model method."""

    @pytest.mark.asyncio
    async def test_invoke_model_success(self, service):
        """Verify successful invoke returns raw bytes."""
        mock_resp = Mock(content=b'{"ok":true}', raise_for_status=Mock())
        mock_client = AsyncMock(post=AsyncMock(return_value=mock_resp))

        with patch("services.bedrock_service_httpx._get_httpx_client", return_value=mock_client):
            assert await service.invoke_model("model", b"{}", CREDS) == b'{"ok":true}'

    @pytest.mark.asyncio
    async def test_invoke_model_with_guardrail_headers(self, service):
        """Verify guardrail headers are included in signed request."""
        mock_resp = Mock(content=b"{}", raise_for_status=Mock())
        mock_client = AsyncMock(post=AsyncMock(return_value=mock_resp))
        guardrail = {"guardrailIdentifier": "g1", "guardrailVersion": "1", "trace": "ENABLED"}

        with patch("services.bedrock_service_httpx._get_httpx_client", return_value=mock_client):
            await service.invoke_model("model", b"{}", CREDS, guardrail)

        headers = mock_client.post.call_args.kwargs.get("headers", {})
        assert "X-Amzn-Bedrock-GuardrailIdentifier" in headers


class TestApplyGuardrail:
    """Test cases for apply_guardrail method."""

    @pytest.mark.asyncio
    async def test_apply_guardrail_success(self, service):
        """Verify successful apply guardrail returns parsed response."""
        import orjson

        mock_resp = Mock(content=orjson.dumps({"action": "NONE"}), raise_for_status=Mock())
        mock_client = AsyncMock(post=AsyncMock(return_value=mock_resp))

        with patch("services.bedrock_service_httpx._get_httpx_client", return_value=mock_client):
            result = await service.apply_guardrail("g1", "1", {"content": []}, CREDS)
        assert result["action"] == "NONE"


class TestVpcEndpointHeaders:
    """Test cases for VPC endpoint Host header handling."""

    def test_sts_vpc_endpoint_sets_host(self):
        """Verify STS endpoint uses VPC endpoint DNS when configured."""
        with patch("services.bedrock_service_httpx.config") as c:
            c.aws_region = "us-east-1"
            c.shared_role_name = "r"
            c.sts_vpc_endpoint_dns = "vpce-abc.sts.us-east-1.vpce.amazonaws.com"
            c.bedrock_runtime_vpc_endpoint_dns = ""
            c.environment = "dev"
            c.app_hash = "h"
            assert "vpce-abc" in BedrockHttpxService(Mock()).sts_endpoint

    def test_bedrock_vpc_endpoint_sets_host(self):
        """Verify Bedrock endpoint uses VPC endpoint DNS when configured."""
        with patch("services.bedrock_service_httpx.config") as c:
            c.aws_region = "us-east-1"
            c.shared_role_name = "r"
            c.sts_vpc_endpoint_dns = ""
            c.bedrock_runtime_vpc_endpoint_dns = "vpce-xyz.bedrock.vpce.amazonaws.com"
            c.environment = "dev"
            c.app_hash = "h"
            assert "vpce-xyz" in BedrockHttpxService(Mock()).bedrock_endpoint
