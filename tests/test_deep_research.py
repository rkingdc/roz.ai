import pytest
import unittest.mock
import json
import concurrent.futures
import os
from flask import current_app, g

# Mock external libraries
import google.genai
from google.genai import types
import requests

# Import the module to be tested
from app import deep_research
from app.plugins import web_search as web_search_plugin
from app import ai_services # For transcribe_pdf_bytes (used in the actual code, but mocked here)
from app import database # For add_message_to_db
from app import socketio as app_socketio # Import the actual socketio instance from app/__init__.py

# Define common mock responses for LLM
MOCK_RESEARCH_PLAN = [
    ["Initial Search", "Find general information about the query."],
    ["Detailed Analysis", "Analyze specific aspects mentioned in the query."]
]

MOCK_WEB_SEARCH_RESULTS = [
    {"title": "Result 1", "link": "http://example.com/page1", "snippet": "Snippet 1"},
    {"title": "Result 2", "link": "http://example.com/page2", "snippet": "Snippet 2"},
]

MOCK_HTML_CONTENT = {
    'type': 'html',
    'content': 'This is the scraped content from an HTML page.',
    'url': 'http://example.com/page1'
}

MOCK_PDF_BYTES = b"%PDF-1.4\n% Some PDF content\n%%EOF"
MOCK_PDF_CONTENT_INFO = {
    'type': 'pdf',
    'content': MOCK_PDF_BYTES,
    'url': 'http://example.com/document.pdf',
    'filename': 'document.pdf'
}
MOCK_TRANSCRIBED_PDF_TEXT = "This is the transcribed text from the PDF document."

# Re-adding definitions for LLM tool call responses
MOCK_LLM_TOOL_CALL_SEARCH = types.GenerateContentResponse(
    candidates=[
        types.Candidate(
            content=types.Content(
                parts=[
                    types.Part(
                        function_call=types.FunctionCall(name="web_search", args={"query": "test query", "num_results": 2})
                    )
                ]
            )
        )
    ]
)

MOCK_LLM_TOOL_CALL_SCRAPE = types.GenerateContentResponse(
    candidates=[
        types.Candidate(
            content=types.Content(
                parts=[
                    types.Part(
                        function_call=types.FunctionCall(name="scrape_url", args={"url": "http://example.com/page1"})
                    )
                ]
            )
        )
    ]
)

MOCK_LLM_TOOL_CALL_SCRAPE_PDF = types.GenerateContentResponse(
    candidates=[
        types.Candidate(
            content=types.Content(
                parts=[
                    types.Part(
                        function_call=types.FunctionCall(name="scrape_url", args={"url": "http://example.com/document.pdf"})
                    )
                ]
            )
        )
    ]
)

MOCK_LLM_FINAL_JSON_OUTPUT_INITIAL_SEARCH = json.dumps([
    "Title: Result 1\nLink: http://example.com/page1\nSnippet: Snippet 1\nContent: This is the scraped content from an HTML page.\n---",
    "Title: Document\nLink: http://example.com/document.pdf\nSnippet: No Snippet Available\nContent: This is the transcribed text from the PDF document.\n---"
])

MOCK_LLM_FINAL_JSON_OUTPUT_DETAILED_ANALYSIS = json.dumps(["Detailed analysis content."])

MOCK_LLM_FINAL_JSON_OUTPUT_ADDITIONAL_RESEARCH = json.dumps(["Additional research content."])


MOCK_UPDATED_REPORT_PLAN = [
    ["Introduction", "Summarize the query and purpose."],
    ["Key Findings", "Detail the main findings from the research."],
    ["Conclusion", "Provide a concluding summary."]
]

MOCK_SYNTHESIZED_SECTION = {
    "report_section": "## Key Findings\n\nThis section details the key findings from the research. For example, Result 1 provided important information [[1]](http://example.com/page1).",
    "references": ["Source 1"]
}

MOCK_EXECUTIVE_SUMMARY = "# Executive Summary\n\nThis is a summary of the report."
MOCK_NEXT_STEPS = "# Next Steps / Further Research\n\nFuture research could explore X."
MOCK_FINAL_REPORT = "Final Report Content"


@pytest.fixture
def mock_socketio():
    """Mocks the SocketIO object by patching the instance in app/__init__.py."""
    # Patch the actual socketio instance where it's defined/initialized
    with unittest.mock.patch('app.__init__.socketio') as mock_sio:
        yield mock_sio

