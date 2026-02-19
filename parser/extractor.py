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
            'security_schemes': self._extract_security_schemes(spec),
            'service_name': self._generate_service_name(spec)
        }

        # Combine error responses from all operations
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

        # Collect inline response models from operations
        inline_response_models = {}
        for operation in extracted_data['paths']:
            response_info = operation.get('responses', {})
            inline_model = response_info.get('inline_model')
            if inline_model:
                model_name = inline_model['name']
                model_schema = inline_model['schema']
                inline_response_models[model_name] = model_schema

        # Store response models separately from domain models
        extracted_data['response_models'] = inline_response_models

        # Do NOT add inline models to schemas (keep domain models separate)
        # extracted_data['schemas'] remains only components/schemas models

        # CRITICAL: Deduplicate function names to prevent method overrides
        self._deduplicate_function_names(extracted_data['paths'])

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

    def _extract_servers(self, spec: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract server URLs with proper base URL and base path separation.

        Returns:
            Dictionary containing 'base_url' and 'base_path'
        """
        servers = spec.get('servers', [])
        if not servers:
            return {
                'base_url': 'https://api.example.com',
                'base_path': ''
            }

        server_url = servers[0].get('url', 'https://api.example.com')

        # Handle server variables by using default values
        variables = servers[0].get('variables', {})
        for var_name, var_def in variables.items():
            default_value = var_def.get('default', '')
            server_url = server_url.replace(f'{{{var_name}}}', default_value)

        # Parse URL to separate base URL from base path
        from urllib.parse import urlparse
        parsed = urlparse(server_url)

        # Base URL is scheme + netloc (no path)
        base_url = f"{parsed.scheme}://{parsed.netloc}"

        # Base path is the path component (if any)
        base_path = parsed.path if parsed.path else ''

        # Ensure base_url never ends with '/'
        base_url = base_url.rstrip('/')

        # Ensure base_path is properly formatted
        if base_path and not base_path.startswith('/'):
            base_path = '/' + base_path
        if base_path.endswith('/'):
            base_path = base_path.rstrip('/')

        return {
            'base_url': base_url,
            'base_path': base_path
        }

    def _extract_paths(self, spec: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract API paths and operations."""
        paths = spec.get('paths', {})
        operations = []

        # Get base path from servers
        servers_info = self._extract_servers(spec)
        base_path = servers_info.get('base_path', '')

        for path, path_item in paths.items():
            # Combine base_path with endpoint path
            full_path = self._combine_paths(base_path, path)

            for method, operation in path_item.items():
                if method.lower() in ['get', 'post', 'put', 'delete', 'patch', 'head', 'options']:
                    op_data = self._extract_operation(full_path, method.upper(), operation)
                    operations.append(op_data)

        return operations

    def _combine_paths(self, base_path: str, endpoint_path: str) -> str:
        """
        Combine base path and endpoint path properly.

        Args:
            base_path: Base path from server URL (e.g., '/shards/steam')
            endpoint_path: Individual endpoint path (e.g., '/players')

        Returns:
            Combined path (e.g., '/shards/steam/players')
        """
        # Ensure endpoint_path starts with '/'
        if not endpoint_path.startswith('/'):
            endpoint_path = '/' + endpoint_path

        # If no base_path, return endpoint_path as is
        if not base_path:
            return endpoint_path

        # Remove trailing '/' from base_path if exists
        if base_path.endswith('/'):
            base_path = base_path.rstrip('/')

        # Combine paths
        return base_path + endpoint_path

    def _extract_operation(self, path: str, method: str, operation: Dict[str, Any]) -> Dict[str, Any]:
        """Extract single operation data with context injection for response model naming."""
        operation_id = operation.get('operationId', self._generate_operation_id(method, path))

        # Step 1: Determine function name (using sanitizer for consistency)
        from core.sanitizer import IdentifierSanitizer
        func_name = IdentifierSanitizer.to_snake_case(operation_id)

        # Step 2: Determine response model name with priority logic
        suggested_model_name = self._determine_response_model_name(operation, func_name)

        return {
            'operation_id': operation_id,
            'method': method,
            'path': path,
            'summary': operation.get('summary', ''),
            'description': operation.get('description', ''),  # Added description
            'parameters': self._extract_parameters(operation),
            'request_body': self._extract_request_body(operation),
            'responses': self._extract_responses_with_context(operation, suggested_model_name),
            'error_responses': self._extract_error_responses(operation)
        }

    def _determine_response_model_name(self, operation: Dict[str, Any], func_name: str) -> str:
        """
        Determine response model name based on priority logic.

        Priority 1: Operation ID (if exists)
        Priority 2: Generated function name
        """
        # Priority 1: Use operation ID if available
        if 'operationId' in operation and operation['operationId']:
            base_name = operation['operationId']
        else:
            # Priority 2: Use generated function name
            base_name = func_name

        # Convert to PascalCase and add Response suffix
        return self._to_pascal_case_response(base_name)

    def _to_pascal_case_response(self, name: str) -> str:
        """Convert snake_case or camelCase to PascalCase + Response suffix."""
        from core.sanitizer import IdentifierSanitizer

        # First sanitize to snake_case, then convert to PascalCase
        snake_case = IdentifierSanitizer.to_snake_case(name)
        words = snake_case.split('_')
        pascal_case = ''.join(word.capitalize() for word in words if word)

        # Add Response suffix if not present
        if not pascal_case.endswith('Response'):
            pascal_case += 'Response'

        return pascal_case

    def _extract_responses_with_context(self, operation: Dict[str, Any], model_name_hint: str) -> Dict[str, Any]:
        """Extract response information with model name hint for context injection."""
        responses = operation.get('responses', {})
        operation_id = operation.get('operationId', 'unknown')

        # Look for successful response (200, 201, etc.)
        for status_code in ['200', '201', '202', '204']:
            if status_code in responses:
                response = responses[status_code]
                content = response.get('content', {})

                # Analyze content types with model name hint
                response_info = self._analyze_response_content_with_hint(content, model_name_hint)
                response_info['status_code'] = status_code
                response_info['description'] = response.get('description', 'Successful operation')  # Add description
                return response_info

        # Fallback to first response
        if responses:
            first_status = list(responses.keys())[0]
            first_response = list(responses.values())[0]
            content = first_response.get('content', {})
            response_info = self._analyze_response_content_with_hint(content, model_name_hint)
            response_info['status_code'] = first_status
            response_info['description'] = first_response.get('description', 'API response')  # Add description
            return response_info

        return {
            'status_code': '200',
            'schema': {'type': 'object'},
            'response_type': 'json',
            'content_type': 'application/json',
            'description': 'API response'  # Add default description
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
        """Extract and resolve parameter information including descriptions."""
        parameters = operation.get('parameters', [])
        resolved_parameters = []

        for param in parameters:
            if '$ref' in param:
                # Resolve reference
                resolved_param = self._resolve_ref(param['$ref'], self.spec)
                if resolved_param:
                    # Ensure description is included
                    if 'description' not in resolved_param:
                        resolved_param['description'] = ''
                    resolved_parameters.append(resolved_param)
                else:
                    # Fallback for failed resolution
                    print(f"Warning: Failed to resolve parameter reference: {param['$ref']}")
                    fallback_param = {
                        'name': 'unknown_param',
                        'in': 'query',
                        'schema': {'type': 'string'},
                        'required': False,
                        'description': ''
                    }
                    resolved_parameters.append(fallback_param)
            else:
                # Direct parameter definition - ensure description is included
                param_copy = param.copy()
                if 'description' not in param_copy:
                    param_copy['description'] = ''
                resolved_parameters.append(param_copy)

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
        """Extract response information (legacy method - redirects to context-aware version)."""
        # Get operation ID and generate function name for backward compatibility
        operation_id = operation.get('operationId', self._generate_operation_id('get', '/unknown'))
        from core.sanitizer import IdentifierSanitizer
        func_name = IdentifierSanitizer.to_snake_case(operation_id)
        suggested_model_name = self._determine_response_model_name(operation, func_name)

        # Call the context-aware version
        return self._extract_responses_with_context(operation, suggested_model_name)

    def _analyze_response_content(self, content: Dict[str, Any], operation_id: str) -> Dict[str, Any]:
        """Analyze response content by MIME type and return appropriate schema info."""
        if not content:
            return {
                'schema': {'type': 'object'},
                'response_type': 'json',
                'content_type': 'application/json'
            }

        # Check each content type in order of preference
        for content_type, content_spec in content.items():
            content_type = content_type.lower()

            # Case 1: Text content (text/*)
            if content_type.startswith('text/'):
                return {
                    'schema': {'type': 'string'},
                    'response_type': 'text',
                    'content_type': content_type,
                    'python_type': 'str'
                }

            # Case 2: JSON content (application/json or application/*+json)
            elif (content_type == 'application/json' or
                  (content_type.startswith('application/') and content_type.endswith('+json'))):

                schema = content_spec.get('schema', {'type': 'object'})

                # Check if this is an inline schema that needs a model
                response_model_info = self._analyze_inline_schema(schema, operation_id)

                return {
                    'schema': schema,
                    'response_type': 'json',
                    'content_type': content_type,
                    'python_type': response_model_info.get('python_type', 'Dict[str, Any]'),
                    'inline_model': response_model_info.get('inline_model'),
                    'model_name': response_model_info.get('model_name')
                }

        # Case 3: Fallback for other types
        first_content_type = list(content.keys())[0] if content else 'application/octet-stream'
        first_content_spec = list(content.values())[0] if content else {}

        return {
            'schema': first_content_spec.get('schema', {'type': 'object'}),
            'response_type': 'binary',
            'content_type': first_content_type,
            'python_type': 'bytes'
        }

    def _analyze_inline_schema(self, schema: Dict[str, Any], operation_id: str) -> Dict[str, Any]:
        """Analyze schema to determine if inline model generation is needed."""
        # If it's a $ref, use existing model
        if '$ref' in schema:
            ref_path = schema['$ref']
            if ref_path.startswith('#/components/schemas/'):
                model_name = ref_path.split('/')[-1]
                # Simple sanitization
                sanitized_name = ''.join(word.capitalize() for word in model_name.split('_'))
                return {
                    'python_type': sanitized_name,
                    'inline_model': None,
                    'model_name': sanitized_name
                }

        # Check for array of models
        elif schema.get('type') == 'array':
            items = schema.get('items', {})
            if '$ref' in items:
                ref_path = items['$ref']
                if ref_path.startswith('#/components/schemas/'):
                    model_name = ref_path.split('/')[-1]
                    sanitized_name = ''.join(word.capitalize() for word in model_name.split('_'))
                    return {
                        'python_type': f'List[{sanitized_name}]',
                        'inline_model': None,
                        'model_name': sanitized_name
                    }
            elif items.get('type') == 'object' and 'properties' in items:
                # Inline array item model
                model_name = self._generate_response_model_name(operation_id, 'Item')
                return {
                    'python_type': f'List[{model_name}]',
                    'inline_model': {
                        'name': model_name,
                        'schema': items
                    },
                    'model_name': model_name
                }

        # Check for inline object that needs a model
        elif schema.get('type') == 'object' and 'properties' in schema:
            model_name = self._generate_response_model_name(operation_id, 'Response')
            return {
                'python_type': model_name,
                'inline_model': {
                    'name': model_name,
                    'schema': schema
                },
                'model_name': model_name
            }

        # Fallback to generic dict
        return {
            'python_type': 'Dict[str, Any]',
            'inline_model': None
        }

    def _generate_response_model_name(self, operation_id: str, suffix: str = 'Response') -> str:
        """Generate unique response model name based on operation ID."""
        from core.sanitizer import IdentifierSanitizer

        if not operation_id or operation_id == 'unknown':
            return f'Unknown{suffix}'

        # Sanitize operation ID to snake_case first, then convert to PascalCase
        sanitized_op_id = IdentifierSanitizer.to_snake_case(operation_id)

        # Convert to PascalCase
        words = sanitized_op_id.split('_')
        pascal_case = ''.join(word.capitalize() for word in words if word)

        # Add suffix
        return f'{pascal_case}{suffix}'

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

    def _analyze_response_content_with_hint(self, content: Dict[str, Any], model_name_hint: str) -> Dict[str, Any]:
        """Analyze response content with model name hint for context injection."""
        if not content:
            return {
                'schema': {'type': 'object'},
                'response_type': 'json',
                'content_type': 'application/json'
            }

        # Check each content type in order of preference
        for content_type, content_spec in content.items():
            content_type = content_type.lower()

            # Case 1: Text content (text/*)
            if content_type.startswith('text/'):
                return {
                    'schema': {'type': 'string'},
                    'response_type': 'text',
                    'content_type': content_type,
                    'python_type': 'str'
                }

            # Case 2: JSON content (application/json or application/*+json)
            elif (content_type == 'application/json' or
                  (content_type.startswith('application/') and content_type.endswith('+json'))):

                schema = content_spec.get('schema', {'type': 'object'})

                # Check if this is an inline schema that needs a model
                response_model_info = self._analyze_inline_schema_with_hint(schema, model_name_hint)

                return {
                    'schema': schema,
                    'response_type': 'json',
                    'content_type': content_type,
                    'python_type': response_model_info.get('python_type', 'Dict[str, Any]'),
                    'inline_model': response_model_info.get('inline_model'),
                    'model_name': response_model_info.get('model_name')
                }

        # Case 3: Fallback for other types
        first_content_type = list(content.keys())[0] if content else 'application/octet-stream'
        first_content_spec = list(content.values())[0] if content else {}

        return {
            'schema': first_content_spec.get('schema', {'type': 'object'}),
            'response_type': 'binary',
            'content_type': first_content_type,
            'python_type': 'bytes'
        }

    def _analyze_inline_schema_with_hint(self, schema: Dict[str, Any], model_name_hint: str) -> Dict[str, Any]:
        """Analyze schema with model name hint for proper context injection."""
        # If it's a $ref, use existing model
        if '$ref' in schema:
            ref_path = schema['$ref']
            if ref_path.startswith('#/components/schemas/'):
                model_name = ref_path.split('/')[-1]
                # Simple sanitization
                sanitized_name = ''.join(word.capitalize() for word in model_name.split('_'))
                return {
                    'python_type': sanitized_name,
                    'inline_model': None,
                    'model_name': sanitized_name
                }

        # Check for array of models
        elif schema.get('type') == 'array':
            items = schema.get('items', {})

            # Handle oneOf/anyOf inside array items
            if 'oneOf' in items or 'anyOf' in items:
                # Extract model names from oneOf/anyOf references
                refs_list = items.get('oneOf', items.get('anyOf', []))
                model_names = []

                for ref_item in refs_list:
                    if '$ref' in ref_item:
                        ref_path = ref_item['$ref']
                        if ref_path.startswith('#/components/schemas/'):
                            model_name = ref_path.split('/')[-1]
                            sanitized_name = ''.join(word.capitalize() for word in model_name.split('_'))
                            model_names.append(sanitized_name)

                if model_names:
                    # Create Union type for multiple models
                    if len(model_names) > 1:
                        union_type = f"Union[{', '.join(model_names)}]"
                        return {
                            'python_type': f'List[{union_type}]',
                            'inline_model': None,
                            'model_name': None,
                            'union_models': model_names
                        }
                    else:
                        # Single model in oneOf/anyOf
                        return {
                            'python_type': f'List[{model_names[0]}]',
                            'inline_model': None,
                            'model_name': model_names[0]
                        }

            elif '$ref' in items:
                ref_path = items['$ref']
                if ref_path.startswith('#/components/schemas/'):
                    model_name = ref_path.split('/')[-1]
                    sanitized_name = ''.join(word.capitalize() for word in model_name.split('_'))
                    return {
                        'python_type': f'List[{sanitized_name}]',
                        'inline_model': None,
                        'model_name': sanitized_name
                    }
            elif items.get('type') == 'object' and 'properties' in items:
                # Inline array item model - use hint with Item suffix
                item_model_name = model_name_hint.replace('Response', 'Item')
                return {
                    'python_type': f'List[{item_model_name}]',
                    'inline_model': {
                        'name': item_model_name,
                        'schema': items
                    },
                    'model_name': item_model_name
                }

        # Check for inline object that needs a model - USE THE HINT!
        elif schema.get('type') == 'object' and 'properties' in schema:
            # This is the key fix - use the provided model name hint instead of generating one
            return {
                'python_type': model_name_hint,
                'inline_model': {
                    'name': model_name_hint,
                    'schema': schema
                },
                'model_name': model_name_hint
            }

        # Fallback to generic dict
        return {
            'python_type': 'Dict[str, Any]',
            'inline_model': None
        }

    def _extract_security_schemes(self, spec: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extract security schemes from OpenAPI specification.

        Converts securitySchemes to a standardized format for code generation.

        Args:
            spec: OpenAPI specification dictionary

        Returns:
            List of security scheme dictionaries with standardized structure
        """
        components = spec.get('components', {})
        security_schemes = components.get('securitySchemes', {})

        if not security_schemes:
            return []

        from core.sanitizer import IdentifierSanitizer

        extracted_schemes = []

        for scheme_name, scheme_def in security_schemes.items():
            # Sanitize scheme name to snake_case for Python variable names
            arg_name = IdentifierSanitizer.to_snake_case(scheme_name)

            scheme_type = scheme_def.get('type', '').lower()

            if scheme_type == 'http':
                # HTTP authentication schemes (Bearer, Basic)
                scheme_info = self._process_http_scheme(arg_name, scheme_def)
                if scheme_info:
                    extracted_schemes.append(scheme_info)

            elif scheme_type == 'apikey':
                # API Key authentication schemes
                scheme_info = self._process_apikey_scheme(arg_name, scheme_def)
                if scheme_info:
                    extracted_schemes.append(scheme_info)

            elif scheme_type == 'oauth2':
                # OAuth2 authentication - support clientCredentials flow
                scheme_info = self._process_oauth2_scheme(arg_name, scheme_def)
                if scheme_info:
                    extracted_schemes.extend(scheme_info)  # OAuth2 returns multiple items

            else:
                # Unknown scheme type - skip with warning
                print(f"Warning: Unknown security scheme type '{scheme_type}' for '{scheme_name}' - skipped")

        return extracted_schemes

    def _process_http_scheme(self, arg_name: str, scheme_def: Dict[str, Any]) -> Dict[str, Any]:
        """Process HTTP authentication scheme (Bearer, Basic)."""
        scheme = scheme_def.get('scheme', '').lower()

        if scheme == 'bearer':
            return {
                'arg_name': arg_name,
                'type': 'http',
                'scheme': 'bearer',
                'target': 'header',
                'key': 'Authorization',
                'format': 'Bearer {}'
            }

        elif scheme == 'basic':
            return {
                'arg_name': arg_name,
                'type': 'http',
                'scheme': 'basic',
                'target': 'header',
                'key': 'Authorization',
                'format': 'Basic {}'
            }

        else:
            print(f"Warning: Unsupported HTTP scheme '{scheme}' for '{arg_name}' - skipped")
            return None

    def _process_apikey_scheme(self, arg_name: str, scheme_def: Dict[str, Any]) -> Dict[str, Any]:
        """Process API Key authentication scheme."""
        key_location = scheme_def.get('in', '').lower()
        key_name = scheme_def.get('name', '')

        if not key_name:
            print(f"Warning: API Key scheme '{arg_name}' missing 'name' field - skipped")
            return None

        if key_location == 'header':
            return {
                'arg_name': arg_name,
                'type': 'apiKey',
                'target': 'header',
                'key': key_name,
                'format': '{}'
            }

        elif key_location == 'cookie':
            return {
                'arg_name': arg_name,
                'type': 'apiKey',
                'target': 'cookie',
                'key': key_name,
                'format': '{}'
            }

        elif key_location == 'query':
            # Support query parameters via before_request hook
            return {
                'arg_name': arg_name,
                'type': 'apiKey',
                'target': 'query',
                'key': key_name,
                'format': '{}'
            }

        else:
            print(f"Warning: Unknown API Key location '{key_location}' for '{arg_name}' - skipped")
            return None

    def _process_oauth2_scheme(self, arg_name: str, scheme_def: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Process OAuth2 authentication scheme."""
        flows = scheme_def.get('flows', {})

        # Check for clientCredentials flow
        if 'clientCredentials' in flows:
            # OAuth2 clientCredentials requires client_id and client_secret
            return [
                {
                    'arg_name': 'client_id',
                    'type': 'oauth2_creds',
                    'target': 'oauth2',
                    'key': 'client_id',
                    'format': '{}'
                },
                {
                    'arg_name': 'client_secret',
                    'type': 'oauth2_creds',
                    'target': 'oauth2',
                    'key': 'client_secret',
                    'format': '{}'
                }
            ]

        # Other OAuth2 flows not supported yet
        supported_flows = list(flows.keys()) if flows else []
        print(f"Warning: OAuth2 flows {supported_flows} not supported for '{arg_name}' - only clientCredentials is supported")
        return []

    def _deduplicate_function_names(self, operations: List[Dict[str, Any]]) -> None:
        """
        Deduplicate function names to prevent method overrides in generated code.

        This method ensures that each operation has a unique function name by adding
        numerical suffixes to duplicate names (e.g., list_players_1, list_players_2).

        IMPORTANT: This only changes the Python method name (func_name), not the
        response model names which should remain based on operationId.
        """
        from core.sanitizer import IdentifierSanitizer

        # Step 1: Generate function names for all operations
        for operation in operations:
            operation_id = operation.get('operation_id', 'operation')
            func_name = IdentifierSanitizer.to_snake_case(operation_id)
            operation['func_name'] = func_name

        # Step 2: Track name usage and resolve conflicts
        name_counter = {}

        for operation in operations:
            original_func_name = operation['func_name']

            if original_func_name not in name_counter:
                # First occurrence - register and continue
                name_counter[original_func_name] = 1
            else:
                # Collision detected - generate unique name with suffix
                count = name_counter[original_func_name]
                new_func_name = f"{original_func_name}_{count}"

                # Ensure the new name is also unique (handle potential cascading collisions)
                while new_func_name in name_counter:
                    count += 1
                    new_func_name = f"{original_func_name}_{count}"

                # Update the operation with the unique function name
                operation['func_name'] = new_func_name

                # Register both the new name and increment the counter for the original
                name_counter[new_func_name] = 1
                name_counter[original_func_name] = count + 1

        # Step 3: Validate uniqueness (optional debug check)
        # used_names = set()
        # for operation in operations:
        #     func_name = operation['func_name']
        #     if func_name in used_names:
        #         print(f"ERROR: Deduplication failed - '{func_name}' is still duplicated!")
        #     used_names.add(func_name)
