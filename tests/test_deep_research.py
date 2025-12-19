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

MOCK_EXTENDED_RESEARCH_PLAN = [
    ["Define 'Deep Research' Scope", "Clarify what 'deep research' entails..."],
    ["Identify Core Methodologies", "Investigate established research methodologies..."],
    ["Source Identification & Vetting", "Research strategies for identifying..."],
    ["Information Extraction & Synthesis", "Explore effective techniques for systematically extracting..."],
    ["Critical Analysis & Bias Mitigation", "Understand methods for rigorously analyzing..."],
    ["Insight Generation & Pattern Recognition", "Research approaches to moving beyond mere data aggregation..."],
    ["Documentation & Organization Best Practices", "Investigate effective systems, tools..."],
    ["Ethical Considerations in Research", "Understand the ethical guidelines..."],
    ["Leveraging Research Technologies", "Identify and evaluate advanced software..."],
    ["Examine Case Studies & Applications", "Analyze real-world examples of successful 'deep research'..."]
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

# Helper to create a GenerateContentResponse with text
def text_response(text):
    return types.GenerateContentResponse(
        candidates=[types.Candidate(content=types.Content(parts=[types.Part(text=text)]))]
    )

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

MOCK_LLM_TOOL_CALL_MULTIPLE_SEARCHES = types.GenerateContentResponse(
    candidates=[
        types.Candidate(
            content=types.Content(
                parts=[
                    types.Part(function_call=types.FunctionCall(name="web_search", args={"query": "best practices for effective web searching", "num_results": 5})),
                    types.Part(function_call=types.FunctionCall(name="web_search", args={"query": "how search engine algorithms work", "num_results": 5})),
                    types.Part(function_call=types.FunctionCall(name="web_search", args={"query": "limitations of web search engines", "num_results": 5}))
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

# Text content for responses
MOCK_LLM_FINAL_JSON_OUTPUT_INITIAL_SEARCH_TEXT = json.dumps([
    "Title: Result 1\nLink: http://example.com/page1\nSnippet: Snippet 1\nContent: This is the scraped content from an HTML page.\n---",
    "Title: Document\nLink: http://example.com/document.pdf\nSnippet: No Snippet Available\nContent: This is the transcribed text from the PDF document.\n---"
])

MOCK_LLM_FINAL_JSON_OUTPUT_DETAILED_ANALYSIS_TEXT = json.dumps(["Detailed analysis content."])
MOCK_LLM_FINAL_JSON_OUTPUT_ADDITIONAL_RESEARCH_TEXT = json.dumps(["Additional research content."])

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
    with unittest.mock.patch('app.__init__.socketio') as mock_sio:
        yield mock_sio

@pytest.fixture
def mock_generate_text():
    """Mocks app.ai_services_lib.generation_services.generate_text.
    Used for planning, synthesis, summary, etc."""
    with unittest.mock.patch('app.deep_research.generate_text') as mock_gen_text:
        mock_gen_text.return_value = "Default mock text generation response."
        yield mock_gen_text

@pytest.fixture
def mock_genai_client():
    """Mocks google.genai.Client used in execute_research_step."""
    with unittest.mock.patch('app.deep_research.genai.Client') as MockClient:
        mock_instance = MockClient.return_value
        mock_instance.models.generate_content.return_value = text_response("Default mock genai response")
        yield mock_instance

@pytest.fixture
def mock_web_search_plugin():
    """Mocks app.plugins.web_search functions."""
    with unittest.mock.patch('app.plugins.web_search.perform_web_search') as mock_perform_web_search, \
         unittest.mock.patch('app.plugins.web_search.fetch_web_content') as mock_fetch_web_content:
        yield mock_perform_web_search, mock_fetch_web_content

@pytest.fixture
def mock_transcribe_pdf_bytes():
    """Mocks app.ai_services_lib.transcription_services.transcribe_pdf_bytes."""
    with unittest.mock.patch('app.deep_research.transcribe_pdf_bytes') as mock_transcribe:
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
        MockExecutor.return_value.__enter__.return_value = mock_instance
        mock_future = unittest.mock.Mock()
        mock_future.result.return_value = MOCK_TRANSCRIBED_PDF_TEXT
        mock_instance.submit.return_value = mock_future
        yield mock_instance

def test_perform_deep_research_success(app, mock_socketio, mock_generate_text, mock_genai_client,
                                       mock_web_search_plugin, mock_transcribe_pdf_bytes,
                                       mock_add_message_to_db, mock_cpu_executor):
    """
    Tests a full successful deep research flow.
    """
    mock_perform_web_search, mock_fetch_web_content = mock_web_search_plugin

    # 1. Configure mock_generate_text (Plan, Synthesis, Summary)
    mock_generate_text.side_effect = [
        json.dumps(MOCK_EXTENDED_RESEARCH_PLAN), # 1. Initial Research Plan
        json.dumps(MOCK_UPDATED_REPORT_PLAN),    # 2. Updated Report Plan
        json.dumps(MOCK_SYNTHESIZED_SECTION),    # 3. Synthesize Intro
        json.dumps(MOCK_SYNTHESIZED_SECTION),    # 4. Synthesize Key Findings
        json.dumps(MOCK_SYNTHESIZED_SECTION),    # 5. Synthesize Conclusion
        MOCK_EXECUTIVE_SUMMARY,                  # 6. Exec Summary
        MOCK_NEXT_STEPS,                         # 7. Next Steps
        MOCK_FINAL_REPORT,                       # 8. Final Report
    ]

    # 2. Configure mock_genai_client.models.generate_content (Execute Research Step)
    # Step 1 (Define Scope): 4 calls
    step1_responses = [
        MOCK_LLM_TOOL_CALL_MULTIPLE_SEARCHES, # Call 1: Tool Request (Search)
        types.GenerateContentResponse(        # Call 2: Tool Request (Scrape) after Search results
            candidates=[types.Candidate(content=types.Content(parts=[
                types.Part.from_function_response(name="web_search", response={"results": MOCK_WEB_SEARCH_RESULTS}),
                types.Part(function_call=types.FunctionCall(name="scrape_url", args={"url": "http://example.com/page1"})),
                types.Part(function_call=types.FunctionCall(name="scrape_url", args={"url": "http://example.com/page2"}))
            ]))]
        ),
        text_response("I have collected sufficient information."), # Call 3: Text response to break tool loop
        text_response(MOCK_LLM_FINAL_JSON_OUTPUT_INITIAL_SEARCH_TEXT) # Call 4: Final JSON generation
    ]

    # Steps 2-10 (9 steps): 2 calls each (Text break, Final JSON)
    step_generic_responses = [
        text_response("No tools needed."), 
        text_response(json.dumps(["Generic research content."]))
    ] * 9

    # Additional Research (3 sections): 2 calls each
    additional_step_responses = [
        text_response("No tools needed."),
        text_response(MOCK_LLM_FINAL_JSON_OUTPUT_ADDITIONAL_RESEARCH_TEXT)
    ] * 3

    mock_genai_client.models.generate_content.side_effect = (
        step1_responses + step_generic_responses + additional_step_responses
    )

    # Configure web search/scrape mocks
    mock_perform_web_search.return_value = MOCK_WEB_SEARCH_RESULTS
    def fetch_web_content_side_effect(url):
        if url == "http://example.com/page1":
            return MOCK_HTML_CONTENT
        elif url == "http://example.com/document.pdf":
            return MOCK_PDF_CONTENT_INFO
        elif url == "http://example.com/page2":
            return {'type': 'html', 'content': 'Content from page2.', 'url': url}
        else:
            return {'type': 'html', 'content': f'Content from {url}', 'url': url}
    mock_fetch_web_content.side_effect = fetch_web_content_side_effect

    # Configure PDF transcription mock
    mock_transcribe_pdf_bytes.return_value = MOCK_TRANSCRIBED_PDF_TEXT
    # Mock the future returned by cpu_executor.submit
    mock_future = unittest.mock.Mock()
    mock_future.result.return_value = MOCK_TRANSCRIBED_PDF_TEXT
    mock_cpu_executor.submit.return_value = mock_future

    with app.app_context():
        # Inject a dummy API Key so the client init doesn't fail before hitting our mock
        app.config['API_KEY'] = 'dummy_key'
        deep_research.perform_deep_research(
            query="test deep research",
            socketio=mock_socketio,
            sid="test_sid",
            chat_id=123
        )

    # Assertions
    mock_socketio.emit.assert_any_call("status_update", {"message": "Generating initial research plan..."}, room="test_sid")
    mock_socketio.emit.assert_any_call("status_update", {"message": f"Generated {len(MOCK_EXTENDED_RESEARCH_PLAN)} initial research steps."}, room="test_sid")
    mock_socketio.emit.assert_any_call("status_update", {"message": "Refined report plan with 3 sections."}, room="test_sid")
    mock_socketio.emit.assert_any_call("deep_research_result", {"report": MOCK_FINAL_REPORT}, room="test_sid")

    # Verify database save
    mock_add_message_to_db.assert_called_once_with(123, "assistant", MOCK_FINAL_REPORT)

    # Verify web search and scrape were called
    # Step 1 triggers 3 searches.
    assert mock_perform_web_search.call_count == 3
    # Step 1 triggers 2 scrapes.
    assert mock_fetch_web_content.call_count == 2

    # Verify generate_text calls
    assert mock_generate_text.call_count == 8 

    # Verify genai_client calls
    # 4 (Step 1) + 18 (Steps 2-10) + 6 (Additional) = 28
    assert mock_genai_client.models.generate_content.call_count == 28


def test_perform_deep_research_cancellation(app, mock_socketio, mock_generate_text, mock_add_message_to_db):
    """
    Tests that deep research can be cancelled at an early stage.
    """
    mock_generate_text.return_value = json.dumps(MOCK_RESEARCH_PLAN)

    cancellation_flag = {"cancelled": False}
    def is_cancelled():
        return cancellation_flag["cancelled"]

    def set_cancel_after_plan(*args, **kwargs):
        cancellation_flag["cancelled"] = True
        return json.dumps(MOCK_RESEARCH_PLAN) 
    mock_generate_text.side_effect = set_cancel_after_plan

    with app.app_context():
        app.config['API_KEY'] = 'dummy_key'
        deep_research.perform_deep_research(
            query="test cancellation",
            socketio=mock_socketio,
            sid="test_sid",
            chat_id=124,
            is_cancelled_callback=is_cancelled
        )

    mock_socketio.emit.assert_any_call(
        "generation_cancelled",
        {"message": "[AI Info: Deep research cancelled before step 'Initial Search'.]", "chat_id": 124},
        room="test_sid"
    )
    mock_add_message_to_db.assert_called_once_with(124, "assistant", "[AI Info: Deep research cancelled before step 'Initial Search'.]")


def test_perform_deep_research_llm_plan_failure(app, mock_socketio, mock_generate_text, mock_add_message_to_db):
    """
    Tests handling when the LLM fails to generate an initial research plan.
    """
    mock_generate_text.return_value = "[Error: LLM failed]"

    with app.app_context():
        app.config['API_KEY'] = 'dummy_key'
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


def test_execute_research_step_web_search_context_fix(app, mock_socketio, mock_genai_client, mock_web_search_plugin, mock_cpu_executor):
    """
    Tests that web_search_plugin.perform_web_search is called within an app context.
    """
    mock_perform_web_search, mock_fetch_web_content = mock_web_search_plugin

    # Configure mock_genai_client for execute_research_step
    # 1. Tool Call (Search)
    # 2. Text Break (assume search was enough or just testing context)
    # 3. Final JSON
    mock_genai_client.models.generate_content.side_effect = [
        MOCK_LLM_TOOL_CALL_SEARCH,
        text_response("Done."),
        text_response(json.dumps(["Result 1 content"]))
    ]

    def mock_perform_web_search_with_context_check(*args, **kwargs):
        assert current_app is not None, "current_app should be available in perform_web_search"
        assert g is not None, "g should be available in perform_web_search"
        return MOCK_WEB_SEARCH_RESULTS

    mock_perform_web_search.side_effect = mock_perform_web_search_with_context_check
    mock_fetch_web_content.return_value = MOCK_HTML_CONTENT

    with app.app_context():
        app.config['API_KEY'] = 'dummy_key'
        llm_summary_strings, pdf_futures_info = deep_research.execute_research_step(
            "test context for web search",
            lambda: False,
            mock_socketio,
            "test_sid",
            app, 
            mock_cpu_executor
        )

    mock_perform_web_search.assert_called_once()
    assert "Result 1 content" in llm_summary_strings[0]

 
def test_execute_research_step_scrape_context_fix(app, mock_socketio, mock_genai_client, mock_web_search_plugin, mock_cpu_executor):
    """
    Tests that web_search_plugin.fetch_web_content is called within an app context.
    """
    mock_perform_web_search, mock_fetch_web_content = mock_web_search_plugin

    mock_genai_client.models.generate_content.side_effect = [
        MOCK_LLM_TOOL_CALL_SCRAPE,
        text_response("Done."),
        text_response(json.dumps(["Scraped content"]))
    ]

    def mock_fetch_web_content_with_context_check(*args, **kwargs):
        assert current_app is not None, "current_app should be available in fetch_web_content"
        assert g is not None, "g should be available in fetch_web_content"
        return MOCK_HTML_CONTENT

    mock_fetch_web_content.side_effect = mock_fetch_web_content_with_context_check
    mock_perform_web_search.return_value = MOCK_WEB_SEARCH_RESULTS

    with app.app_context():
        app.config['API_KEY'] = 'dummy_key'
        llm_summary_strings, pdf_futures_info = deep_research.execute_research_step(
            "test context for scrape",
            lambda: False,
            mock_socketio,
            "test_sid",
            app,
            mock_cpu_executor
        )

    mock_fetch_web_content.assert_called_once()
    assert "Scraped content" in llm_summary_strings[0]


def test_perform_deep_research_pdf_transcription_flow(app, mock_socketio, mock_generate_text, mock_genai_client,
                                                      mock_web_search_plugin, mock_transcribe_pdf_bytes, 
                                                      mock_add_message_to_db, mock_cpu_executor):
    """
    Tests the flow of PDF scraping, async transcription, and placeholder replacement.
    """
    mock_perform_web_search, mock_fetch_web_content = mock_web_search_plugin

    # 1. mock_generate_text
    mock_generate_text.side_effect = [
        json.dumps(MOCK_EXTENDED_RESEARCH_PLAN),
        json.dumps(MOCK_UPDATED_REPORT_PLAN),
        json.dumps(MOCK_SYNTHESIZED_SECTION),
        json.dumps(MOCK_SYNTHESIZED_SECTION),
        json.dumps(MOCK_SYNTHESIZED_SECTION),
        MOCK_EXECUTIVE_SUMMARY,
        MOCK_NEXT_STEPS,
        MOCK_FINAL_REPORT,
    ]

    # 2. mock_genai_client
    # Step 1 (PDF): 3 calls
    #  1. Tool Request (Scrape PDF)
    #  2. Text Break
    #  3. Final JSON (with placeholder)
    step1_responses = [
        MOCK_LLM_TOOL_CALL_SCRAPE_PDF,
        text_response("Done."),
        text_response(json.dumps([
            "Title: Document\nLink: http://example.com/document.pdf\nSnippet: No Snippet\nContent: PDF_CONTENT_PENDING_ID_MOCK\n---"
        ]))
    ]
    
    # 9 Steps * 2 calls
    step_generic_responses = [
        text_response("No tools needed."), 
        text_response(json.dumps(["Generic content."]))
    ] * 9

    # 3 Additional Steps * 2 calls
    additional_step_responses = [
        text_response("No tools needed."),
        text_response(MOCK_LLM_FINAL_JSON_OUTPUT_ADDITIONAL_RESEARCH_TEXT)
    ] * 3

    mock_genai_client.models.generate_content.side_effect = (
        step1_responses + step_generic_responses + additional_step_responses
    )

    # Web/PDF mocks
    mock_fetch_web_content.return_value = MOCK_PDF_CONTENT_INFO
    mock_transcribe_pdf_bytes.return_value = MOCK_TRANSCRIBED_PDF_TEXT
    mock_future = unittest.mock.Mock()
    mock_future.result.return_value = MOCK_TRANSCRIBED_PDF_TEXT
    mock_cpu_executor.submit.return_value = mock_future

    with app.app_context():
        app.config['API_KEY'] = 'dummy_key'
        # Patch UUID to get consistent placeholder ID
        with unittest.mock.patch('uuid.uuid4', return_value='MOCK'):
            deep_research.perform_deep_research(
                query="test pdf research",
                socketio=mock_socketio,
                sid="test_sid",
                chat_id=126
            )

    mock_fetch_web_content.assert_called_once_with(url="http://example.com/document.pdf")
    mock_cpu_executor.submit.assert_called_once_with(mock_transcribe_pdf_bytes, MOCK_PDF_BYTES, 'document.pdf', app)
    mock_add_message_to_db.assert_called_once_with(126, "assistant", MOCK_FINAL_REPORT)


def test_perform_deep_research_web_search_failure(app, mock_socketio, mock_generate_text, mock_genai_client,
                                                  mock_web_search_plugin, mock_cpu_executor, mock_add_message_to_db):
    """
    Tests handling when web search fails during a research step.
    """
    mock_perform_web_search, mock_fetch_web_content = mock_web_search_plugin

    # 1. mock_generate_text (Plan only, then it fails)
    mock_generate_text.side_effect = [
        json.dumps(MOCK_EXTENDED_RESEARCH_PLAN),
    ]

    # 2. mock_genai_client
    # Step 1:
    # 1. generate_content -> Tool Request
    # 2. generate_content (with error response in history) -> LLM likely apologizes or tries again.
    #    Let's assume LLM gives up and breaks loop with text.
    # 3. generate_content (Final JSON) -> We want this to contain the error message or empty so checking logic handles it.

    mock_genai_client.models.generate_content.side_effect = [
        MOCK_LLM_TOOL_CALL_MULTIPLE_SEARCHES, # 1. Request Search
        text_response("I cannot search due to errors."), # 2. LLM sees error, breaks loop
        text_response(json.dumps([ # 3. Final JSON with error info
             "Title: Search Error\nLink: \nSnippet: [System Error]\nContent: [System Error]\n---"
        ]))
    ]
    
    # Mock Steps 2-10 for GenAI client
    # Step 1: 3 calls (as defined above)
    # Steps 2-10: 2 calls each
    step_generic_responses = [
        text_response("No tools."), 
        text_response(json.dumps(["Generic."]))
    ] * 9
    
    mock_genai_client.models.generate_content.side_effect = (
         [
            MOCK_LLM_TOOL_CALL_MULTIPLE_SEARCHES,
            text_response("Give up."),
            text_response(json.dumps(["Error content."]))
         ] + 
         step_generic_responses
    )

    # Simulate web search failure
    mock_perform_web_search.side_effect = requests.exceptions.RequestException("Simulated network error")

    with app.app_context():
        app.config['API_KEY'] = 'dummy_key'
        deep_research.perform_deep_research(
            query="test web search failure",
            socketio=mock_socketio,
            sid="test_sid",
            chat_id=127
        )

    # Assertions
    emitted_calls = [call for call in mock_socketio.emit.call_args_list if call[0][0] == "task_error"]
    assert len(emitted_calls) > 0
    error_message_dict = emitted_calls[0][0][1]
    assert "Failed to generate the report outline" in error_message_dict["error"]
    
    # 3 calls * 3 retries = 9
    assert mock_perform_web_search.call_count == 9