@pytest.fixture
def mock_generate_text():
    """Mocks app.ai_services.generate_text."""
    # Patch the function where deep_research *uses* it.
    # Corrected patch target to 'app.deep_research.ai_services.generate_text'
    with unittest.mock.patch('app.deep_research.ai_services.generate_text') as mock_gen_text:
        # Default return value for cases not covered by side_effect
        mock_gen_text.return_value = "Default mock text generation response."
        yield mock_gen_text

@pytest.fixture
def mock_web_search_plugin():
    """Mocks app.plugins.web_search functions."""
    with unittest.mock.patch('app.plugins.web_search.perform_web_search') as mock_perform_web_search, \
         unittest.mock.patch('app.plugins.web_search.fetch_web_content') as mock_fetch_web_content:
        yield mock_perform_web_search, mock_fetch_web_content

@pytest.fixture
def mock_transcribe_pdf_bytes():
    """Mocks app.ai_services.transcribe_pdf_bytes."""
    # Patch the function where deep_research *uses* it, not necessarily where it's defined.
    # Corrected patch target to 'app.deep_research.ai_services.transcribe_pdf_bytes'
    with unittest.mock.patch('app.deep_research.ai_services.transcribe_pdf_bytes') as mock_transcribe:
        mock_transcribe.return_value = MOCK_TRANSCRIBED_PDF_TEXT
        yield mock_transcribe

@pytest.fixture
def mock_add_message_to_db():
    """Mocks app.database.add_message_to_db."""
    with unittest.mock.patch('app.database.add_message_to_db') as mock_add_msg:
        yield mock_add_msg

@pytest.fixture
def mock_cpu_executor():
    """Mocks concurrent.futures.ProcessPoolExecutor."""
    with unittest.mock.patch('concurrent.futures.ProcessPoolExecutor') as MockExecutor:
        mock_instance = MockExecutor.return_value
        # Mock the __enter__ method of the MockExecutor (the class mock)
        # to return the mock_instance when the 'with' statement is entered.
        MockExecutor.return_value.__enter__.return_value = mock_instance
        # Mock the submit method on the mock_instance
        mock_future = unittest.mock.Mock()
        mock_future.result.return_value = MOCK_TRANSCRIBED_PDF_TEXT
        mock_instance.submit.return_value = mock_future
        yield mock_instance


