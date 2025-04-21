import pytest
from unittest.mock import patch, MagicMock, mock_open, call
import os
import base64

# Import the module to test AFTER potentially patching builtins if needed
# For now, direct import is fine.
from app import ai_services, database, create_app
from app.plugins import web_search

# --- Fixtures ---


@pytest.fixture(scope="function", autouse=True)
def reset_gemini_configured():
    """Ensures gemini_configured is reset before/after each test."""
    original_state = ai_services.gemini_configured
    ai_services.gemini_configured = False  # Start unconfigured
    yield
    ai_services.gemini_configured = original_state  # Restore original state if needed


@pytest.fixture
def app():
    """Create and configure a new app instance for each test."""
    # Mock configuration values
    app = create_app(
        {
            "TESTING": True,
            "API_KEY": "test-api-key",
            "SUMMARY_MODEL": "gemini-test-summary-model",
            "DEFAULT_MODEL": "gemini-test-default-model",
            "GEMINI_REQUEST_TIMEOUT": 10,
            # Add other necessary config mocks if needed
        }
    )
    return app


@pytest.fixture
def client(app):
    """A test client for the app."""
    return app.test_client()


@pytest.fixture
def runner(app):
    """A test runner for the app's Click commands."""
    return app.test_cli_runner()


@pytest.fixture
def app_context(app):
    """Provides the Flask application context."""
    with app.app_context():
        yield


@pytest.fixture
def mock_genai():
    """Mocks the google.generativeai library."""
    with patch("app.ai_services.genai", autospec=True) as mock_genai_lib:
        # Mock the configure function
        mock_genai_lib.configure = MagicMock()

        # Mock the GenerativeModel class and its methods
        mock_model_instance = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "Mocked AI Response"
        mock_response.parts = [
            MagicMock(text="Mocked AI Response")
        ]  # Ensure parts exist
        mock_response.prompt_feedback = None  # Default to no blocking
        mock_model_instance.generate_content.return_value = mock_response
        mock_genai_lib.GenerativeModel.return_value = mock_model_instance

        # Mock the file upload API
        mock_uploaded_file = MagicMock()
        mock_uploaded_file.uri = "mock://uploaded/file/uri"
        mock_genai_lib.upload_file.return_value = mock_uploaded_file

        yield mock_genai_lib


@pytest.fixture
def mock_db():
    """Mocks the app.database module functions."""
    with patch("app.ai_services.database", autospec=True) as mock_db_module:
        # Setup default return values for commonly used functions
        mock_db_module.get_file_details_from_db.return_value = {
            "id": 1,
            "filename": "test.txt",
            "mimetype": "text/plain",
            "content": b"Test file content",
            "has_summary": False,
            "summary": None,
        }
        mock_db_module.get_chat_details_from_db.return_value = {
            "id": 1,
            "model_name": "gemini-test-default-model",
        }
        mock_db_module.get_chat_history_from_db.return_value = []
        mock_db_module.save_summary_in_db.return_value = True
        mock_db_module.add_message_to_db.return_value = True
        yield mock_db_module


@pytest.fixture
def mock_tempfile():
    """Mocks tempfile.NamedTemporaryFile and os.remove."""
    mock_file = MagicMock()
    mock_file.__enter__.return_value.name = "/tmp/fake_temp_file_123"
    mock_file.__enter__.return_value.write = MagicMock()

    with patch(
        "app.ai_services.tempfile.NamedTemporaryFile", return_value=mock_file
    ) as mock_ntf, patch("app.ai_services.os.remove") as mock_remove, patch(
        "app.ai_services.os.path.exists", return_value=True
    ) as mock_exists:  # Assume file exists for removal attempt
        yield {
            "mock_ntf": mock_ntf,
            "mock_remove": mock_remove,
            "mock_exists": mock_exists,
        }


@pytest.fixture
def mock_web_search():
    """Mocks the web search functionality."""
    with patch("app.ai_services.perform_web_search") as mock_search:
        mock_search.return_value = ["Web search result 1", "Web search result 2"]
        yield mock_search


# --- Test Cases ---


# == Test configure_gemini ==
def test_configure_gemini_success(app, mock_genai):
    """Test successful configuration with API key."""
    with app.app_context():
        result = ai_services.configure_gemini(app)
        assert result is True
        assert ai_services.gemini_configured is True
        mock_genai.configure.assert_called_once_with(api_key="test-api-key")


