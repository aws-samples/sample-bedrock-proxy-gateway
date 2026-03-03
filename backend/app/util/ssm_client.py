"""SSM client utility for parameter retrieval."""

import json
from typing import Any

import boto3
from botocore.exceptions import ClientError


class SSMClient:
    """Utility class for AWS Systems Manager Parameter Store operations."""

    def __init__(self):
        """Initialize SSM client."""
        self._client = None

    @property
    def client(self):
        """Lazy initialization of SSM client."""
        if self._client is None:
            self._client = boto3.client("ssm")
        return self._client

    def get_parameter_json(self, parameter_name: str, logger) -> dict[str, Any] | None:
        """Get JSON parameter from SSM Parameter Store.

        Args:
        ----
            parameter_name: Parameter name (without leading slash)
            logger: Logger instance for error reporting

        Returns:
        -------
            Parsed JSON data or None if parameter not found/accessible
        """
        try:
            # Use parameter name as-is if it starts with slash, otherwise add it
            parameter_path = (
                parameter_name if parameter_name.startswith("/") else f"/{parameter_name}"
            )
            response = self.client.get_parameter(Name=parameter_path, WithDecryption=True)
            return json.loads(response["Parameter"]["Value"])
        except ClientError as e:
            logger.warning(f"Failed to load SSM parameter '{parameter_name}': {str(e)}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in SSM parameter '{parameter_name}': {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error loading SSM parameter '{parameter_name}': {str(e)}")
            return None

    def put_parameter(
        self,
        parameter_name: str,
        value: str,
        logger,
        parameter_type: str = "String",
        overwrite: bool = False,
    ) -> bool:
        """Put parameter to SSM Parameter Store.

        Args:
        ----
            parameter_name: Parameter name (without leading slash)
            value: Parameter value
            logger: Logger instance for error reporting
            parameter_type: Parameter type (String, SecureString, StringList)
            overwrite: Whether to overwrite existing parameter

        Returns:
        -------
            True if successful, False otherwise
        """
        try:
            # Use parameter name as-is if it starts with slash, otherwise add it
            parameter_path = (
                parameter_name if parameter_name.startswith("/") else f"/{parameter_name}"
            )
            self.client.put_parameter(
                Name=parameter_path, Value=value, Type=parameter_type, Overwrite=overwrite
            )
            return True
        except ClientError as e:
            logger.error(f"Failed to put SSM parameter '{parameter_name}': {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error putting SSM parameter '{parameter_name}': {str(e)}")
            return False