def test_perform_deep_research_success(app, mock_socketio, mock_generate_text, 
                                       mock_web_search_plugin, mock_transcribe_pdf_bytes, 
                                       mock_add_message_to_db, mock_cpu_executor):
    """
    Tests a full successful deep research flow.
    """
    mock_perform_web_search, mock_fetch_web_content = mock_web_search_plugin

    # Configure mock_generate_text for each stage
    mock_generate_text.side_effect = [
        # 1. Initial Research Plan (1 call)
        json.dumps(MOCK_RESEARCH_PLAN),
        
        # 2. execute_research_step (Initial Search) (2 calls to generate_text)
        MOCK_LLM_TOOL_CALL_SEARCH, # LLM asks for web_search (first call in tool loop)
        MOCK_LLM_FINAL_JSON_OUTPUT_INITIAL_SEARCH, # LLM provides final JSON for Initial Search step (second call in tool loop)
        
        # 3. execute_research_step (Detailed Analysis) (2 calls to generate_text)
        "No tools needed for detailed analysis. Just some text.", # LLM interaction for text-only response
        MOCK_LLM_FINAL_JSON_OUTPUT_DETAILED_ANALYSIS, # LLM provides final JSON

        # 4. Updated Report Plan (1 call)
        json.dumps(MOCK_UPDATED_REPORT_PLAN),
        
        # 5. Additional Research Steps (Introduction, Key Findings, Conclusion) (2 calls each = 6 calls)
        # For "Introduction"
        "No tools needed for Introduction. Just some text.", # LLM interaction for text-only response
        MOCK_LLM_FINAL_JSON_OUTPUT_ADDITIONAL_RESEARCH,
        # For "Key Findings"
        "No tools needed for Key Findings. Just some text.", # LLM interaction for text-only response
        MOCK_LLM_FINAL_JSON_OUTPUT_ADDITIONAL_RESEARCH,
        # For "Conclusion"
        "No tools needed for Conclusion. Just some text.", # LLM interaction for text-only response
        MOCK_LLM_FINAL_JSON_OUTPUT_ADDITIONAL_RESEARCH,

        # 6. Synthesize Report Sections (3 calls)
        json.dumps(MOCK_SYNTHESIZED_SECTION), # For Introduction
        json.dumps(MOCK_SYNTHESIZED_SECTION), # For Key Findings
        json.dumps(MOCK_SYNTHESIZED_SECTION), # For Conclusion
        
        # 7. Executive Summary (1 call)
        MOCK_EXECUTIVE_SUMMARY,
        
        # 8. Next Steps (1 call)
        MOCK_NEXT_STEPS,
        
        # 9. Final Report Formatting (1 call)
        MOCK_FINAL_REPORT,
    ]

    # Configure web search/scrape mocks
    mock_perform_web_search.return_value = MOCK_WEB_SEARCH_RESULTS
    mock_fetch_web_content.side_effect = [
        MOCK_HTML_CONTENT,
        MOCK_PDF_CONTENT_INFO
    ]

    # Configure PDF transcription mock
    mock_transcribe_pdf_bytes.return_value = MOCK_TRANSCRIBED_PDF_TEXT

    # Run the deep research function within an app context
    with app.app_context():
        deep_research.perform_deep_research(
            query="test deep research",
            socketio=mock_socketio,
            sid="test_sid",
            chat_id=123
        )

    # Assertions
    mock_socketio.emit.assert_any_call("status_update", {"message": "Generating initial research plan..."}, room="test_sid")
    mock_socketio.emit.assert_any_call("status_update", {"message": "Performing initial research..."}, room="test_sid")
    mock_socketio.emit.assert_any_call("status_update", {"message": "Refined report plan with 3 sections."}, room="test_sid")
    mock_socketio.emit.assert_any_call("status_update", {"message": "Synthesizing report sections in parallel..."}, room="test_sid")
    mock_socketio.emit.assert_any_call("status_update", {"message": "Formatting final report..."}, room="test_sid")
    mock_socketio.emit.assert_any_call("deep_research_result", {"report": MOCK_FINAL_REPORT}, room="test_sid")

    # Verify database save
    mock_add_message_to_db.assert_called_once_with(123, "assistant", MOCK_FINAL_REPORT)

    # Verify web search and scrape were called
    mock_perform_web_search.assert_called_with(query="test query", num_results=2)
    mock_fetch_web_content.assert_any_call(url="http://example.com/page1")
    mock_fetch_web_content.assert_any_call(url="http://example.com/document.pdf")

    # Verify PDF transcription was called
    mock_transcribe_pdf_bytes.assert_called_once_with(MOCK_PDF_BYTES, 'document.pdf', app) # Check for app instance

    # Verify generate_text calls
    assert mock_generate_text.call_count == 18 # 1 (plan) + 2 (initial search) + 2 (detailed analysis) + 1 (updated plan) + 6 (additional research) + 3 (synthesis) + 1 (exec summary) + 1 (next steps) + 1 (final format) = 18

def test_perform_deep_research_cancellation(app, mock_socketio, mock_generate_text, mock_add_message_to_db):
    """
    Tests that deep research can be cancelled at an early stage.
    """
    # Mock the LLM to return a plan, but then immediately set cancellation
    # This will be the first call to generate_text
    mock_generate_text.return_value = json.dumps(MOCK_RESEARCH_PLAN)

    # Create a mutable cancellation flag
    cancellation_flag = {"cancelled": False}
    def is_cancelled():
        return cancellation_flag["cancelled"]

    # Set cancellation to True after the first step (plan generation)
    def set_cancel_after_plan(*args, **kwargs):
        cancellation_flag["cancelled"] = True
        return json.dumps(MOCK_RESEARCH_PLAN) # Return a valid plan for the first call
    mock_generate_text.side_effect = set_cancel_after_plan

    with app.app_context():
        deep_research.perform_deep_research(
            query="test cancellation",
            socketio=mock_socketio,
            sid="test_sid",
            chat_id=124,
            is_cancelled_callback=is_cancelled
        )

    # Assert cancellation message was emitted
    mock_socketio.emit.assert_any_call(
        "generation_cancelled",
        {"message": "[AI Info: Deep research cancelled before step 'Initial Search'.]", "chat_id": 124},
        room="test_sid"
    )
    # Assert error message was saved to DB
    mock_add_message_to_db.assert_called_once_with(124, "assistant", "[AI Info: Deep research cancelled before step 'Initial Search'.]")

