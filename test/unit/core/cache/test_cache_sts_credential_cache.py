"""Unit tests for cache.sts_credential_cache module."""


# from cache.sts_credential_cache import get_sts_credentials, set_sts_credentials


# class TestSTSCredentialCache:
#     """Test cases for STS credential caching functions."""

#     @pytest.mark.asyncio
#     async def test_get_sts_credentials_success(self):
#         """Test successful credential retrieval from cache."""
#         mock_client = AsyncMock()
#         mock_client.hgetall.return_value = {
#             b"AccessKeyId": b"test-access-key",
#             b"SecretAccessKey": b"test-secret-key",
#             b"SessionToken": b"test-session-token",
#         }

#         result = await get_sts_credentials(mock_client, "test-key")

#         assert result == {
#             "AccessKeyId": "test-access-key",
#             "SecretAccessKey": "test-secret-key",
#             "SessionToken": "test-session-token",
#         }
#         mock_client.hgetall.assert_called_once_with("test-key")

#     @pytest.mark.asyncio
#     async def test_get_sts_credentials_cache_miss(self):
#         """Test cache miss scenario."""
#         mock_client = AsyncMock()
#         mock_client.hgetall.return_value = None

#         result = await get_sts_credentials(mock_client, "test-key")

#         assert result is None
#         mock_client.hgetall.assert_called_once_with("test-key")

#     @pytest.mark.asyncio
#     async def test_get_sts_credentials_empty_cache(self):
#         """Test empty cache response."""
#         mock_client = AsyncMock()
#         mock_client.hgetall.return_value = {}

#         result = await get_sts_credentials(mock_client, "test-key")

#         assert result is None

#     @pytest.mark.asyncio
#     async def test_get_sts_credentials_exception(self):
#         """Test exception handling during cache retrieval."""
#         mock_client = AsyncMock()
#         mock_client.hgetall.side_effect = Exception("Cache error")

#         result = await get_sts_credentials(mock_client, "test-key")

#         assert result is None

#     @pytest.mark.asyncio
#     async def test_set_sts_credentials_success(self):
#         """Test successful credential caching."""
#         mock_client = AsyncMock()
#         mock_client.hset.return_value = 3
#         mock_client.expire.return_value = True

#         credentials = {
#             "AccessKeyId": "test-access-key",
#             "SecretAccessKey": "test-secret-key",
#             "SessionToken": "test-session-token",
#         }

#         await set_sts_credentials(mock_client, "test-key", credentials, 3600)

#         mock_client.hset.assert_called_once_with(
#             "test-key",
#             {
#                 "AccessKeyId": "test-access-key",
#                 "SecretAccessKey": "test-secret-key",
#                 "SessionToken": "test-session-token",
#             },
#         )
#         mock_client.expire.assert_called_once_with("test-key", 3600)

#     @pytest.mark.asyncio
#     async def test_set_sts_credentials_missing_fields(self):
#         """Test credential caching with missing fields."""
#         mock_client = AsyncMock()
#         mock_client.hset.return_value = 3
#         mock_client.expire.return_value = True

#         credentials = {
#             "AccessKeyId": "test-access-key",
#             # Missing SecretAccessKey and SessionToken
#         }

#         await set_sts_credentials(mock_client, "test-key", credentials)

#         mock_client.hset.assert_called_once_with(
#             "test-key",
#             {
#                 "AccessKeyId": "test-access-key",
#                 "SecretAccessKey": "",
#                 "SessionToken": "",
#             },
#         )

#     @pytest.mark.asyncio
#     async def test_set_sts_credentials_exception(self):
#         """Test exception handling during cache set."""
#         mock_client = AsyncMock()
#         mock_client.hset.side_effect = Exception("Cache error")

#         credentials = {
#             "AccessKeyId": "test-access-key",
#             "SecretAccessKey": "test-secret-key",
#             "SessionToken": "test-session-token",
#         }

#         result = await set_sts_credentials(mock_client, "test-key", credentials)

#         assert result is None

#     @pytest.mark.asyncio
#     async def test_set_sts_credentials_default_expiration(self):
#         """Test credential caching with default expiration."""
#         mock_client = AsyncMock()
#         mock_client.hset.return_value = 3
#         mock_client.expire.return_value = True

#         credentials = {
#             "AccessKeyId": "test-access-key",
#             "SecretAccessKey": "test-secret-key",
#             "SessionToken": "test-session-token",
#         }

#         await set_sts_credentials(mock_client, "test-key", credentials)

#         mock_client.expire.assert_called_once_with("test-key", 3500)