def test_configure_gemini_no_key(app, mock_genai):
    """Test configuration failure without API key."""
    app.config["API_KEY"] = None
    with app.app_context():
        result = ai_services.configure_gemini(app)
        assert result is False
        assert ai_services.gemini_configured is False
        mock_genai.configure.assert_not_called()


def test_configure_gemini_api_error(app, mock_genai):
    """Test configuration failure when genai.configure raises an error."""
    mock_genai.configure.side_effect = Exception("API Configuration Error")
    with app.app_context():
        result = ai_services.configure_gemini(app)
        assert result is False
        assert ai_services.gemini_configured is False
        mock_genai.configure.assert_called_once_with(api_key="test-api-key")


# == Test generate_summary ==
async def test_generate_summary_not_configured(app_context):
    """Test generate_summary when Gemini is not configured."""
    ai_services.gemini_configured = False
    result = await ai_services.generate(summary(1))
    assert result == "[Error: AI model not configured]"


async def test_generate_summary_file_not_found(app_context, mock_db):
    """Test generate_summary when file details are not found."""
    ai_services.gemini_configured = True
    mock_db.get_file_details_from_db.return_value = None
    result = await ai_services.generate(summary(1))
    assert result == "[Error: File content not found]"
    mock_db.get_file_details_from_db.assert_called_once_with(1, include_content=True)


async def test_generate_summary_text_file(app_context, mock_genai, mock_db):
    """Test summary generation for a text file."""
    ai_services.gemini_configured = True
    mock_db.get_file_details_from_db.return_value = {
        "filename": "report.txt",
        "mimetype": "text/plain",
        "content": b"This is the content of the text file.",
    }
    mock_genai.GenerativeModel.return_value.generate_content.return_value.text = (
        "Text Summary"
    )

    result = await ai_services.generate(summary(1))

    assert result == "Text Summary"
    mock_db.get_file_details_from_db.assert_called_once_with(1, include_content=True)
    mock_genai.GenerativeModel.assert_called_once_with("gemini-test-summary-model")
    expected_prompt = "Please provide a concise summary of the following text content from the file named 'report.txt':\n\nThis is the content of the text file."
    mock_genai.GenerativeModel.return_value.generate_content.assert_called_once_with(
        [expected_prompt], request_options={"timeout": 10}
    )
    mock_genai.upload_file.assert_not_called()  # Should not upload for text


async def test_generate_summary_image_file(
    app_context, mock_genai, mock_db, mock_tempfile
):
    """Test summary generation for an image file (requires upload)."""
    ai_services.gemini_configured = True
    mock_db.get_file_details_from_db.return_value = {
        "filename": "logo.png",
        "mimetype": "image/png",
        "content": b"fakeimagedata",
    }
    mock_genai.GenerativeModel.return_value.generate_content.return_value.text = (
        "Image Summary"
    )
    mock_uploaded_file = MagicMock(uri="mock://image/uri")
    mock_genai.upload_file.return_value = mock_uploaded_file

    result = await ai_services.generate(summary(1))

    assert result == "Image Summary"
    mock_db.get_file_details_from_db.assert_called_once_with(1, include_content=True)
    mock_tempfile["mock_ntf"].assert_called_once()  # Check temp file created
    mock_tempfile["mock_ntf"]().__enter__().write.assert_called_once_with(
        b"fakeimagedata"
    )
    mock_genai.upload_file.assert_called_once_with(
        path="/tmp/fake_temp_file_123", display_name="logo.png", mime_type="image/png"
    )
    mock_genai.GenerativeModel.assert_called_once_with("gemini-test-summary-model")
    expected_prompt = "Please provide a concise summary of the attached file named 'logo.png'. Focus on the main points and key information."
    mock_genai.GenerativeModel.return_value.generate_content.assert_called_once_with(
        [expected_prompt, mock_uploaded_file], request_options={"timeout": 10}
    )
    mock_tempfile["mock_remove"].assert_called_once_with(
        "/tmp/fake_temp_file_123"
    )  # Check temp file removed


async def test_generate_summary_unsupported_type(app_context, mock_db):
    """Test summary generation for an unsupported file type."""
    ai_services.gemini_configured = True
    mock_db.get_file_details_from_db.return_value = {
        "filename": "archive.zip",
        "mimetype": "application/zip",
        "content": b"zipdata",
    }
    result = await ai_services.generate(summary(1))
    assert result == "[Summary generation not supported for this file type]"


