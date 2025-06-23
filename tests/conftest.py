import pytest
from app import create_app, db as _db # Use _db to avoid conflict with fixture
from app.config import Config

class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:" # Use in-memory SQLite for tests
    # Disable CSRF protection in tests for simplicity if you have it enabled globally
    WTF_CSRF_ENABLED = False
    # Ensure other potentially problematic settings for tests are overridden
    DEBUG = False # Usually set by TESTING = True, but good to be explicit
    # If you have email sending or other external services, disable them here
    # MAIL_SUPPRESS_SEND = True
    AVAILABLE_MODELS = ["test_model_1", "test_model_2", "test_model_default"]
    DEFAULT_MODEL = "test_model_default"


@pytest.fixture(scope='session')
def app():
    """Session-wide test Flask application."""
    # Pass an instance of TestConfig
    _app = create_app(test_config=TestConfig())

    # Establish an application context before running the tests.
    ctx = _app.app_context()
    ctx.push()

    yield _app

    ctx.pop()


@pytest.fixture(scope='function')
def client(app):
    """A test client for the app."""
    return app.test_client()


@pytest.fixture(scope='function')
def db(app):
    """Session-wide test database."""
    # app context is already pushed by the 'app' fixture if it's session-scoped
    # and this db fixture depends on it.
    # If app fixture was function-scoped, we'd need app.app_context().push() here.

    _db.app = app # Associate db with the app
    _db.create_all()

    yield _db

    _db.session.remove() # Ensure session is closed
    _db.drop_all()

# Alias init_database to db for consistency with Flask-SQLAlchemy patterns
# if you prefer to call it init_database, you can keep that name.
# For now, the 'db' fixture handles initialization and teardown.
# If more complex setup/teardown per test is needed, this can be expanded.
