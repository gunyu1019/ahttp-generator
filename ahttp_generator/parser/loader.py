"""
OpenAPI specification loader module.
Handles loading and basic validation of OpenAPI JSON files.
"""

import json
import pathlib
from typing import Dict, Any


class OpenAPILoader:
    """Loads OpenAPI specification from JSON file."""

    def load(self, file_path: str) -> Dict[str, Any]:
        """
        Load OpenAPI specification from JSON file.

        Args:
            file_path: Path to OpenAPI JSON file

        Returns:
            Dictionary containing the OpenAPI specification

        Raises:
            FileNotFoundError: If the file doesn't exist
            json.JSONDecodeError: If the file is not valid JSON
            ValueError: If the file doesn't contain a valid OpenAPI spec
        """
        path = pathlib.Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"OpenAPI file not found: {file_path}")

        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in {file_path}: {e}")
        except Exception as e:
            raise ValueError(f"Error reading {file_path}: {e}")

        # Basic validation
        if not isinstance(data, dict):
            raise ValueError("OpenAPI specification must be a JSON object")

        if 'openapi' not in data:
            raise ValueError("Missing 'openapi' field in specification")

        openapi_version = data['openapi']
        if not openapi_version.startswith('3.'):
            raise ValueError(f"Unsupported OpenAPI version: {openapi_version}. Only 3.x is supported")

        return data