async def test_generate_summary_upload_error(
    app_context, mock_genai, mock_db, mock_tempfile
):
    """Test handling of errors during file upload for summary."""
    ai_services.gemini_configured = True
    mock_db.get_file_details_from_db.return_value = {
        "filename": "document.pdf",
        "mimetype": "application/pdf",
        "content": b"pdfdata",
    }
    mock_genai.upload_file.side_effect = Exception("Upload Failed")

    result = await ai_services.generate(summary(1))

    assert result.startswith("[Error preparing file for summary: Upload Failed]")
    mock_tempfile["mock_ntf"].assert_called_once()
    mock_genai.upload_file.assert_called_once()  # Attempted upload
    mock_genai.GenerativeModel.return_value.generate_content.assert_not_called()  # Did not call generate
    mock_tempfile["mock_remove"].assert_called_once_with(
        "/tmp/fake_temp_file_123"
    )  # Ensure cleanup still happens


async def test_generate_summary_api_error(app_context, mock_genai, mock_db):
    """Test handling of API errors during summary generation."""
    ai_services.gemini_configured = True
    mock_db.get_file_details_from_db.return_value = {
        "filename": "notes.txt",
        "mimetype": "text/plain",
        "content": b"Some notes.",
    }
    mock_genai.GenerativeModel.return_value.generate_content.side_effect = Exception(
        "API Call Failed"
    )

    result = await ai_services.generate(summary(1))
    assert result == "[Error generating summary via API: API Call Failed]"


async def test_generate_summary_api_blocked(app_context, mock_genai, mock_db):
    """Test handling of API blocking errors during summary generation."""
    ai_services.gemini_configured = True
    mock_db.get_file_details_from_db.return_value = {
        "filename": "blocked.txt",
        "mimetype": "text/plain",
        "content": b"Sensitive content.",
    }
    # Simulate a blocked prompt error
    mock_genai.GenerativeModel.return_value.generate_content.side_effect = Exception(
        "prompt was blocked due to safety"
    )

    result = await ai_services.generate(summary(1))
    assert result == "[Error: Summary generation blocked due to safety settings]"


# == Test get_or_generate_summary ==
async def test_get_or_generate_summary_exists(app_context, mock_db, mock_genai):
    """Test retrieving an existing valid summary."""
    ai_services.gemini_configured = True  # Needed if generation fallback occurs
    mock_db.get_file_details_from_db.return_value = {
        "id": 1,
        "filename": "test.txt",
        "mimetype": "text/plain",
        "has_summary": True,
        "summary": "Existing Summary Text",
        # No content needed if summary exists
    }
    result = await ai_services.get_or_generate_summary(1)
    assert result == "Existing Summary Text"
    mock_db.get_file_details_from_db.assert_called_once_with(
        1
    )  # Called without include_content
    mock_genai.GenerativeModel.return_value.generate_content.assert_not_called()  # Should not generate
    mock_db.save_summary_in_db.assert_not_called()  # Should not save


async def test_get_or_generate_summary_generate_new(app_context, mock_db, mock_genai):
    """Test generating a new summary when none exists."""
    ai_services.gemini_configured = True
    # First call to get_file_details (no content)
    mock_db.get_file_details_from_db.side_effect = [
        {
            "id": 1,
            "filename": "new.txt",
            "mimetype": "text/plain",
            "has_summary": False,
            "summary": None,
        },
        # Second call inside generate_summary (with content)
        {
            "id": 1,
            "filename": "new.txt",
            "mimetype": "text/plain",
            "content": b"Generate this.",
            "has_summary": False,
            "summary": None,
        },
    ]
    mock_genai.GenerativeModel.return_value.generate_content.return_value.text = (
        "Newly Generated Summary"
    )

    result = await ai_services.get_or_generate_summary(1)

    assert result == "Newly Generated Summary"
    assert mock_db.get_file_details_from_db.call_count == 2
    mock_db.get_file_details_from_db.assert_has_calls(
        [call(1), call(1, include_content=True)]
    )
    mock_genai.GenerativeModel.return_value.generate_content.assert_called_once()  # Generation happened
    mock_db.save_summary_in_db.assert_called_once_with(
        1, "Newly Generated Summary"
    )  # Saved the new summary


