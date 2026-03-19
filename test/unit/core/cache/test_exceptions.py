# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for cache exceptions."""

import pytest
from core.cache.exceptions import (
    CacheConfigurationError,
    CacheConnectionError,
    CacheError,
    CacheOperationError,
)


class TestCacheError:
    """Test cases for CacheError base exception."""

    def test_cache_error_is_exception(self) -> None:
        """Test that CacheError inherits from Exception."""
        assert issubclass(CacheError, Exception)

    def test_cache_error_instantiation(self) -> None:
        """Test CacheError can be instantiated with message."""
        error = CacheError("Test error")
        assert str(error) == "Test error"

    def test_cache_error_without_message(self) -> None:
        """Test CacheError can be instantiated without message."""
        error = CacheError()
        assert str(error) == ""


class TestCacheConnectionError:
    """Test cases for CacheConnectionError."""

    def test_inherits_from_cache_error(self) -> None:
        """Test that CacheConnectionError inherits from CacheError."""
        assert issubclass(CacheConnectionError, CacheError)

    def test_instantiation_with_message(self) -> None:
        """Test CacheConnectionError can be instantiated with message."""
        error = CacheConnectionError("Connection failed")
        assert str(error) == "Connection failed"

    def test_can_be_raised_and_caught_as_cache_error(self) -> None:
        """Test that CacheConnectionError can be caught as CacheError."""
        with pytest.raises(CacheError):
            raise CacheConnectionError("Connection failed")


class TestCacheOperationError:
    """Test cases for CacheOperationError."""

    def test_inherits_from_cache_error(self) -> None:
        """Test that CacheOperationError inherits from CacheError."""
        assert issubclass(CacheOperationError, CacheError)

    def test_instantiation_with_message(self) -> None:
        """Test CacheOperationError can be instantiated with message."""
        error = CacheOperationError("Operation failed")
        assert str(error) == "Operation failed"

    def test_can_be_raised_and_caught_as_cache_error(self) -> None:
        """Test that CacheOperationError can be caught as CacheError."""
        with pytest.raises(CacheError):
            raise CacheOperationError("Operation failed")


class TestCacheConfigurationError:
    """Test cases for CacheConfigurationError."""

    def test_inherits_from_cache_error(self) -> None:
        """Test that CacheConfigurationError inherits from CacheError."""
        assert issubclass(CacheConfigurationError, CacheError)

    def test_instantiation_with_message(self) -> None:
        """Test CacheConfigurationError can be instantiated with message."""
        error = CacheConfigurationError("Invalid configuration")
        assert str(error) == "Invalid configuration"

    def test_can_be_raised_and_caught_as_cache_error(self) -> None:
        """Test that CacheConfigurationError can be caught as CacheError."""
        with pytest.raises(CacheError):
            raise CacheConfigurationError("Invalid configuration")


class TestExceptionHierarchy:
    """Test cases for exception hierarchy and polymorphism."""

    def test_all_exceptions_inherit_from_cache_error(self) -> None:
        """Test that all cache exceptions inherit from CacheError."""
        exceptions = [CacheConnectionError, CacheOperationError, CacheConfigurationError]
        for exception_class in exceptions:
            assert issubclass(exception_class, CacheError)

    def test_exception_polymorphism(self) -> None:
        """Test that specific exceptions can be caught as CacheError."""
        exceptions = [
            CacheConnectionError("Connection error"),
            CacheOperationError("Operation error"),
            CacheConfigurationError("Config error"),
        ]

        for exception in exceptions:
            with pytest.raises(CacheError):
                raise exception
