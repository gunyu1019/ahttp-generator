# Copyright (c) 2026 gunyu1019
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""
Core loader module for OpenAPI specification files.
Supports multiple formats: JSON, YAML, XML.
"""

import json
import os
from typing import Dict, Any, Union

# Optional YAML support - graceful degradation if PyYAML is not installed
try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    yaml = None
    YAML_AVAILABLE = False

# XML parsing using standard library
import xml.etree.ElementTree as ET


def load_spec(file_path: str) -> Dict[str, Any]:
    """
    Load OpenAPI specification from a file and return as Python dictionary.

    Supported formats:
    - JSON (.json)
    - YAML (.yaml, .yml) - requires PyYAML
    - XML (.xml) - basic support for OpenAPI structure

    Args:
        file_path: Path to the specification file

    Returns:
        Dictionary containing parsed OpenAPI specification

    Raises:
        FileNotFoundError: If the file doesn't exist
        ImportError: If required dependencies are missing
        ValueError: If file format is not supported
        json.JSONDecodeError: If JSON parsing fails
        yaml.YAMLError: If YAML parsing fails
        ET.ParseError: If XML parsing fails
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Specification file not found: {file_path}")

    # Detect file format by extension
    _, ext = os.path.splitext(file_path)
    ext = ext.lower()

    try:
        if ext == '.json':
            return _load_json(file_path)

        elif ext in ('.yaml', '.yml'):
            return _load_yaml(file_path)

        elif ext == '.xml':
            return _load_xml(file_path)

        else:
            raise ValueError(f"Unsupported file format: {ext}. Supported formats: .json, .yaml, .yml, .xml")

    except Exception as e:
        raise ValueError(f"Failed to parse {file_path}: {str(e)}") from e


def _load_json(file_path: str) -> Dict[str, Any]:
    """Load JSON file and return as dictionary."""
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def _load_yaml(file_path: str) -> Dict[str, Any]:
    """Load YAML file and return as dictionary."""
    if not YAML_AVAILABLE:
        raise ImportError(
            "PyYAML library is required to parse YAML files. "
            "Install it with: pip install PyYAML"
        )

    with open(file_path, 'r', encoding='utf-8') as f:
        try:
            # Use safe_load for security - prevents arbitrary code execution
            data = yaml.safe_load(f)

            # Ensure we return a dictionary
            if not isinstance(data, dict):
                raise ValueError("YAML file must contain a dictionary/object at root level")

            return data

        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML format: {str(e)}") from e


def _load_xml(file_path: str) -> Dict[str, Any]:
    """Load XML file and convert to dictionary."""
    try:
        tree = ET.parse(file_path)
        root = tree.getroot()

        # Convert XML tree to dictionary
        result = _xml_to_dict(root)

        # OpenAPI XML should have a root element (usually 'openapi' or similar)
        # If the root has a meaningful tag name, preserve it
        if root.tag and root.tag != 'root':
            return {root.tag: result} if result else {}

        return result if isinstance(result, dict) else {}

    except ET.ParseError as e:
        raise ValueError(f"Invalid XML format: {str(e)}") from e


def _xml_to_dict(element: ET.Element) -> Union[Dict[str, Any], str, None]:
    """
    Recursively convert XML element to dictionary.

    Conversion rules:
    - Tag names become dictionary keys
    - Text content becomes values
    - Attributes are merged into the dictionary with '@' prefix
    - Child elements become nested dictionaries or lists
    - Multiple children with same tag name become a list

    Args:
        element: XML element to convert

    Returns:
        Dictionary representation of the XML element
    """
    result = {}

    # Handle attributes - prefix with '@' to distinguish from child elements
    if element.attrib:
        for key, value in element.attrib.items():
            result[f'@{key}'] = value

    # Handle child elements
    children = list(element)
    if children:
        # Group children by tag name
        child_dict = {}
        for child in children:
            tag = child.tag
            child_data = _xml_to_dict(child)

            if tag in child_dict:
                # Multiple children with same tag - convert to list
                if not isinstance(child_dict[tag], list):
                    child_dict[tag] = [child_dict[tag]]
                child_dict[tag].append(child_data)
            else:
                child_dict[tag] = child_data

        result.update(child_dict)

    # Handle text content
    text = element.text
    if text and text.strip():
        text = text.strip()

        # If element has children, store text as '#text'
        if children:
            result['#text'] = text
        else:
            # If no children, return text directly (for leaf nodes)
            if result:
                # Has attributes, keep as dict and add text
                result['#text'] = text
            else:
                # No attributes or children, return text only
                return text

    # Handle tail content (text after closing tag)
    tail = element.tail
    if tail and tail.strip():
        result['#tail'] = tail.strip()

    # Return the result
    if not result:
        return None  # Empty element

    return result


def get_supported_formats() -> list[str]:
    """
    Get list of supported file formats.

    Returns:
        List of supported file extensions
    """
    formats = ['.json', '.xml']

    if YAML_AVAILABLE:
        formats.extend(['.yaml', '.yml'])

    return formats


def is_format_supported(file_path: str) -> bool:
    """
    Check if the file format is supported.

    Args:
        file_path: Path to check

    Returns:
        True if format is supported, False otherwise
    """
    _, ext = os.path.splitext(file_path)
    return ext.lower() in get_supported_formats()


# Convenience function for backward compatibility
def load(file_path: str) -> Dict[str, Any]:
    """Alias for load_spec for backward compatibility."""
    return load_spec(file_path)