async def test_get_or_generate_summary_generate_new_save_fails(
    app_context, mock_db, mock_genai
):
    """Test generating a new summary when saving it fails."""
    ai_services.gemini_configured = True
    mock_db.get_file_details_from_db.side_effect = [
        {
            "id": 1,
            "filename": "new.txt",
            "mimetype": "text/plain",
            "has_summary": False,
            "summary": None,
        },
        {
            "id": 1,
            "filename": "new.txt",
            "mimetype": "text/plain",
            "content": b"Generate this.",
            "has_summary": False,
            "summary": None,
        },
    ]
    mock_genai.GenerativeModel.return_value.generate_content.return_value.text = (
        "Generated But Not Saved"
    )
    mock_db.save_summary_in_db.return_value = False  # Simulate save failure

    result = await ai_services.get_or_generate_summary(1)

    assert (
        result == "Generated But Not Saved"
    )  # Should still return the generated summary
    mock_db.save_summary_in_db.assert_called_once_with(1, "Generated But Not Saved")


async def test_get_or_generate_summary_file_not_found(app_context, mock_db):
    """Test get_or_generate_summary when file details are not found initially."""
    mock_db.get_file_details_from_db.return_value = None
    result = await ai_services.get_or_generate_summary(99)
    assert result == "[Error: File details not found]"
    mock_db.get_file_details_from_db.assert_called_once_with(99)


# == Test generate_search_query ==
async def test_generate_search_query_success(app_context, mock_genai):
    """Test successful generation of a search query."""
    ai_services.gemini_configured = True
    user_message = "Tell me about the weather in London tomorrow."
    mock_genai.GenerativeModel.return_value.generate_content.return_value.text = (
        " London weather forecast tomorrow "  # With extra spaces
    )

    result = await ai_services.generate_search_query(user_message)

    assert result == "London weather forecast tomorrow"  # Check cleaning
    mock_genai.GenerativeModel.assert_called_once_with(
        "gemini-test-summary-model"
    )  # Uses summary model
    generate_call = mock_genai.GenerativeModel.return_value.generate_content
    assert generate_call.call_count == 1
    # Check prompt contains user message
    assert user_message in generate_call.call_args[0][0]

    # Check that generate_content was called with a generation_config argument
    assert "generation_config" in generate_call.call_args[1]
    gen_config_arg = generate_call.call_args[1]["generation_config"]

    # Assert that the passed config object is of the expected type (mocked type)
    # Note: Due to the broad mocking of 'genai', gen_config_arg is likely a MagicMock itself.
    # We can't easily assert the *values* it was created with in this setup without
    # more complex patching or checking the call to GenerationConfig *before* generate_content.
    # For now, we verify *a* config object was passed.
    # The mock created by autospec for GenerationConfig is likely NonCallable
    assert isinstance(
        gen_config_arg, unittest.mock.NonCallableMagicMock
    )  # Check it's the correct mock type
    # A more specific check if genai.types wasn't fully mocked:
    # assert isinstance(gen_config_arg, genai.types.GenerationConfig)


async def test_generate_search_query_cleaning(app_context, mock_genai):
    """Test cleaning of LLM output for search query."""
    ai_services.gemini_configured = True
    user_message = "Search query test"
    # Simulate various messy outputs
    test_cases = [
        '"clean query"',
        "  query with spaces  ",
        "Search Query: actual query",
        "query: another query",
        "- list item query",
        "* bullet query",
        "1. numbered query",
    ]
    expected_results = [
        "clean query",
        "query with spaces",
        "actual query",
        "another query",
        "list item query",
        "bullet query",
        "numbered query",
    ]

    for i, messy_output in enumerate(test_cases):
        mock_genai.GenerativeModel.return_value.generate_content.reset_mock()  # Reset for next iteration
        mock_genai.GenerativeModel.return_value.generate_content.return_value.text = (
            messy_output
        )
        result = await ai_services.generate_search_query(user_message)
        assert result == expected_results[i], f"Failed on case: {messy_output}"


async def test_generate_search_query_not_configured(app_context):
    """Test generate_search_query when not configured."""
    ai_services.gemini_configured = False
    result = await ai_services.generate_search_query("Any message")
    assert result is None


async def test_generate_search_query_empty_message(app_context):
    """Test generate_search_query with an empty user message."""
    ai_services.gemini_configured = True
    result = await ai_services.generate_search_query("")
    assert result is None
    result = await ai_services.generate_search_query("   ")
    assert result is None


