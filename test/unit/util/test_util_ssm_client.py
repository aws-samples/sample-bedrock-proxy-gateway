# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for SSM client utility."""

import json
from unittest.mock import Mock, patch

from botocore.exceptions import ClientError
from util.ssm_client import SSMClient


class TestSSMClient:
    """Test class for SSM client functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.ssm_client = SSMClient()
        self.mock_logger = Mock()

    def test_init(self):
        """Test SSMClient initialization."""
        client = SSMClient()
        assert client._client is None

    @patch("util.ssm_client.boto3")
    def test_client_property_lazy_initialization(self, mock_boto3):
        """Test lazy initialization of SSM client."""
        mock_ssm_client = Mock()
        mock_boto3.client.return_value = mock_ssm_client

        # First access should create client
        result = self.ssm_client.client
        assert result == mock_ssm_client
        mock_boto3.client.assert_called_once_with("ssm")

        # Second access should return cached client
        result2 = self.ssm_client.client
        assert result2 == mock_ssm_client
        # Should not call boto3.client again
        assert mock_boto3.client.call_count == 1

    @patch("util.ssm_client.boto3")
    def test_get_parameter_json_success(self, mock_boto3):
        """Test successful parameter retrieval."""
        mock_ssm_client = Mock()
        mock_boto3.client.return_value = mock_ssm_client

        test_data = {"key": "value", "number": 42}
        mock_ssm_client.get_parameter.return_value = {
            "Parameter": {"Value": json.dumps(test_data)}
        }

        result = self.ssm_client.get_parameter_json("test-param", self.mock_logger)

        assert result == test_data
        mock_ssm_client.get_parameter.assert_called_once_with(
            Name="/test-param", WithDecryption=True
        )
        self.mock_logger.warning.assert_not_called()
        self.mock_logger.error.assert_not_called()

    @patch("util.ssm_client.boto3")
    def test_get_parameter_json_client_error(self, mock_boto3):
        """Test parameter retrieval with ClientError."""
        mock_ssm_client = Mock()
        mock_boto3.client.return_value = mock_ssm_client

        error_response = {"Error": {"Code": "ParameterNotFound", "Message": "Parameter not found"}}
        mock_ssm_client.get_parameter.side_effect = ClientError(error_response, "GetParameter")

        result = self.ssm_client.get_parameter_json("missing-param", self.mock_logger)

        assert result is None
        mock_ssm_client.get_parameter.assert_called_once_with(
            Name="/missing-param", WithDecryption=True
        )
        self.mock_logger.warning.assert_called_once()
        assert (
            "Failed to load SSM parameter 'missing-param'"
            in self.mock_logger.warning.call_args[0][0]
        )

    @patch("util.ssm_client.boto3")
    def test_get_parameter_json_invalid_json(self, mock_boto3):
        """Test parameter retrieval with invalid JSON."""
        mock_ssm_client = Mock()
        mock_boto3.client.return_value = mock_ssm_client

        mock_ssm_client.get_parameter.return_value = {"Parameter": {"Value": "invalid json {"}}

        result = self.ssm_client.get_parameter_json("invalid-json-param", self.mock_logger)

        assert result is None
        mock_ssm_client.get_parameter.assert_called_once_with(
            Name="/invalid-json-param", WithDecryption=True
        )
        self.mock_logger.error.assert_called_once()
        assert (
            "Invalid JSON in SSM parameter 'invalid-json-param'"
            in self.mock_logger.error.call_args[0][0]
        )

    @patch("util.ssm_client.boto3")
    def test_get_parameter_json_unexpected_error(self, mock_boto3):
        """Test parameter retrieval with unexpected error."""
        mock_ssm_client = Mock()
        mock_boto3.client.return_value = mock_ssm_client

        mock_ssm_client.get_parameter.side_effect = Exception("Unexpected error")

        result = self.ssm_client.get_parameter_json("error-param", self.mock_logger)

        assert result is None
        mock_ssm_client.get_parameter.assert_called_once_with(
            Name="/error-param", WithDecryption=True
        )
        self.mock_logger.error.assert_called_once()
        assert (
            "Unexpected error loading SSM parameter 'error-param'"
            in self.mock_logger.error.call_args[0][0]
        )

    @patch("util.ssm_client.boto3")
    def test_get_parameter_json_complex_data(self, mock_boto3):
        """Test parameter retrieval with complex JSON data."""
        mock_ssm_client = Mock()
        mock_boto3.client.return_value = mock_ssm_client

        complex_data = {
            "accounts": ["123456789", "987654321"],
            "config": {"enabled": True, "timeout": 30, "nested": {"value": "test"}},
        }
        mock_ssm_client.get_parameter.return_value = {
            "Parameter": {"Value": json.dumps(complex_data)}
        }

        result = self.ssm_client.get_parameter_json("complex-param", self.mock_logger)

        assert result == complex_data
        assert isinstance(result["accounts"], list)
        assert isinstance(result["config"], dict)
        assert result["config"]["nested"]["value"] == "test"

    @patch("util.ssm_client.boto3")
    def test_get_parameter_json_empty_string(self, mock_boto3):
        """Test parameter retrieval with empty string value."""
        mock_ssm_client = Mock()
        mock_boto3.client.return_value = mock_ssm_client

        mock_ssm_client.get_parameter.return_value = {"Parameter": {"Value": ""}}

        result = self.ssm_client.get_parameter_json("empty-param", self.mock_logger)

        assert result is None
        self.mock_logger.error.assert_called_once()
        assert (
            "Invalid JSON in SSM parameter 'empty-param'" in self.mock_logger.error.call_args[0][0]
        )

    @patch("util.ssm_client.boto3")
    def test_get_parameter_json_null_value(self, mock_boto3):
        """Test parameter retrieval with null JSON value."""
        mock_ssm_client = Mock()
        mock_boto3.client.return_value = mock_ssm_client

        mock_ssm_client.get_parameter.return_value = {"Parameter": {"Value": "null"}}

        result = self.ssm_client.get_parameter_json("null-param", self.mock_logger)

        assert result is None

    def test_parameter_path_formatting(self):
        """Test that parameter names are correctly formatted with leading slash."""
        with patch("util.ssm_client.boto3") as mock_boto3:
            mock_ssm_client = Mock()
            mock_boto3.client.return_value = mock_ssm_client
            mock_ssm_client.get_parameter.return_value = {"Parameter": {"Value": '{"test": true}'}}

            # Test various parameter name formats
            test_cases = [
                "simple-param",
                "param/with/slashes",
                "param-with-dashes",
                "param_with_underscores",
            ]

            for param_name in test_cases:
                self.ssm_client.get_parameter_json(param_name, self.mock_logger)
                expected_path = f"/{param_name}"
                mock_ssm_client.get_parameter.assert_called_with(
                    Name=expected_path, WithDecryption=True
                )

    @patch("util.ssm_client.boto3")
    def test_put_parameter_success(self, mock_boto3):
        """Test successful parameter creation."""
        mock_ssm_client = Mock()
        mock_boto3.client.return_value = mock_ssm_client
        mock_ssm_client.put_parameter.return_value = {}

        result = self.ssm_client.put_parameter("test-param", "test-value", self.mock_logger)

        assert result is True
        mock_ssm_client.put_parameter.assert_called_once_with(
            Name="/test-param", Value="test-value", Type="String", Overwrite=False
        )
        self.mock_logger.error.assert_not_called()

    @patch("util.ssm_client.boto3")
    def test_put_parameter_with_options(self, mock_boto3):
        """Test parameter creation with custom options."""
        mock_ssm_client = Mock()
        mock_boto3.client.return_value = mock_ssm_client
        mock_ssm_client.put_parameter.return_value = {}

        result = self.ssm_client.put_parameter(
            "secure-param",
            "secure-value",
            self.mock_logger,
            parameter_type="SecureString",
            overwrite=True,
        )

        assert result is True
        mock_ssm_client.put_parameter.assert_called_once_with(
            Name="/secure-param", Value="secure-value", Type="SecureString", Overwrite=True
        )

    @patch("util.ssm_client.boto3")
    def test_put_parameter_client_error(self, mock_boto3):
        """Test parameter creation with ClientError."""
        mock_ssm_client = Mock()
        mock_boto3.client.return_value = mock_ssm_client

        error_response = {
            "Error": {"Code": "ParameterAlreadyExists", "Message": "Parameter exists"}
        }
        mock_ssm_client.put_parameter.side_effect = ClientError(error_response, "PutParameter")

        result = self.ssm_client.put_parameter("existing-param", "value", self.mock_logger)

        assert result is False
        self.mock_logger.error.assert_called_once()
        assert (
            "Failed to put SSM parameter 'existing-param'"
            in self.mock_logger.error.call_args[0][0]
        )

    @patch("util.ssm_client.boto3")
    def test_put_parameter_unexpected_error(self, mock_boto3):
        """Test parameter creation with unexpected error."""
        mock_ssm_client = Mock()
        mock_boto3.client.return_value = mock_ssm_client
        mock_ssm_client.put_parameter.side_effect = Exception("Unexpected error")

        result = self.ssm_client.put_parameter("error-param", "value", self.mock_logger)

        assert result is False
        self.mock_logger.error.assert_called_once()
        assert (
            "Unexpected error putting SSM parameter 'error-param'"
            in self.mock_logger.error.call_args[0][0]
        )
