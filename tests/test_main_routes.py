import pytest

def test_health_check(client):
    """Test the /health endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.data.decode() == "OK"

def test_index_route(client, app):
    """Test the / route."""
    # Ensure app context is available if config values are accessed directly
    # The client fixture should handle this, but being explicit can help.
    # with app.app_context():
    response = client.get("/")
    assert response.status_code == 200
    # Check for some content that should be present on the index page
    # For example, if you have a title or a specific HTML element
    assert b"<title>" in response.data # A generic check
    # You can also check for specific config values if they are rendered
    # For example, if default_model is rendered:
    # default_model = app.config.get('DEFAULT_MODEL', '')
    # assert default_model.encode() in response.data