async def test_generate_search_query_api_error(app_context, mock_genai):
    """Test generate_search_query handling API errors."""
    ai_services.gemini_configured = True
    mock_genai.GenerativeModel.return_value.generate_content.side_effect = Exception(
        "API Error"
    )
    result = await ai_services.generate_search_query("A message", max_retries=1)
    assert result is None
    # Called once for initial try, once for retry
    assert mock_genai.GenerativeModel.return_value.generate_content.call_count == 2


async def test_generate_search_query_blocked(app_context, mock_genai):
    """Test generate_search_query when the prompt is blocked."""
    ai_services.gemini_configured = True
    mock_response = MagicMock()
    mock_response.text = ""  # Blocked responses often have empty text
    mock_response.parts = []  # No parts when blocked
    mock_response.prompt_feedback = MagicMock(block_reason="SAFETY")
    mock_genai.GenerativeModel.return_value.generate_content.return_value = (
        mock_response
    )

    result = await ai_services.generate_search_query("Risky message", max_retries=1)
    assert result is None
    # Should not retry if blocked
    assert mock_genai.GenerativeModel.return_value.generate_content.call_count == 1


async def test_generate_search_query_empty_response(app_context, mock_genai):
    """Test generate_search_query when the LLM returns an empty string."""
    ai_services.gemini_configured = True
    mock_genai.GenerativeModel.return_value.generate_content.return_value.text = (
        "  "  # Empty after strip
    )

    result = await ai_services.generate_search_query("A message", max_retries=1)
    assert result is None
    # Should not retry if LLM returns empty
    assert mock_genai.GenerativeModel.return_value.generate_content.call_count == 1


# == Test generate_chat_response ==


# Helper to create mock session file data
def create_mock_session_file(
    filename="session.txt", mimetype="text/plain", content=b"Session data"
):
    encoded_content = base64.b64encode(content).decode("utf-8")
    return {
        "filename": filename,
        "mimetype": mimetype,
        "content": f"data:{mimetype};base64,{encoded_content}",
    }


async def test_generate_chat_response_not_configured(app_context):
    """Test chat response when Gemini is not configured."""
    ai_services.gemini_configured = False
    result = await ai_services.generate_chat_response(1, "Hello", [], None, [])
    assert result == "[Error: Gemini API Key not configured]"


async def test_generate_chat_response_chat_not_found(app_context, mock_db):
    """Test chat response when chat details are not found."""
    ai_services.gemini_configured = True
    mock_db.get_chat_details_from_db.return_value = None
    result = await ai_services.generate_chat_response(99, "Hello", [], None, [])
    assert result == "[Error: Chat session not found]"
    mock_db.get_chat_details_from_db.assert_called_once_with(99)


async def test_generate_chat_response_basic(app_context, mock_genai, mock_db):
    """Test basic chat response generation."""
    ai_services.gemini_configured = True
    chat_id = 5
    user_message = "Hi Gemini!"
    mock_db.get_chat_details_from_db.return_value = {
        "id": chat_id,
        "model_name": "gemini-test-default-model",
    }
    mock_db.get_chat_history_from_db.return_value = [
        {"role": "user", "content": "Previous message"},
        {"role": "assistant", "content": "Previous response"},
    ]
    mock_genai.GenerativeModel.return_value.generate_content.return_value.text = (
        "Hello there!"
    )

    result = await ai_services.generate_chat_response(chat_id, user_message, [], None, [])

    assert result == "Hello there!"
    # Check DB interactions
    mock_db.add_message_to_db.assert_has_calls(
        [
            call(chat_id, "user", user_message),
            call(chat_id, "assistant", "Hello there!"),
        ]
    )
    mock_db.get_chat_history_from_db.assert_called_once_with(chat_id, limit=20)
    # Check Gemini call
    mock_genai.GenerativeModel.assert_called_once_with("gemini-test-default-model")
    generate_call = mock_genai.GenerativeModel.return_value.generate_content
    assert generate_call.call_count == 1
    # Verify history and new message passed to Gemini
    expected_gemini_context = [
        {"role": "user", "parts": ["Previous message"]},
        {"role": "model", "parts": ["Previous response"]},
        {"role": "user", "parts": [user_message]},  # New user message added
    ]
    assert generate_call.call_args[0][0] == expected_gemini_context
    assert generate_call.call_args[1]["request_options"] == {"timeout": 10}


