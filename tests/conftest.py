"""
Pytest fixtures and configuration for ahttp_generator tests.
Provides mock OpenAPI specifications with edge cases for testing.
"""

import pytest
from typing import Dict, Any


@pytest.fixture
def minimal_openapi_spec() -> Dict[str, Any]:
    """Minimal valid OpenAPI 3.x specification."""
    return {
        "openapi": "3.0.0",
        "info": {
            "title": "Test API",
            "version": "1.0.0",
            "description": "A test API specification"
        },
        "servers": [
            {
                "url": "https://api.example.com/v1"
            }
        ],
        "paths": {},
        "components": {
            "schemas": {}
        }
    }


@pytest.fixture
def edge_case_openapi_spec() -> Dict[str, Any]:
    """
    OpenAPI spec with edge cases:
    - Reserved keywords (class, return, import)
    - Circular references
    - Deep nesting
    - Server path variables
    - Parameter references ($ref)
    - Enum parameters
    - Special characters in parameter names
    """
    return {
        "openapi": "3.0.3",
        "info": {
            "title": "Edge Case API",
            "version": "2.0.0",
            "description": "Tests edge cases like reserved keywords and circular refs"
        },
        "servers": [
            {
                "url": "https://{environment}.example.com/{version}",
                "variables": {
                    "environment": {
                        "default": "api",
                        "enum": ["api", "staging", "dev"]
                    },
                    "version": {
                        "default": "v1"
                    }
                }
            }
        ],
        "paths": {
            "/users/{user_id}": {
                "get": {
                    "operationId": "getUser",
                    "summary": "Get user by ID",
                    "description": "Retrieves a user with reserved keyword handling",
                    "parameters": [
                        {
                            "name": "user_id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"}
                        },
                        {
                            "$ref": "#/components/parameters/FilterParameter"
                        },
                        {
                            "name": "class",
                            "in": "query",
                            "required": False,
                            "schema": {"type": "string"}
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "Success",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "$ref": "#/components/schemas/User"
                                    }
                                }
                            }
                        },
                        "404": {
                            "description": "Not Found",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "$ref": "#/components/schemas/Error"
                                    }
                                }
                            }
                        }
                    }
                }
            },
            "/items": {
                "post": {
                    "operationId": "createItem",
                    "summary": "Create item with status enum",
                    "parameters": [
                        {
                            "name": "status",
                            "in": "query",
                            "required": True,
                            "schema": {
                                "type": "string",
                                "enum": ["active", "inactive", "pending"]
                            }
                        }
                    ],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "$ref": "#/components/schemas/Item"
                                }
                            }
                        }
                    },
                    "responses": {
                        "201": {
                            "description": "Created",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "$ref": "#/components/schemas/Item"
                                    }
                                }
                            }
                        }
                    }
                }
            }
        },
        "components": {
            "parameters": {
                "FilterParameter": {
                    "name": "filter[type]",
                    "in": "query",
                    "required": False,
                    "schema": {"type": "string"}
                }
            },
            "schemas": {
                "User": {
                    "type": "object",
                    "description": "User model with circular reference",
                    "required": ["id", "name"],
                    "properties": {
                        "id": {
                            "type": "string",
                            "description": "User ID"
                        },
                        "name": {
                            "type": "string",
                            "description": "User name"
                        },
                        "class": {
                            "type": "string",
                            "description": "User class (reserved keyword)"
                        },
                        "manager": {
                            "$ref": "#/components/schemas/User",
                            "description": "Manager (circular reference)"
                        },
                        "items": {
                            "type": "array",
                            "items": {
                                "$ref": "#/components/schemas/Item"
                            },
                            "description": "User's items"
                        }
                    }
                },
                "Item": {
                    "type": "object",
                    "required": ["id", "name"],
                    "properties": {
                        "id": {
                            "type": "string"
                        },
                        "name": {
                            "type": "string"
                        },
                        "owner": {
                            "$ref": "#/components/schemas/User"
                        },
                        "status": {
                            "type": "string",
                            "enum": ["active", "inactive"]
                        }
                    }
                },
                "Error": {
                    "type": "object",
                    "required": ["code", "message"],
                    "properties": {
                        "code": {
                            "type": "integer"
                        },
                        "message": {
                            "type": "string"
                        },
                        "return": {
                            "type": "string",
                            "description": "Reserved keyword field"
                        }
                    }
                }
            },
            "securitySchemes": {
                "BearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                    "bearerFormat": "JWT"
                }
            }
        }
    }


@pytest.fixture
def deeply_nested_spec() -> Dict[str, Any]:
    """OpenAPI spec with deeply nested object structures."""
    return {
        "openapi": "3.0.0",
        "info": {
            "title": "Nested API",
            "version": "1.0.0"
        },
        "paths": {
            "/nested": {
                "get": {
                    "operationId": "getNested",
                    "responses": {
                        "200": {
                            "description": "Success",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "$ref": "#/components/schemas/Level1"
                                    }
                                }
                            }
                        }
                    }
                }
            }
        },
        "components": {
            "schemas": {
                "Level1": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "level2": {
                            "$ref": "#/components/schemas/Level2"
                        }
                    }
                },
                "Level2": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "level3": {
                            "$ref": "#/components/schemas/Level3"
                        }
                    }
                },
                "Level3": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "data": {
                            "type": "object",
                            "additionalProperties": True
                        }
                    }
                }
            }
        }
    }


@pytest.fixture
def inline_response_spec() -> Dict[str, Any]:
    """OpenAPI spec with inline response schemas."""
    return {
        "openapi": "3.0.0",
        "info": {
            "title": "Inline Response API",
            "version": "1.0.0"
        },
        "paths": {
            "/inline": {
                "get": {
                    "operationId": "getInlineResponse",
                    "responses": {
                        "200": {
                            "description": "Success with inline schema",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "id": {"type": "string"},
                                            "value": {"type": "integer"}
                                        },
                                        "required": ["id"]
                                    }
                                }
                            }
                        }
                    }
                }
            }
        },
        "components": {
            "schemas": {}
        }
    }