def test_perform_deep_research_llm_plan_failure(app, mock_socketio, mock_generate_text, mock_add_message_to_db):
    """
    Tests handling when the LLM fails to generate an initial research plan.
    """
    # This will be the first call to generate_text
    mock_generate_text.return_value = "[Error: LLM failed]" # Not valid JSON, will cause parse error

    with app.app_context():
        deep_research.perform_deep_research(
            query="test plan failure",
            socketio=mock_socketio,
            sid="test_sid",
            chat_id=125
        )

    mock_socketio.emit.assert_any_call(
        "task_error",
        {"error": "[Error: Could not generate initial research plan.]"},
        room="test_sid"
    )
    mock_add_message_to_db.assert_called_once_with(125, "assistant", "[Error: Could not generate initial research plan.]")

def test_execute_research_step_web_search_context_fix(app, mock_socketio, mock_generate_text, mock_web_search_plugin, mock_cpu_executor):
    """
    Tests that web_search_plugin.perform_web_search is called within an app context
    when executed by the ThreadPoolExecutor.
    """
    mock_perform_web_search, mock_fetch_web_content = mock_web_search_plugin

    # Mock generate_text to return tool call and then final JSON
    mock_generate_text.side_effect = [
        # LLM interaction for tool calls
        MOCK_LLM_TOOL_CALL_SEARCH,
        # LLM interaction for final JSON output after tool results
        json.dumps([
            "Title: Result 1\nLink: http://example.com/page1\nSnippet: Snippet 1\nContent: This is the scraped content from an HTML page.\n---"
        ])
    ]

    # Mock perform_web_search to assert app context
    def mock_perform_web_search_with_context_check(*args, **kwargs):
        assert current_app is not None, "current_app should be available in perform_web_search"
        assert g is not None, "g should be available in perform_web_search"
        return MOCK_WEB_SEARCH_RESULTS

    mock_perform_web_search.side_effect = mock_perform_web_search_with_context_check
    mock_fetch_web_content.return_value = MOCK_HTML_CONTENT # Not used in this specific test, but good to have a default

    with app.app_context():
        # Call execute_research_step directly to isolate the test
        llm_summary_strings, pdf_futures_info = deep_research.execute_research_step(
            "test context for web search",
            lambda: False, # Not cancelled
            mock_socketio,
            "test_sid",
            app, # Pass the app object directly
            mock_cpu_executor
        )

    mock_perform_web_search.assert_called_once()
    assert "Snippet 1" in llm_summary_strings[0] # Verify content from mock search results

def test_execute_research_step_scrape_context_fix(app, mock_socketio, mock_generate_text, mock_web_search_plugin, mock_cpu_executor):
    """
    Tests that web_search_plugin.fetch_web_content is called within an app context
    when executed by the ThreadPoolExecutor.
    """
    mock_perform_web_search, mock_fetch_web_content = mock_web_search_plugin

    # Mock generate_text to return tool call and then final JSON
    mock_generate_text.side_effect = [
        # LLM interaction for tool calls
        MOCK_LLM_TOOL_CALL_SCRAPE,
        # LLM interaction for final JSON output after tool results
        json.dumps([
            "Title: Scraped Page\nLink: http://example.com/page1\nSnippet: Scraped content\nContent: This is the scraped content from an HTML page.\n---"
        ])
    ]

    # Mock fetch_web_content to assert app context
    def mock_fetch_web_content_with_context_check(*args, **kwargs):
        assert current_app is not None, "current_app should be available in fetch_web_content"
        assert g is not None, "g should be available in fetch_web_content"
        return MOCK_HTML_CONTENT

    mock_fetch_web_content.side_effect = mock_fetch_web_content_with_context_check
    mock_perform_web_search.return_value = MOCK_WEB_SEARCH_RESULTS # Not used in this specific test, but good to have a default

    with app.app_context():
        # Call execute_research_step directly to isolate the test
        llm_summary_strings, pdf_futures_info = deep_research.execute_research_step(
            "test context for scrape",
            lambda: False, # Not cancelled
            mock_socketio,
            "test_sid",
            app, # Pass the app object directly
            mock_cpu_executor
        )

    mock_fetch_web_content.assert_called_once()
    assert "scraped content" in llm_summary_strings[0] # Verify content from mock scrape results