async def test_generate_chat_response_with_calendar(app_context, mock_genai, mock_db):
    """Test chat response with calendar context."""
    ai_services.gemini_configured = True
    chat_id = 6
    user_message = "What's my schedule?"
    calendar_context = "Event: Meeting at 10 AM"
    mock_db.get_chat_details_from_db.return_value = {
        "id": chat_id,
        "model_name": "gemini-test-default-model",
    }
    mock_db.get_chat_history_from_db.return_value = []
    mock_genai.GenerativeModel.return_value.generate_content.return_value.text = (
        "You have a meeting."
    )

    result = await ai_services.generate_chat_response(
        chat_id, user_message, [], calendar_context, []
    )

    assert result == "You have a meeting."
    mock_db.add_message_to_db.assert_has_calls(
        [
            call(chat_id, "user", user_message),
            call(chat_id, "assistant", "You have a meeting."),
        ]
    )
    # Check Gemini call context
    generate_call = mock_genai.GenerativeModel.return_value.generate_content
    expected_gemini_context = [
        {
            "role": "user",
            "parts": [
                "--- Start Calendar Context ---",
                calendar_context,
                "--- End Calendar Context ---",
                user_message,
            ],
        }
    ]
    assert generate_call.call_args[0][0] == expected_gemini_context


async def test_generate_chat_response_with_session_file(
    app_context, mock_genai, mock_db, mock_tempfile
):
    """Test chat response with a session file."""
    ai_services.gemini_configured = True
    chat_id = 7
    user_message = "Summarize the session file."
    session_file_data = create_mock_session_file(
        filename="session_doc.txt", content=b"Session content"
    )
    mock_db.get_chat_details_from_db.return_value = {
        "id": chat_id,
        "model_name": "gemini-test-default-model",
    }
    mock_db.get_chat_history_from_db.return_value = []
    mock_genai.GenerativeModel.return_value.generate_content.return_value.text = (
        "Session Summary"
    )
    mock_uploaded_file = MagicMock(uri="mock://session/uri")
    mock_genai.upload_file.return_value = mock_uploaded_file

    result = await ai_services.generate_chat_response(
        chat_id, user_message, [], None, [session_file_data]
    )

    assert result == "Session Summary"
    # Check temp file usage and upload
    mock_tempfile["mock_ntf"].assert_called_once()
    mock_tempfile["mock_ntf"]().__enter__().write.assert_called_once_with(
        b"Session content"
    )
    mock_genai.upload_file.assert_called_once_with(
        path="/tmp/fake_temp_file_123",
        display_name="session_session_doc.txt",
        mime_type="text/plain",
    )
    # Check DB save (user message should NOT contain session file info)
    mock_db.add_message_to_db.assert_has_calls(
        [
            call(chat_id, "user", user_message),
            call(chat_id, "assistant", "Session Summary"),
        ]
    )
    # Check Gemini call context
    generate_call = mock_genai.GenerativeModel.return_value.generate_content
    expected_gemini_context = [
        {
            "role": "user",
            "parts": [mock_uploaded_file, user_message],  # Uploaded session file part
        }
    ]
    assert generate_call.call_args[0][0] == expected_gemini_context
    mock_tempfile["mock_remove"].assert_called_once_with(
        "/tmp/fake_temp_file_123"
    )  # Check cleanup


