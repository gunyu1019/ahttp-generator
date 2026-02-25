# Copyright (c) 2026 gunyu1019
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""
NumPy style docstring generator for OpenAPI operations.
"""

from typing import Dict, Any, List, Optional


class DocstringGenerator:
    """Generates NumPy style docstrings from OpenAPI operation information."""

    def generate_numpy_docstring(
        self,
        summary: Optional[str] = None,
        description: Optional[str] = None,
        parameters: List[Dict[str, Any]] = None,
        return_type: Optional[str] = None,
        return_description: Optional[str] = None
    ) -> str:
        """
        Generate NumPy style docstring from operation data.

        Args:
            summary: Brief summary of the operation
            description: Detailed description of the operation
            parameters: List of parameter dictionaries with name, type, description
            return_type: Return type string
            return_description: Description of the return value

        Returns:
            Complete NumPy style docstring text
        """
        lines = []

        # 1. Summary line (first line)
        if summary:
            lines.append(summary.strip())
        elif description:
            # Use first sentence of description as summary if no summary provided
            first_sentence = self._extract_first_sentence(description)
            lines.append(first_sentence)
        else:
            lines.append("Execute API operation.")

        # 2. Extended description (if different from summary)
        if description and description.strip():
            description_text = description.strip()
            # Only add if it's different from the summary line
            if not summary or description_text != summary.strip():
                lines.append("")  # Blank line
                lines.append(description_text)

        # 3. Parameters section
        if parameters:
            lines.append("")  # Blank line
            lines.append("Parameters")
            lines.append("----------")

            for param in parameters:
                param_name = param.get('name', 'unknown')
                param_type = self._get_parameter_type_string(param)
                param_desc = param.get('description', '')

                # Parameter line: name : type
                lines.append(f"{param_name} : {param_type}")

                # Description (indented with 4 spaces)
                if param_desc:
                    desc_lines = param_desc.strip().split('\n')
                    for desc_line in desc_lines:
                        lines.append(f"    {desc_line.strip()}")
                else:
                    # Provide contextual description based on parameter name or type
                    param_type_desc = self._get_contextual_description(param_name, param.get('schema', {}))
                    lines.append(f"    {param_type_desc}")

        # 4. Returns section
        if return_type:
            lines.append("")  # Blank line
            lines.append("Returns")
            lines.append("-------")
            lines.append(return_type)

            # Return description (indented with 4 spaces)
            if return_description:
                desc_lines = return_description.strip().split('\n')
                for desc_line in desc_lines:
                    lines.append(f"    {desc_line.strip()}")
            else:
                lines.append("    The response from the API operation.")

        # Join all lines and ensure proper formatting
        docstring = '\n'.join(lines)

        return docstring

    def _extract_first_sentence(self, text: str) -> str:
        """Extract first sentence from text."""
        if not text:
            return ""

        text = text.strip()
        # Look for sentence ending punctuation
        for punct in ['.', '!', '?']:
            if punct in text:
                first_sentence = text.split(punct)[0] + punct
                return first_sentence.strip()

        # If no sentence ending found, return first 80 characters or the whole text
        if len(text) <= 80:
            return text
        else:
            return text[:77] + "..."

    def _get_parameter_type_string(self, param: Dict[str, Any]) -> str:
        """Get type string for parameter."""
        schema = param.get('schema', param)  # Some specs put schema info directly in param
        param_type = schema.get('type', 'string')

        # Map OpenAPI types to Python types
        type_mapping = {
            'string': 'str',
            'integer': 'int',
            'number': 'float',
            'boolean': 'bool',
            'array': 'list',
            'object': 'dict'
        }

        python_type = type_mapping.get(param_type, 'str')

        # Handle optional parameters
        is_required = param.get('required', True)
        if not is_required:
            python_type = f"{python_type}, optional"

        return python_type

    def _get_contextual_description(self, param_name: str, schema: Dict[str, Any]) -> str:
        """Get contextual description for parameter based on name and type."""
        param_name_lower = param_name.lower()

        # Common parameter name patterns
        if 'id' in param_name_lower and param_name_lower.endswith('_id'):
            entity_name = param_name_lower.replace('_id', '')
            return f"The unique identifier for the {entity_name}."
        elif param_name_lower in ['account_id', 'accountid']:
            return "The unique identifier for the account."
        elif param_name_lower in ['user_id', 'userid']:
            return "The unique identifier for the user."
        elif param_name_lower in ['player_id', 'playerid']:
            return "The unique identifier for the player."
        elif param_name_lower in ['match_id', 'matchid']:
            return "The unique identifier for the match."
        elif param_name_lower in ['season_id', 'seasonid']:
            return "The unique identifier for the season."
        elif param_name_lower.startswith('filter_'):
            filter_field = param_name_lower.replace('filter_', '')
            return f"Filter parameter for {filter_field}."
        elif 'limit' in param_name_lower:
            return "Maximum number of items to return."
        elif 'offset' in param_name_lower:
            return "Number of items to skip before returning results."
        elif param_name_lower in ['sort', 'sort_by', 'order_by']:
            return "Field to sort results by."
        elif param_name_lower in ['page', 'page_number']:
            return "Page number for paginated results."
        elif param_name_lower in ['size', 'page_size']:
            return "Number of items per page."
        else:
            # Generic description based on type
            param_type = schema.get('type', 'string')
            type_desc = {
                'string': 'A text value',
                'integer': 'A numeric value',
                'number': 'A numeric value',
                'boolean': 'A true/false value',
                'array': 'A list of values',
                'object': 'An object value'
            }.get(param_type, 'A parameter value')

            return f"{type_desc} for {param_name.replace('_', ' ')}."

    def create_docstring_ast_node(self, docstring_text: str) -> 'ast.Expr':
        """
        Create AST Expr node for docstring with proper formatting.

        Args:
            docstring_text: The docstring text

        Returns:
            AST Expr node containing the docstring
        """
        import ast

        # Clean and normalize the docstring
        normalized_text = self.normalize_docstring(docstring_text)
        return ast.Expr(value=ast.Constant(value=normalized_text))

    def normalize_docstring(self, docstring_text: str) -> str:
        """
        Normalize docstring text with proper indentation and formatting.

        Args:
            docstring_text: Raw docstring text

        Returns:
            Normalized docstring text that will format correctly when unparsed
        """
        if not docstring_text:
            return ""

        lines = docstring_text.strip().split('\n')

        # Remove empty lines at the beginning and end
        while lines and not lines[0].strip():
            lines.pop(0)
        while lines and not lines[-1].strip():
            lines.pop()

        if not lines:
            return ""

        # For single-line docstrings, return as-is
        if len(lines) == 1:
            return lines[0].strip()

        # For multi-line docstrings, ensure proper formatting
        result_lines = []

        # First line (summary)
        result_lines.append(lines[0].strip())

        # Process remaining lines, preserving NumPy docstring structure
        i = 1
        while i < len(lines):
            line = lines[i]
            stripped_line = line.strip()
            
            if not stripped_line:  # Empty lines
                result_lines.append("")
                i += 1
                continue
                
            # Check for numpy docstring section headers
            if stripped_line in ["Parameters", "Returns", "Raises", "See Also", "Notes", "Examples"]:
                result_lines.append(stripped_line)
                i += 1
                continue
            elif stripped_line.startswith("---"):  # Section underline (like "----------")
                result_lines.append(stripped_line)
                i += 1
                continue
            
            # Check if this line starts with 4 spaces (parameter/return description)
            if line.startswith("    "):
                # This is an indented description line - preserve it exactly
                result_lines.append(line.rstrip())  # Keep indentation but remove trailing spaces
            else:
                # Regular line - just strip
                result_lines.append(stripped_line)
            
            i += 1

        return '\n'.join(result_lines)

