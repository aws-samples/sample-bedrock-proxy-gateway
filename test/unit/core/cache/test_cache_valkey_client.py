"""Unit tests for cache.valkey_client module."""


# from cache.valkey_client import get_valkey_client, is_valkey_available


# class TestValkeyClient:
#     """Test cases for Valkey client functions."""

#     @pytest.mark.asyncio
#     @patch("cache.valkey_client.config")
#     @patch("cache.valkey_client.GlideClusterClient")
#     async def test_get_valkey_client_success(self, mock_glide_client, mock_config):
#         """Test successful client creation."""
#         mock_config.valkey_cache_endpoint = "localhost"
#         mock_config.valkey_cache_port = 6379
#         mock_config.valkey_ssl = False

#         mock_client = Mock()

#         async def mock_create(_config):
#             return mock_client

#         mock_glide_client.create = mock_create

#         result = await get_valkey_client()

#         assert result == mock_client

#     @pytest.mark.asyncio
#     @patch("cache.valkey_client.config")
#     @patch("cache.valkey_client.GlideClusterClient")
#     async def test_get_valkey_client_creation_failure(self, mock_glide_client, mock_config):
#         """Test client creation failure."""
#         mock_config.valkey_cache_endpoint = "localhost"
#         mock_config.valkey_cache_port = 6379
#         mock_config.valkey_ssl = False

#         mock_glide_client.create.side_effect = Exception("Connection failed")

#         result = await get_valkey_client()

#         assert result is None

#     @pytest.mark.asyncio
#     @patch("cache.valkey_client.config")
#     @patch("cache.valkey_client.GlideClusterClient")
#     async def test_get_valkey_client_ssl_config(self, mock_glide_client, _mock_config):
#         """Test client creation with SSL configuration."""
#         _mock_config.valkey_cache_endpoint = "prod-endpoint"
#         _mock_config.valkey_cache_port = 6380
#         _mock_config.valkey_ssl = True

#         mock_client = Mock()
#         config_used = None

#         async def mock_create(_config):
#             nonlocal config_used
#             config_used = _config
#             return mock_client

#         mock_glide_client.create = mock_create

#         result = await get_valkey_client()

#         assert result == mock_client
#         # Verify SSL configuration was passed
#         assert config_used.use_tls is True

#     @pytest.mark.asyncio
#     @patch("cache.valkey_client.get_valkey_client")
#     async def test_is_valkey_available_success(self, mock_get_client):
#         """Test successful Valkey availability check."""
#         mock_client = AsyncMock()
#         mock_client.ping.return_value = "PONG"
#         mock_get_client.return_value = mock_client

#         result = await is_valkey_available()

#         assert result is True
#         mock_client.ping.assert_called_once()

#     @pytest.mark.asyncio
#     @patch("cache.valkey_client.get_valkey_client")
#     async def test_is_valkey_available_no_client(self, mock_get_client):
#         """Test availability check when no client available."""
#         mock_get_client.return_value = None

#         result = await is_valkey_available()

#         assert result is False

#     @pytest.mark.asyncio
#     @patch("cache.valkey_client.get_valkey_client")
#     async def test_is_valkey_available_ping_failure(self, mock_get_client):
#         """Test availability check with ping failure."""
#         mock_client = AsyncMock()
#         mock_client.ping.side_effect = Exception("Ping failed")
#         mock_get_client.return_value = mock_client

#         result = await is_valkey_available()

#         assert result is False
