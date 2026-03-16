# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Context-aware logger wrapper

This module provides a ContextLogger that automatically adds user context
like client_id and custom headers to all log messages while preserving the
original caller's file path, line number, and function name.

The key challenge solved here is that logger wrappers typically show the wrapper's
location instead of the actual calling code. This implementation uses Python's inspect
module to capture the real caller information and manually create LogRecords with
correct metadata.
"""  # noqa D415

import inspect
import logging

from observability.context_vars import client_id_context, client_name_context


class ContextLogger:
    """Logger wrapper that automatically includes user context while preserving caller info.

    This wrapper solves the common problem where logger wrappers lose the
    original caller information (file path, line number, function name) by using
    inspect to capture the real calling location and manually creating LogRecords
    with correct metadata.
    """

    def __init__(self, logger):
        self._logger = logger

    def _add_context(self, extra=None):
        """Add user context to extra dict.

        Args:
        ----
            extra: Optional dictionary to add context to.

        Returns:
        -------
            dict: Dictionary with user context added.
        """
        if extra is None:
            extra = {}

        client_id = client_id_context.get()
        client_name = client_name_context.get()

        if client_id:
            extra["client.id"] = client_id
        if client_name:
            extra["client.name"] = client_name

        return extra

    def _log_with_caller_info(self, level, msg, *args, extra=None, **kwargs):
        """Create LogRecord with original caller information preserved.

        This method solves the wrapper problem by:
        1. Using inspect to get the actual calling code's frame information
        2. Manually creating a LogRecord with the correct file path, line number,
           and function name
        3. Adding user context automatically without losing caller metadata

        Frame stack when this method is called:
        - f_back.f_back.f_back = Original calling code (e.g., bedrock_routes.py:123)
        - f_back.f_back = Logger method (e.g., info(), error())
        - f_back = This method (_log_with_caller_info)
        - Current frame = This line of code

        Args:
        ----
            level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            msg: Log message format string
            *args: Arguments for message formatting
            extra: Additional attributes to include in log record
            **kwargs: Additional keyword arguments for LogRecord
        """
        extra = self._add_context(extra)

        # Get the original caller's frame by going back 2 levels:
        # current -> _log_with_caller_info -> info/error/etc -> actual caller
        frame = inspect.currentframe().f_back.f_back

        # Manually create LogRecord with correct caller information
        # This ensures code.file.path shows the real calling file, not context_logger.py
        record = self._logger.makeRecord(
            self._logger.name,
            level,
            frame.f_code.co_filename,
            frame.f_lineno,
            msg,
            args,
            None,
            frame.f_code.co_name,
            extra=extra,
            **kwargs,
        )

        self._logger.handle(record)

    def debug(self, msg, *args, extra=None, **kwargs):
        """Log debug message with user context.

        Args:
        ----
            msg: Log message format string.
            *args: Arguments for message formatting.
            extra: Additional log record attributes.
            **kwargs: Additional keyword arguments.
        """
        if self._logger.isEnabledFor(logging.DEBUG):
            self._log_with_caller_info(logging.DEBUG, msg, *args, extra=extra, **kwargs)

    def info(self, msg, *args, extra=None, **kwargs):
        """Log info message with user context.

        Args:
        ----
            msg: Log message format string.
            *args: Arguments for message formatting.
            extra: Additional log record attributes.
            **kwargs: Additional keyword arguments.
        """
        if self._logger.isEnabledFor(logging.INFO):
            self._log_with_caller_info(logging.INFO, msg, *args, extra=extra, **kwargs)

    def warning(self, msg, *args, extra=None, **kwargs):
        """Log warning message with user context.

        Args:
        ----
            msg: Log message format string.
            *args: Arguments for message formatting.
            extra: Additional log record attributes.
            **kwargs: Additional keyword arguments.
        """
        if self._logger.isEnabledFor(logging.WARNING):
            self._log_with_caller_info(logging.WARNING, msg, *args, extra=extra, **kwargs)

    def error(self, msg, *args, extra=None, **kwargs):
        """Log error message with user context.

        Args:
        ----
            msg: Log message format string.
            *args: Arguments for message formatting.
            extra: Additional log record attributes.
            **kwargs: Additional keyword arguments.
        """
        if self._logger.isEnabledFor(logging.ERROR):
            self._log_with_caller_info(logging.ERROR, msg, *args, extra=extra, **kwargs)

    def critical(self, msg, *args, extra=None, **kwargs):
        """Log critical message with user context.

        Args:
        ----
            msg: Log message format string.
            *args: Arguments for message formatting.
            extra: Additional log record attributes.
            **kwargs: Additional keyword arguments.
        """
        if self._logger.isEnabledFor(logging.CRITICAL):
            self._log_with_caller_info(logging.CRITICAL, msg, *args, extra=extra, **kwargs)
