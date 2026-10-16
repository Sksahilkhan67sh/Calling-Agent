"""The generated OpenAPI schema describes the auth views without generator warnings."""

import pytest
from drf_spectacular.generators import SchemaGenerator


@pytest.fixture(scope="module")
def schema():
    return SchemaGenerator().get_schema(request=None, public=True)


def test_auth_security_schemes_are_declared(schema, settings):
    schemes = schema["components"]["securitySchemes"]
    assert schemes["cookieAuth"] == {
        "type": "apiKey",
        "in": "cookie",
        "name": settings.AUTH_ACCESS_COOKIE_NAME,
    }
    enrollment = schemes["enrollmentAuth"]
    assert (enrollment["in"], enrollment["name"]) == ("header", "Authorization")


@pytest.mark.parametrize(
    ("path", "codes"),
    [
        ("/v1/auth/token", {"200", "400", "401", "429"}),
        ("/v1/auth/token/refresh", {"200", "401", "429"}),
        ("/v1/auth/logout", {"204", "403"}),
    ],
)
def test_contract_auth_paths_document_their_responses(schema, path, codes):
    assert set(schema["paths"][path]["post"]["responses"]) == codes


@pytest.mark.parametrize("path", ["/v1/auth/token", "/v1/auth/token/refresh"])
def test_login_and_refresh_declare_no_security_requirement(schema, path):
    # No global requirement exists, so an operation without one is public (the contract's ``security: []``).
    assert "security" not in schema["paths"][path]["post"]