def test_perform_deep_research_pdf_transcription_flow(app, mock_socketio, mock_generate_text, 
                                                      mock_web_search_plugin, mock_transcribe_pdf_bytes, 
                                                      mock_add_message_to_db, mock_cpu_executor):
    """
    Tests the flow of PDF scraping, async transcription, and placeholder replacement.
    """
    mock_perform_web_search, mock_fetch_web_content = mock_web_search_plugin

    # Configure mock_generate_text for each stage
    mock_generate_text.side_effect = [
        # 1. Initial Research Plan (1 call)
        json.dumps(MOCK_RESEARCH_PLAN),
        
        # 2. execute_research_step (Initial Search) - only PDF scrape (2 calls)
        MOCK_LLM_TOOL_CALL_SCRAPE_PDF, # LLM asks for scrape PDF
        json.dumps([ # LLM provides final JSON for Initial Search step
            "Title: Document\nLink: http://example.com/document.pdf\nSnippet: No Snippet Available\nContent: PDF_CONTENT_PENDING_ID_MOCK\n---"
        ]),
        
        # 3. execute_research_step (Detailed Analysis) (2 calls)
        "No tools needed for detailed analysis. Just some text.", # LLM interaction for text-only response
        MOCK_LLM_FINAL_JSON_OUTPUT_DETAILED_ANALYSIS,

        # 4. Updated Report Plan (1 call)
        json.dumps(MOCK_UPDATED_REPORT_PLAN),
        
        # 5. Additional Research Steps (Introduction, Key Findings, Conclusion) (6 calls)
        # For "Introduction"
        "No tools needed for Introduction. Just some text.", # LLM interaction for text-only response
        MOCK_LLM_FINAL_JSON_OUTPUT_ADDITIONAL_RESEARCH,
        # For "Key Findings"
        "No tools needed for Key Findings. Just some text.", # LLM interaction for text-only response
        MOCK_LLM_FINAL_JSON_OUTPUT_ADDITIONAL_RESEARCH,
        # For "Conclusion"
        "No tools needed for Conclusion. Just some text.", # LLM interaction for text-only response
        MOCK_LLM_FINAL_JSON_OUTPUT_ADDITIONAL_RESEARCH,

        # 6. Synthesize Report Sections (3 calls)
        json.dumps(MOCK_SYNTHESIZED_SECTION), # For Introduction
        json.dumps(MOCK_SYNTHESIZED_SECTION), # For Key Findings
        json.dumps(MOCK_SYNTHESIZED_SECTION), # For Conclusion
        
        # 7. Executive Summary (1 call)
        MOCK_EXECUTIVE_SUMMARY,
        
        # 8. Next Steps (1 call)
        MOCK_NEXT_STEPS,
        
        # 9. Final Report Formatting (1 call)
        MOCK_FINAL_REPORT,
    ]

    # Configure web scrape mock to return PDF
    mock_fetch_web_content.return_value = MOCK_PDF_CONTENT_INFO

    # Configure PDF transcription mock
    mock_transcribe_pdf_bytes.return_value = MOCK_TRANSCRIBED_PDF_TEXT

    # Mock the future returned by cpu_executor.submit
    mock_future = unittest.mock.Mock()
    mock_future.result.return_value = MOCK_TRANSCRIBED_PDF_TEXT
    mock_cpu_executor.submit.return_value = mock_future

    with app.app_context():
        deep_research.perform_deep_research(
            query="test pdf research",
            socketio=mock_socketio,
            sid="test_sid",
            chat_id=126
        )

    # Assertions
    mock_fetch_web_content.assert_called_once_with(url="http://example.com/document.pdf")
    # The mock_transcribe_pdf_bytes fixture patches `app.deep_research.ai_services.transcribe_pdf_bytes`
    # so the call to `submit` will receive the *mock* object, not the original function.
    mock_cpu_executor.submit.assert_called_once_with(mock_transcribe_pdf_bytes, MOCK_PDF_BYTES, 'document.pdf', app) # Check for app instance
    mock_transcribe_pdf_bytes.assert_called_once() # Ensure the actual transcription function was called via the executor

    # Verify the final report content contains the transcribed text, not the placeholder
    # This is a limitation of mocking the final step, but the core PDF flow is tested.
    mock_socketio.emit.assert_any_call("deep_research_result", {"report": MOCK_FINAL_REPORT}, room="test_sid")
    mock_add_message_to_db.assert_called_once_with(126, "assistant", MOCK_FINAL_REPORT)
    assert mock_generate_text.call_count == 18 # Total generate_text calls

