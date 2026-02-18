"""
OpenAPI specification extractor module.
Extracts relevant information from OpenAPI specification for code generation.
"""

from typing import Dict, Any, List, Optional, Tuple
import re


class OpenAPIExtractor:
    """Extracts structured data from OpenAPI specification."""

    def extract(self, spec: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract relevant information from OpenAPI specification.

        Args:
            spec: OpenAPI specification dictionary

        Returns:
            Dictionary containing extracted data for code generation
        """
        # Store spec for reference resolution
        self.spec = spec

        # Extract basic info
        extracted_data = {
            'info': self._extract_info(spec),
            'servers': self._extract_servers(spec),
            'paths': self._extract_paths(spec),
            'schemas': self._extract_schemas(spec),
            'service_name': self._generate_service_name(spec)
        }

        # ...existing code...
        all_error_responses = {}
        for operation in extracted_data['paths']:
            error_responses = operation.get('error_responses', {})
            for status_code, error_info in error_responses.items():
                if status_code not in all_error_responses:
                    all_error_responses[status_code] = error_info
                # If same status code exists, merge descriptions
                elif error_info['description'] not in all_error_responses[status_code]['description']:
                    current_desc = all_error_responses[status_code]['description']
                    new_desc = error_info['description']
                    all_error_responses[status_code]['description'] = f"{current_desc}; {new_desc}"

        extracted_data['error_responses'] = all_error_responses

        # Create status code to exception class mapping for HTTP hooks
        extracted_data['status_code_mapping'] = self._create_status_code_mapping(all_error_responses)

        return extracted_data

    def _create_status_code_mapping(self, error_responses: Dict[str, Dict[str, Any]]) -> Dict[int, str]:
        """Create mapping from status codes to exception class names."""

        # Status code to exception name mapping (duplicated to avoid circular import)
        STATUS_CODE_NAMES = {
            '400': 'BadRequestError',
            '401': 'UnauthorizedError',
            '403': 'ForbiddenError',
            '404': 'NotFoundError',
            '405': 'MethodNotAllowedError',
            '409': 'ConflictError',
            '422': 'UnprocessableEntityError',
            '429': 'TooManyRequestsError',
            '500': 'InternalServerError',
            '502': 'BadGatewayError',
            '503': 'ServiceUnavailableError',
            '504': 'GatewayTimeoutError'
        }

        mapping = {}
        for status_code in error_responses.keys():
            if status_code in STATUS_CODE_NAMES:
                mapping[int(status_code)] = STATUS_CODE_NAMES[status_code]
            else:
                # Fallback for unknown status codes
                mapping[int(status_code)] = f'HttpError{status_code}'

        return mapping

    def _extract_info(self, spec: Dict[str, Any]) -> Dict[str, Any]:
        """Extract API information."""
        info = spec.get('info', {})
        return {
            'title': info.get('title', 'API'),
            'version': info.get('version', '1.0.0'),
            'description': info.get('description', '')
        }

    def _extract_servers(self, spec: Dict[str, Any]) -> List[str]:
        """Extract server URLs."""
        servers = spec.get('servers', [])
        if not servers:
            return ['https://api.example.com']

        return [server.get('url', 'https://api.example.com') for server in servers]

    def _extract_paths(self, spec: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract API paths and operations."""
        paths = spec.get('paths', {})
        operations = []

        for path, path_item in paths.items():
            for method, operation in path_item.items():
                if method.lower() in ['get', 'post', 'put', 'delete', 'patch', 'head', 'options']:
                    op_data = self._extract_operation(path, method.upper(), operation)
                    operations.append(op_data)

        return operations

    def _extract_operation(self, path: str, method: str, operation: Dict[str, Any]) -> Dict[str, Any]:
        """Extract single operation data."""
        operation_id = operation.get('operationId', self._generate_operation_id(method, path))

        return {
            'operation_id': operation_id,
            'method': method,
            'path': path,
            'summary': operation.get('summary', ''),
            'parameters': self._extract_parameters(operation),
            'request_body': self._extract_request_body(operation),
            'responses': self._extract_responses(operation),
            'error_responses': self._extract_error_responses(operation)
        }

    def _resolve_ref(self, ref_path: str, spec: Dict[str, Any]) -> Dict[str, Any]:
        """
        Resolve $ref reference to actual definition.

        Args:
            ref_path: Reference path (e.g., "#/components/parameters/AccountId")
            spec: Full OpenAPI specification

        Returns:
            Resolved definition dictionary
        """
        if not ref_path.startswith('#/'):
            # External references not supported yet
            return {}

        # Remove leading '#/' and split by '/'
        path_parts = ref_path[2:].split('/')

        # Navigate through the spec dictionary
        current = spec
        try:
            for part in path_parts:
                current = current[part]
            return current
        except (KeyError, TypeError):
            # Reference not found or invalid structure
            print(f"Warning: Could not resolve reference: {ref_path}")
            return {}

    def _extract_parameters(self, operation: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract and resolve parameter information."""
        parameters = operation.get('parameters', [])
        resolved_parameters = []

        for param in parameters:
            if '$ref' in param:
                # Resolve reference
                resolved_param = self._resolve_ref(param['$ref'], self.spec)
                if resolved_param:
                    resolved_parameters.append(resolved_param)
                else:
                    # Fallback for failed resolution
                    print(f"Warning: Failed to resolve parameter reference: {param['$ref']}")
                    fallback_param = {
                        'name': 'unknown_param',
                        'in': 'query',
                        'schema': {'type': 'string'},
                        'required': False
                    }
                    resolved_parameters.append(fallback_param)
            else:
                # Direct parameter definition
                resolved_parameters.append(param)

        return resolved_parameters

    def _extract_request_body(self, operation: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Extract request body information."""
        request_body = operation.get('requestBody')
        if not request_body:
            return None

        content = request_body.get('content', {})
        json_content = content.get('application/json', {})
        schema = json_content.get('schema', {})

        return {
            'required': request_body.get('required', False),
            'schema': schema
        }

    def _extract_responses(self, operation: Dict[str, Any]) -> Dict[str, Any]:
        """Extract response information."""
        responses = operation.get('responses', {})

        # Look for successful response (200, 201, etc.)
        for status_code in ['200', '201', '202', '204']:
            if status_code in responses:
                response = responses[status_code]
                content = response.get('content', {})
                json_content = content.get('application/json', {})
                schema = json_content.get('schema', {'type': 'object'})

                return {
                    'status_code': status_code,
                    'schema': schema
                }

        # Fallback to first response
        if responses:
            first_response = list(responses.values())[0]
            content = first_response.get('content', {})
            json_content = content.get('application/json', {})
            schema = json_content.get('schema', {'type': 'object'})

            return {
                'status_code': '200',
                'schema': schema
            }

        return {
            'status_code': '200',
            'schema': {'type': 'object'}
        }

    def _extract_error_responses(self, operation: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        """Extract error response information (non-2xx status codes)."""
        responses = operation.get('responses', {})
        error_responses = {}

        for status_code, response in responses.items():
            # Only process non-success status codes
            if not status_code.startswith('2') and status_code.isdigit():
                error_responses[status_code] = {
                    'description': response.get('description', f'Error {status_code}'),
                    'content': response.get('content', {}),
                    'schema': self._extract_error_schema(response)
                }

        return error_responses

    def _extract_error_schema(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """Extract schema from error response."""
        content = response.get('content', {})
        json_content = content.get('application/json', {})
        return json_content.get('schema', {'type': 'object'})

    def _extract_schemas(self, spec: Dict[str, Any]) -> Dict[str, Any]:
        """Extract component schemas."""
        components = spec.get('components', {})
        schemas = components.get('schemas', {})
        return schemas

    def _generate_service_name(self, spec: Dict[str, Any]) -> str:
        """Generate service class name from API info."""
        info = spec.get('info', {})
        title = info.get('title', 'API')

        # Clean up common suffixes and words
        title = re.sub(r'\b(API|api|Api)\b', '', title)
        title = title.strip()

        # Convert to PascalCase and add Service suffix
        words = re.findall(r'[a-zA-Z0-9]+', title)
        name = ''.join(word.capitalize() for word in words if word)

        if not name:
            name = 'Api'

        if not name.endswith('Service'):
            name += 'Service'

        return name

    def _generate_operation_id(self, method: str, path: str) -> str:
        """Generate operation ID from method and path."""
        # Convert path to camelCase method name
        path_parts = [part for part in path.split('/') if part and not part.startswith('{')]
        method_lower = method.lower()

        if not path_parts:
            return method_lower

        if method_lower == 'get':
            prefix = 'get' if len(path_parts) > 1 else 'list'
        elif method_lower == 'post':
            prefix = 'create'
        elif method_lower == 'put':
            prefix = 'update'
        elif method_lower == 'delete':
            prefix = 'delete'
        else:
            prefix = method_lower

        suffix = ''.join(word.capitalize() for word in path_parts)
        return prefix + suffix