async def test_generate_chat_response_with_permanent_file_full(
    app_context, mock_genai, mock_db, mock_tempfile
):
    """Test chat response with a permanently attached file (full content)."""
    ai_services.gemini_configured = True
    chat_id = 8
    user_message = "Analyze the attached file."
    file_id = 10
    attached_files = [{"id": file_id, "type": "full"}]
    mock_db.get_chat_details_from_db.return_value = {
        "id": chat_id,
        "model_name": "gemini-test-default-model",
    }
    mock_db.get_chat_history_from_db.return_value = []
    mock_db.get_file_details_from_db.return_value = {  # Mock for the permanent file
        "id": file_id,
        "filename": "permanent.pdf",
        "mimetype": "application/pdf",
        "content": b"permanent pdf data",
        "has_summary": False,
        "summary": None,
    }
    mock_genai.GenerativeModel.return_value.generate_content.return_value.text = (
        "File Analysis"
    )
    mock_uploaded_file = MagicMock(uri="mock://permanent/uri")
    mock_genai.upload_file.return_value = mock_uploaded_file

    result = await ai_services.generate_chat_response(
        chat_id, user_message, attached_files, None, []
    )

    assert result == "File Analysis"
    # Check temp file usage and upload for permanent file
    mock_tempfile["mock_ntf"].assert_called_once()
    mock_tempfile["mock_ntf"]().__enter__().write.assert_called_once_with(
        b"permanent pdf data"
    )
    mock_genai.upload_file.assert_called_once_with(
        path="/tmp/fake_temp_file_123",
        display_name="permanent.pdf",
        mime_type="application/pdf",
    )
    # Check DB save (user message SHOULD contain permanent file marker)
    expected_user_history = "[Attached File: 'permanent.pdf' (ID: 10, Type: full)]\nAnalyze the attached file."
    mock_db.add_message_to_db.assert_has_calls(
        [
            call(chat_id, "user", expected_user_history),
            call(chat_id, "assistant", "File Analysis"),
        ]
    )
    # Check Gemini call context
    generate_call = mock_genai.GenerativeModel.return_value.generate_content
    expected_gemini_context = [
        {
            "role": "user",
            "parts": [mock_uploaded_file, user_message],  # Uploaded permanent file part
        }
    ]
    assert generate_call.call_args[0][0] == expected_gemini_context
    mock_tempfile["mock_remove"].assert_called_once_with(
        "/tmp/fake_temp_file_123"
    )  # Check cleanup


async def test_generate_chat_response_with_permanent_file_summary(
    app_context, mock_genai, mock_db
):
    """Test chat response with a permanently attached file (summary)."""
    ai_services.gemini_configured = True
    chat_id = 9
    user_message = "What does the summary say?"
    file_id = 11
    attached_files = [{"id": file_id, "type": "summary"}]
    file_details_dict = {
        "id": file_id,
        "filename": "report.docx",
        "mimetype": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "has_summary": True,
        "summary": "Existing Report Summary",
    }

    mock_db.get_chat_details_from_db.return_value = {
        "id": chat_id,
        "model_name": "gemini-test-default-model",
    }
    mock_db.get_chat_history_from_db.return_value = []

    # Mock get_file_details: Provide return values for BOTH calls without include_content
    mock_db.get_file_details_from_db.side_effect = [
        file_details_dict,  # For the call in generate_chat_response (~line 289)
        file_details_dict,  # For the call in get_or_generate_summary (~line 111)
    ]
    mock_genai.GenerativeModel.return_value.generate_content.return_value.text = (
        "Summary Response"
    )

    result = await ai_services.generate_chat_response(
        chat_id, user_message, attached_files, None, []
    )

    assert result == "Summary Response"

    # Check get_file_details calls
    # It should be called twice with just the file_id
    expected_calls_get_details = [call(file_id), call(file_id)]
    # Use assert_has_calls to check for these specific calls in sequence (or any_order=True if order doesn't matter)
    # Note: Depending on exact execution, other calls might occur *after* these.
    # assert_has_calls checks if the sequence exists within the call list.
    mock_db.get_file_details_from_db.assert_has_calls(
        expected_calls_get_details, any_order=False
    )  # Adjust any_order if needed

    # Ensure it wasn't called with include_content=True
    for call_args in mock_db.get_file_details_from_db.call_args_list:
        # Check the keyword arguments specifically
        if call_args.kwargs.get("include_content") is True:
            pytest.fail(
                f"get_file_details_from_db called with include_content=True for summary type file ID {file_id}"
            )

    # Check DB save (user message SHOULD contain permanent file marker)
    expected_user_history = f"[Attached File: '{file_details_dict['filename']}' (ID: {file_id}, Type: summary)]\n{user_message}"
    mock_db.add_message_to_db.assert_has_calls(
        [
            call(chat_id, "user", expected_user_history),
            call(chat_id, "assistant", "Summary Response"),
        ],
        any_order=False,
    )  # Keep any_order=False as the order matters here


