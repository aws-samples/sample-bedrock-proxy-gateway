"""Unit tests for auth.jwks module."""

import time
from unittest.mock import Mock, patch

import requests
from core.auth.jwks import JWKSCache, jwks_cache


class TestJWKSCache:
    """Test cases for JWKSCache class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.cache = JWKSCache()

    @patch("requests.get")
    def test_get_rsa_key_success(self, mock_get):
        """Test successful JWKS retrieval."""
        jwks_data = {
            "keys": [
                {
                    "use": "sig",
                    "kty": "RSA",
                    "n": "test_n",
                    "e": "AQAB",
                }
            ]
        }
        mock_response = Mock()
        mock_response.json.return_value = jwks_data
        mock_get.return_value = mock_response

        result = self.cache.get_rsa_key("https://test.com/jwks")

        assert result == jwks_data
        mock_get.assert_called_once_with("https://test.com/jwks", timeout=10)

    @patch("requests.get")
    def test_get_rsa_key_cache_hit(self, mock_get):
        """Test cache hit scenario."""
        # Set up cached key
        jwks_data = {"keys": [{"use": "sig", "kty": "RSA"}]}
        self.cache._keys = jwks_data
        self.cache._last_fetch = time.time()

        result = self.cache.get_rsa_key("https://test.com/jwks")

        assert result == jwks_data
        mock_get.assert_not_called()

    @patch("requests.get")
    def test_get_rsa_key_request_failure(self, mock_get):
        """Test request failure handling."""
        mock_get.side_effect = requests.RequestException("Network error")

        result = self.cache.get_rsa_key("https://test.com/jwks")

        assert result is None

    @patch("requests.get")
    def test_get_rsa_key_no_suitable_key(self, mock_get):
        """Test when JWKS is returned even without signing keys."""
        jwks_data = {
            "keys": [
                {
                    "use": "enc",  # Not signing key
                    "kty": "RSA",
                }
            ]
        }
        mock_response = Mock()
        mock_response.json.return_value = jwks_data
        mock_get.return_value = mock_response

        result = self.cache.get_rsa_key("https://test.com/jwks")

        assert result == jwks_data

    @patch("requests.get")
    def test_get_rsa_key_cache_expired(self, mock_get):
        """Test cache expiration."""
        # Set up expired cache
        self.cache._keys = {"keys": []}
        self.cache._last_fetch = time.time() - 87000  # Expired

        jwks_data = {
            "keys": [
                {
                    "use": "sig",
                    "kty": "RSA",
                    "n": "test_n",
                    "e": "AQAB",
                }
            ]
        }
        mock_response = Mock()
        mock_response.json.return_value = jwks_data
        mock_get.return_value = mock_response

        result = self.cache.get_rsa_key("https://test.com/jwks")

        assert result == jwks_data
        mock_get.assert_called_once()

    def test_global_cache_instance(self):
        """Test global cache instance exists."""
        assert jwks_cache is not None
        assert isinstance(jwks_cache, JWKSCache)
