"""
Identifier sanitizer module.
Converts invalid Python identifiers to PEP 8 compliant snake_case names.
"""

import re
import keyword


class IdentifierSanitizer:
    """Sanitizes identifiers for Python PEP 8 compliance."""

    # Python reserved keywords that need suffix
    RESERVED_KEYWORDS = set(keyword.kwlist + ['True', 'False', 'None'])

    @classmethod
    def to_snake_case(cls, name: str) -> str:
        """
        Convert any string to a valid Python snake_case identifier.

        Args:
            name: Original parameter name (may contain special characters)

        Returns:
            Valid Python identifier in snake_case format

        Examples:
            filter[playerIds] -> filter_player_ids
            page[number] -> page_number
            Content-Type -> content_type
            X-API-Key -> x_api_key
            camelCase -> camel_case
            in -> in_
            1st -> arg_1st
        """
        if not name:
            return "arg"

        # Step 1: Handle special characters first
        # Replace brackets, dots, dashes with underscores
        sanitized = re.sub(r'[\[\]\.()-]', '_', name)

        # Remove other invalid characters
        sanitized = re.sub(r'[^a-zA-Z0-9_]', '_', sanitized)

        # Step 2: Convert camelCase to snake_case
        # Insert underscore before uppercase letters that follow lowercase letters
        sanitized = re.sub(r'([a-z])([A-Z])', r'\1_\2', sanitized)

        # Step 3: Convert to lowercase
        sanitized = sanitized.lower()

        # Step 4: Clean up multiple underscores
        sanitized = re.sub(r'_+', '_', sanitized)

        # Step 5: Remove leading/trailing underscores
        sanitized = sanitized.strip('_')

        # Step 6: Handle edge cases
        if not sanitized:
            sanitized = "arg"

        # Step 7: Handle names starting with numbers
        if sanitized and sanitized[0].isdigit():
            sanitized = f"arg_{sanitized}"

        # Step 8: Handle Python reserved keywords
        if sanitized in cls.RESERVED_KEYWORDS:
            sanitized = f"{sanitized}_"

        # Step 9: Ensure it's a valid identifier (fallback)
        if not sanitized.isidentifier():
            # Last resort: create a generic name
            sanitized = "arg"

        return sanitized

    @classmethod
    def needs_custom_name(cls, original: str, sanitized: str) -> bool:
        """
        Check if custom_name annotation is needed.

        Args:
            original: Original parameter name
            sanitized: Sanitized parameter name

        Returns:
            True if custom_name is needed (names are different)
        """
        return original != sanitized