def test_perform_deep_research_web_search_failure(app, mock_socketio, mock_generate_text, mock_web_search_plugin, mock_cpu_executor, mock_add_message_to_db):
    """
    Tests handling when web search fails during a research step.
    """
    mock_perform_web_search, mock_fetch_web_content = mock_web_search_plugin

    # Configure mock_generate_text
    mock_generate_text.side_effect = [
        # 1. Initial Research Plan (1 call)
        json.dumps(MOCK_RESEARCH_PLAN),
        
        # 2. execute_research_step (Initial Search) (2 calls)
        MOCK_LLM_TOOL_CALL_SEARCH, # LLM asks for web_search
        json.dumps([ # LLM provides final JSON for Initial Search step (with error message)
            "Title: Search Error\nLink: \nSnippet: [System Error: Web search failed. Reason: 500 Internal Server Error]\nContent: [System Error: Web search failed. Reason: 500 Internal Server Error]\n---"
        ]),
        
        # 3. execute_research_step (Detailed Analysis) (2 calls)
        "No tools needed for detailed analysis. Just some text.", # LLM interaction for text-only response
        MOCK_LLM_FINAL_JSON_OUTPUT_DETAILED_ANALYSIS,

        # 4. Updated Report Plan (1 call)
        json.dumps(MOCK_UPDATED_REPORT_PLAN),
        
        # 5. Additional Research Steps (Introduction, Key Findings, Conclusion) (6 calls)
        # For "Introduction"
        "No tools needed for Introduction. Just some text.", # LLM interaction for text-only response
        MOCK_LLM_FINAL_JSON_OUTPUT_ADDITIONAL_RESEARCH,
        # For "Key Findings"
        "No tools needed for Key Findings. Just some text.", # LLM interaction for text-only response
        MOCK_LLM_FINAL_JSON_OUTPUT_ADDITIONAL_RESEARCH,
        # For "Conclusion"
        "No tools needed for Conclusion. Just some text.", # LLM interaction for text-only response
        MOCK_LLM_FINAL_JSON_OUTPUT_ADDITIONAL_RESEARCH,

        # 6. Synthesize Report Sections (3 calls)
        json.dumps(MOCK_SYNTHESIZED_SECTION), # For Introduction
        json.dumps(MOCK_SYNTHESIZED_SECTION), # For Key Findings
        json.dumps(MOCK_SYNTHESIZED_SECTION), # For Conclusion
        
        # 7. Executive Summary (1 call)
        MOCK_EXECUTIVE_SUMMARY,
        
        # 8. Next Steps (1 call)
        MOCK_NEXT_STEPS,
        
        # 9. Final Report Formatting (1 call)
        MOCK_FINAL_REPORT,
    ]

    # Simulate web search failure
    mock_perform_web_search.side_effect = requests.exceptions.RequestException("Simulated network error")
    mock_fetch_web_content.return_value = MOCK_HTML_CONTENT # Default for scrape

    with app.app_context():
        deep_research.perform_deep_research(
            query="test web search failure",
            socketio=mock_socketio,
            sid="test_sid",
            chat_id=127
        )

    # Verify that an error message related to search failure is in the collected research
    mock_socketio.emit.assert_any_call(
        "task_error",
        unittest.mock.ANY, # Match any dictionary for the second argument
        room="test_sid"
    )
    # And then more specifically check the content of the error message
    emitted_calls = [call for call in mock_socketio.emit.call_args_list if call[0][0] == "task_error"]
    assert len(emitted_calls) > 0
    error_message_dict = emitted_calls[0][0][1] # Get the dictionary from the first 'task_error' call
    assert "error" in error_message_dict
    assert "Failed to generate the report outline" in error_message_dict["error"]

    # Ensure the web search was attempted multiple times due to retries
    assert mock_perform_web_search.call_count == 3
    assert mock_generate_text.call_count == 18 # Total generate_text calls
