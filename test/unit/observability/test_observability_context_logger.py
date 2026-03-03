"""Unit tests for observability.context_logger module."""

import logging
from unittest.mock import Mock, patch

from observability.context_logger import ContextLogger
from observability.context_vars import set_user_context


class TestContextLogger:
    """Test cases for ContextLogger class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_logger = Mock()
        self.context_logger = ContextLogger(self.mock_logger)

    def test_add_context_with_user_info(self):
        """Test adding user context to extra dict."""
        set_user_context("test-client", "Test Client")

        result = self.context_logger._add_context()

        assert result["client.id"] == "test-client"
        assert result["client.name"] == "Test Client"

    def test_add_context_with_client_name(self):
        """Test adding user context with client name to extra dict."""
        set_user_context("test-client", "Test Client Name")

        result = self.context_logger._add_context()

        assert result["client.id"] == "test-client"
        assert result["client.name"] == "Test Client Name"

    def test_add_context_without_user_info(self):
        """Test adding context without user info set."""
        result = self.context_logger._add_context()

        assert result == {}

    def test_add_context_with_existing_extra(self):
        """Test adding context to existing extra dict."""
        set_user_context("test-client", "Test Client")
        existing_extra = {"custom_field": "custom_value"}

        result = self.context_logger._add_context(existing_extra)

        assert result["client.id"] == "test-client"
        assert result["client.name"] == "Test Client"
        assert result["custom_field"] == "custom_value"

    @patch("observability.context_logger.inspect.currentframe")
    def test_log_with_caller_info_debug(self, mock_frame):
        """Test debug logging with caller info preservation."""
        # Mock frame stack
        mock_current_frame = Mock()
        mock_caller_frame = Mock()
        mock_caller_frame.f_code.co_filename = "/test/file.py"
        mock_caller_frame.f_code.co_name = "test_function"
        mock_caller_frame.f_lineno = 42

        mock_current_frame.f_back.f_back = mock_caller_frame
        mock_frame.return_value = mock_current_frame

        # Mock logger methods
        self.mock_logger.isEnabledFor.return_value = True
        self.mock_logger.makeRecord.return_value = Mock()
        self.mock_logger.handle = Mock()

        self.context_logger.debug("Test message")

        # Verify makeRecord was called with correct parameters
        self.mock_logger.makeRecord.assert_called_once()
        call_args = self.mock_logger.makeRecord.call_args[0]

        assert call_args[1] == logging.DEBUG  # level
        assert call_args[2] == "/test/file.py"  # filename
        assert call_args[3] == 42  # lineno
        assert call_args[4] == "Test message"  # msg
        assert call_args[7] == "test_function"  # funcName

    @patch("observability.context_logger.inspect.currentframe")
    def test_log_with_caller_info_info(self, mock_frame):
        """Test info logging with caller info preservation."""
        # Mock frame stack
        mock_current_frame = Mock()
        mock_caller_frame = Mock()
        mock_caller_frame.f_code.co_filename = "/test/file.py"
        mock_caller_frame.f_code.co_name = "test_function"
        mock_caller_frame.f_lineno = 42

        mock_current_frame.f_back.f_back = mock_caller_frame
        mock_frame.return_value = mock_current_frame

        # Mock logger methods
        self.mock_logger.isEnabledFor.return_value = True
        self.mock_logger.makeRecord.return_value = Mock()
        self.mock_logger.handle = Mock()

        self.context_logger.info("Test message")

        # Verify makeRecord was called with INFO level
        call_args = self.mock_logger.makeRecord.call_args[0]
        assert call_args[1] == logging.INFO

    @patch("observability.context_logger.inspect.currentframe")
    def test_log_with_caller_info_warning(self, mock_frame):
        """Test warning logging with caller info preservation."""
        # Mock frame stack
        mock_current_frame = Mock()
        mock_caller_frame = Mock()
        mock_caller_frame.f_code.co_filename = "/test/file.py"
        mock_caller_frame.f_code.co_name = "test_function"
        mock_caller_frame.f_lineno = 42

        mock_current_frame.f_back.f_back = mock_caller_frame
        mock_frame.return_value = mock_current_frame

        # Mock logger methods
        self.mock_logger.isEnabledFor.return_value = True
        self.mock_logger.makeRecord.return_value = Mock()
        self.mock_logger.handle = Mock()

        self.context_logger.warning("Test message")

        # Verify makeRecord was called with WARNING level
        call_args = self.mock_logger.makeRecord.call_args[0]
        assert call_args[1] == logging.WARNING

    @patch("observability.context_logger.inspect.currentframe")
    def test_log_with_caller_info_error(self, mock_frame):
        """Test error logging with caller info preservation."""
        # Mock frame stack
        mock_current_frame = Mock()
        mock_caller_frame = Mock()
        mock_caller_frame.f_code.co_filename = "/test/file.py"
        mock_caller_frame.f_code.co_name = "test_function"
        mock_caller_frame.f_lineno = 42

        mock_current_frame.f_back.f_back = mock_caller_frame
        mock_frame.return_value = mock_current_frame

        # Mock logger methods
        self.mock_logger.isEnabledFor.return_value = True
        self.mock_logger.makeRecord.return_value = Mock()
        self.mock_logger.handle = Mock()

        self.context_logger.error("Test message")

        # Verify makeRecord was called with ERROR level
        call_args = self.mock_logger.makeRecord.call_args[0]
        assert call_args[1] == logging.ERROR

    @patch("observability.context_logger.inspect.currentframe")
    def test_log_with_caller_info_critical(self, mock_frame):
        """Test critical logging with caller info preservation."""
        # Mock frame stack
        mock_current_frame = Mock()
        mock_caller_frame = Mock()
        mock_caller_frame.f_code.co_filename = "/test/file.py"
        mock_caller_frame.f_code.co_name = "test_function"
        mock_caller_frame.f_lineno = 42

        mock_current_frame.f_back.f_back = mock_caller_frame
        mock_frame.return_value = mock_current_frame

        # Mock logger methods
        self.mock_logger.isEnabledFor.return_value = True
        self.mock_logger.makeRecord.return_value = Mock()
        self.mock_logger.handle = Mock()

        self.context_logger.critical("Test message")

        # Verify makeRecord was called with CRITICAL level
        call_args = self.mock_logger.makeRecord.call_args[0]
        assert call_args[1] == logging.CRITICAL

    def test_debug_level_check(self):
        """Test debug logging respects log level."""
        self.mock_logger.isEnabledFor.return_value = False

        self.context_logger.debug("Test message")

        self.mock_logger.isEnabledFor.assert_called_once_with(logging.DEBUG)
        self.mock_logger.makeRecord.assert_not_called()

    def test_info_level_check(self):
        """Test info logging respects log level."""
        self.mock_logger.isEnabledFor.return_value = False

        self.context_logger.info("Test message")

        self.mock_logger.isEnabledFor.assert_called_once_with(logging.INFO)
        self.mock_logger.makeRecord.assert_not_called()

    @patch("observability.context_logger.inspect.currentframe")
    def test_log_with_args_and_kwargs(self, mock_frame):
        """Test logging with args and kwargs."""
        # Mock frame stack
        mock_current_frame = Mock()
        mock_caller_frame = Mock()
        mock_caller_frame.f_code.co_filename = "/test/file.py"
        mock_caller_frame.f_code.co_name = "test_function"
        mock_caller_frame.f_lineno = 42

        mock_current_frame.f_back.f_back = mock_caller_frame
        mock_frame.return_value = mock_current_frame

        # Mock logger methods
        self.mock_logger.isEnabledFor.return_value = True
        self.mock_logger.makeRecord.return_value = Mock()
        self.mock_logger.handle = Mock()

        extra = {"custom": "value"}
        self.context_logger.info("Test %s", "message", extra=extra, stack_info=True)

        # Verify makeRecord was called with correct parameters
        call_args = self.mock_logger.makeRecord.call_args
        assert call_args[0][4] == "Test %s"  # msg
        assert call_args[0][5] == ("message",)  # args
        assert call_args[1]["extra"]["custom"] == "value"
        assert call_args[1]["stack_info"] is True