async def test_generate_chat_response_with_web_search(
    app_context, mock_genai, mock_db, mock_web_search
):
    """Test chat response with web search enabled."""
    ai_services.gemini_configured = True
    chat_id = 10
    user_message = "Search the web for recent AI news."
    mock_db.get_chat_details_from_db.return_value = {
        "id": chat_id,
        "model_name": "gemini-test-default-model",
    }
    mock_db.get_chat_history_from_db.return_value = []
    mock_genai.GenerativeModel.return_value.generate_content.side_effect = [
        MagicMock(text="recent AI news search query"),  # For generate_search_query
        MagicMock(text="Web Search Enhanced Response"),  # For final chat response
    ]
    mock_web_search.return_value = ["AI News Result 1", "AI News Result 2"]

    result = await ai_services.generate_chat_response(
        chat_id, user_message, [], None, [], enable_web_search=True
    )

    assert result == "Web Search Enhanced Response"
    # Check generate_search_query was called
    assert (
        mock_genai.GenerativeModel.return_value.generate_content.call_count == 2
    )  # Once for query, once for chat
    # Check perform_web_search was called
    mock_web_search.assert_called_once_with("recent AI news search query")
    # Check DB save (user message SHOULD contain web search marker)
    expected_user_history = "[Web search performed]\nSearch the web for recent AI news."
    mock_db.add_message_to_db.assert_has_calls(
        [
            call(chat_id, "user", expected_user_history),
            call(chat_id, "assistant", "Web Search Enhanced Response"),
        ]
    )
    # Check Gemini call context for the chat response
    chat_generate_call = (
        mock_genai.GenerativeModel.return_value.generate_content.call_args_list[1]
    )  # Second call
    expected_web_parts = [
        "--- Start Web Search Results ---",
        "The following information was retrieved from a web search and may contain inaccuracies. Please verify the information before relying on it.",
        "AI News Result 1\nAI News Result 2",
        "--- End Web Search Results ---",
    ]
    expected_gemini_context = [
        {"role": "user", "parts": expected_web_parts + [user_message]}
    ]
    assert chat_generate_call[0][0] == expected_gemini_context


async def test_generate_chat_response_web_search_fails(
    app_context, mock_genai, mock_db, mock_web_search
):
    """Test chat response when web search itself fails."""
    ai_services.gemini_configured = True
    chat_id = 11
    user_message = "Search for something complex."
    mock_db.get_chat_details_from_db.return_value = {
        "id": chat_id,
        "model_name": "gemini-test-default-model",
    }
    mock_db.get_chat_history_from_db.return_value = []
    mock_genai.GenerativeModel.return_value.generate_content.side_effect = [
        MagicMock(text="complex search query"),  # For generate_search_query
        MagicMock(text="Response without web results"),  # For final chat response
    ]
    mock_web_search.return_value = [
        "[System Error: Search API timed out]"
    ]  # Simulate error from search function

    result = await ai_services.generate_chat_response(
        chat_id, user_message, [], None, [], enable_web_search=True
    )

    assert result == "Response without web results"
    mock_web_search.assert_called_once_with("complex search query")
    # Check DB save (user message SHOULD contain web search failed marker)
    expected_user_history = "[Web search failed]\nSearch for something complex."
    mock_db.add_message_to_db.assert_has_calls(
        [
            call(chat_id, "user", expected_user_history),
            call(chat_id, "assistant", "Response without web results"),
        ]
    )
    # Check Gemini call context includes the system error message
    chat_generate_call = (
        mock_genai.GenerativeModel.return_value.generate_content.call_args_list[1]
    )
    expected_gemini_context = [
        {
            "role": "user",
            "parts": [
                "[System Error: Search API timed out]",  # Error passed to Gemini
                user_message,
            ],
        }
    ]
    assert chat_generate_call[0][0] == expected_gemini_context


async def test_generate_chat_response_api_error(app_context, mock_genai, mock_db):
    """Test handling of API errors during chat response generation."""
    ai_services.gemini_configured = True
    chat_id = 12
    user_message = "Trigger an error."
    mock_db.get_chat_details_from_db.return_value = {
        "id": chat_id,
        "model_name": "gemini-test-default-model",
    }
    mock_db.get_chat_history_from_db.return_value = []
    mock_genai.GenerativeModel.return_value.generate_content.side_effect = Exception(
        "Chat API Failed"
    )

    result = await ai_services.generate_chat_response(chat_id, user_message, [], None, [])

    assert result == "[Error communicating with AI: Chat API Failed]"
    # Check user message still saved
    mock_db.add_message_to_db.assert_any_call(chat_id, "user", user_message)
    # Check assistant error message saved
    mock_db.add_message_to_db.assert_any_call(
        chat_id, "assistant", "[Error communicating with AI: Chat API Failed]"
    )


# Add more tests for specific error types (429, blocked, timeout, etc.) if needed
# Add tests for file processing errors within generate_chat_response
# Add tests for model fallback logic

# Need this import for the updated test_generate_search_query_success
import unittest.mock
