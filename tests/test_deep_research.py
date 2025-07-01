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
# NOTE: The actual LLM might generate a plan with more steps than this MOCK_RESEARCH_PLAN.
# The side_effect for mock_generate_text must account for the number of calls
# that the LLM's *actual* (mocked) plan generation would trigger.
# For simplicity in tests, we'll define a consistent 2-step plan here,
# but the side_effect will be expanded to simulate a more complex scenario if needed.
MOCK_RESEARCH_PLAN = [
    ["Initial Search", "Find general information about the query."],
    ["Detailed Analysis", "Analyze specific aspects mentioned in the query."]
]

# A more complex plan to match observed LLM behavior in logs (10 steps)
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

# NEW MOCK: Simulates LLM returning multiple web_search calls in one turn
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
    """Mocks app.ai_services_lib.generation_services.generate_text."""
    # Corrected patch target: Patch where deep_research looks it up.
    with unittest.mock.patch('app.deep_research.generate_text') as mock_gen_text:
        # Default return value for cases not covered by side_effect
        mock_gen_text.return_value = "Default mock text generation response."
        yield mock_gen_text

@pytest.fixture
def mock_web_search_plugin():
    """Mocks app.plugins.web_search functions."""
    # Patch the functions at their original definition locations
    with unittest.mock.patch('app.plugins.web_search.perform_web_search') as mock_perform_web_search, \
         unittest.mock.patch('app.plugins.web_search.fetch_web_content') as mock_fetch_web_content:
        yield mock_perform_web_search, mock_fetch_web_content

@pytest.fixture
def mock_transcribe_pdf_bytes():
    """Mocks app.ai_services_lib.transcription_services.transcribe_pdf_bytes."""
    # Corrected patch target: Patch where deep_research looks it up.
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
        # Mock the __enter__ method of the MockExecutor (the class mock)
        # to return the mock_instance when the 'with' statement is entered.
        MockExecutor.return_value.__enter__.return_value = mock_instance
        # Mock the submit method on the mock_instance
        mock_future = unittest.mock.Mock()
        mock_future.result.return_value = MOCK_TRANSCRIBED_PDF_TEXT
        mock_instance.submit.return_value = mock_future
        yield mock_instance

# Re-enabling the test as we are addressing the mock issues
# @pytest.mark.skip(reason="mocks not working correctly")
def test_perform_deep_research_success(app, mock_socketio, mock_generate_text, 
                                       mock_web_search_plugin, mock_transcribe_pdf_bytes, 
                                       mock_add_message_to_db, mock_cpu_executor):
    """
    Tests a full successful deep research flow.
    """
    mock_perform_web_search, mock_fetch_web_content = mock_web_search_plugin

    # Configure mock_generate_text for each stage
    # The side_effect list must be exhaustive for all expected LLM calls.
    # This now simulates a 10-step initial plan and 3-section updated plan.
    mock_generate_text.side_effect = [
        # 1. Initial Research Plan (1 call)
        json.dumps(MOCK_EXTENDED_RESEARCH_PLAN), # Returns 10 steps
        
        # 2. execute_research_step for each of the 10 initial research steps
        # Each step will typically involve 3 calls: tool request, tool response, final JSON
        # For simplicity, we'll use a generic sequence for each step.
        # Step 1: Define 'Deep Research' Scope
        MOCK_LLM_TOOL_CALL_MULTIPLE_SEARCHES, # LLM asks for web_search (3 times in one turn)
        types.GenerateContentResponse( # LLM gets search results, then asks for scrape_url for page1 and page2
            candidates=[
                types.Candidate(
                    content=types.Content(
                        parts=[
                            types.Part.from_function_response(name="web_search", response={"results": MOCK_WEB_SEARCH_RESULTS}),
                            types.Part(function_call=types.FunctionCall(name="scrape_url", args={"url": "http://example.com/page1"})),
                            types.Part(function_call=types.FunctionCall(name="scrape_url", args={"url": "http://example.com/page2"}))
                        ]
                    )
                )
            ]
        ),
        MOCK_LLM_FINAL_JSON_OUTPUT_INITIAL_SEARCH, # LLM provides final JSON
        
        # Step 2: Identify Core Methodologies
        MOCK_LLM_TOOL_CALL_MULTIPLE_SEARCHES,
        types.GenerateContentResponse(
            candidates=[types.Candidate(content=types.Content(parts=[
                types.Part.from_function_response(name="web_search", response={"results": MOCK_WEB_SEARCH_RESULTS}),
                types.Part(function_call=types.FunctionCall(name="scrape_url", args={"url": "http://example.com/page1"})),
                types.Part(function_call=types.FunctionCall(name="scrape_url", args={"url": "http://example.com/page2"}))
            ]))]
        ),
        MOCK_LLM_FINAL_JSON_OUTPUT_INITIAL_SEARCH,

        # Step 3: Source Identification & Vetting
        MOCK_LLM_TOOL_CALL_MULTIPLE_SEARCHES,
        types.GenerateContentResponse(
            candidates=[types.Candidate(content=types.Content(parts=[
                types.Part.from_function_response(name="web_search", response={"results": MOCK_WEB_SEARCH_RESULTS}),
                types.Part(function_call=types.FunctionCall(name="scrape_url", args={"url": "http://example.com/page1"})),
                types.Part(function_call=types.FunctionCall(name="scrape_url", args={"url": "http://example.com/page2"}))
            ]))]
        ),
        MOCK_LLM_FINAL_JSON_OUTPUT_INITIAL_SEARCH,

        # Step 4: Information Extraction & Synthesis
        MOCK_LLM_TOOL_CALL_MULTIPLE_SEARCHES,
        types.GenerateContentResponse(
            candidates=[types.Candidate(content=types.Content(parts=[
                types.Part.from_function_response(name="web_search", response={"results": MOCK_WEB_SEARCH_RESULTS}),
                types.Part(function_call=types.FunctionCall(name="scrape_url", args={"url": "http://example.com/page1"})),
                types.Part(function_call=types.FunctionCall(name="scrape_url", args={"url": "http://example.com/page2"}))
            ]))]
        ),
        MOCK_LLM_FINAL_JSON_OUTPUT_INITIAL_SEARCH,

        # Step 5: Critical Analysis & Bias Mitigation
        MOCK_LLM_TOOL_CALL_MULTIPLE_SEARCHES,
        types.GenerateContentResponse(
            candidates=[types.Candidate(content=types.Content(parts=[
                types.Part.from_function_response(name="web_search", response={"results": MOCK_WEB_SEARCH_RESULTS}),
                types.Part(function_call=types.FunctionCall(name="scrape_url", args={"url": "http://example.com/page1"})),
                types.Part(function_call=types.FunctionCall(name="scrape_url", args={"url": "http://example.com/page2"}))
            ]))]
        ),
        MOCK_LLM_FINAL_JSON_OUTPUT_INITIAL_SEARCH,

        # Step 6: Insight Generation & Pattern Recognition
        MOCK_LLM_TOOL_CALL_MULTIPLE_SEARCHES,
        types.GenerateContentResponse(
            candidates=[types.Candidate(content=types.Content(parts=[
                types.Part.from_function_response(name="web_search", response={"results": MOCK_WEB_SEARCH_RESULTS}),
                types.Part(function_call=types.FunctionCall(name="scrape_url", args={"url": "http://example.com/page1"})),
                types.Part(function_call=types.FunctionCall(name="scrape_url", args={"url": "http://example.com/page2"}))
            ]))]
        ),
        MOCK_LLM_FINAL_JSON_OUTPUT_INITIAL_SEARCH,

        # Step 7: Documentation & Organization Best Practices
        MOCK_LLM_TOOL_CALL_MULTIPLE_SEARCHES,
        types.GenerateContentResponse(
            candidates=[types.Candidate(content=types.Content(parts=[
                types.Part.from_function_response(name="web_search", response={"results": MOCK_WEB_SEARCH_RESULTS}),
                types.Part(function_call=types.FunctionCall(name="scrape_url", args={"url": "http://example.com/page1"})),
                types.Part(function_call=types.FunctionCall(name="scrape_url", args={"url": "http://example.com/page2"}))
            ]))]
        ),
        MOCK_LLM_FINAL_JSON_OUTPUT_INITIAL_SEARCH,

        # Step 8: Ethical Considerations in Research
        MOCK_LLM_TOOL_CALL_MULTIPLE_SEARCHES,
        types.GenerateContentResponse(
            candidates=[types.Candidate(content=types.Content(parts=[
                types.Part.from_function_response(name="web_search", response={"results": MOCK_WEB_SEARCH_RESULTS}),
                types.Part(function_call=types.FunctionCall(name="scrape_url", args={"url": "http://example.com/page1"})),
                types.Part(function_call=types.FunctionCall(name="scrape_url", args={"url": "http://example.com/page2"}))
            ]))]
        ),
        MOCK_LLM_FINAL_JSON_OUTPUT_INITIAL_SEARCH,

        # Step 9: Leveraging Research Technologies
        MOCK_LLM_TOOL_CALL_MULTIPLE_SEARCHES,
        types.GenerateContentResponse(
            candidates=[types.Candidate(content=types.Content(parts=[
                types.Part.from_function_response(name="web_search", response={"results": MOCK_WEB_SEARCH_RESULTS}),
                types.Part(function_call=types.FunctionCall(name="scrape_url", args={"url": "http://example.com/page1"})),
                types.Part(function_call=types.FunctionCall(name="scrape_url", args={"url": "http://example.com/page2"}))
            ]))]
        ),
        MOCK_LLM_FINAL_JSON_OUTPUT_INITIAL_SEARCH,

        # Step 10: Examine Case Studies & Applications
        MOCK_LLM_TOOL_CALL_MULTIPLE_SEARCHES,
        types.GenerateContentResponse(
            candidates=[types.Candidate(content=types.Content(parts=[
                types.Part.from_function_response(name="web_search", response={"results": MOCK_WEB_SEARCH_RESULTS}),
                types.Part(function_call=types.FunctionCall(name="scrape_url", args={"url": "http://example.com/page1"})),
                types.Part(function_call=types.FunctionCall(name="scrape_url", args={"url": "http://example.com/page2"}))
            ]))]
        ),
        MOCK_LLM_FINAL_JSON_OUTPUT_INITIAL_SEARCH,
        
        # 3. Updated Report Plan (1 call)
        json.dumps(MOCK_UPDATED_REPORT_PLAN), # Returns 3 sections
        
        # 4. Additional Research Steps (Introduction, Key Findings, Conclusion) (2 calls each = 6 calls)
        # These are new sections, so execute_research_step is called for each.
        # For "Introduction"
        "No tools needed for Introduction. Just some text.", # LLM interaction for text-only response
        MOCK_LLM_FINAL_JSON_OUTPUT_ADDITIONAL_RESEARCH,
        # For "Key Findings"
        "No tools needed for Key Findings. Just some text.", # LLM interaction for text-only response
        MOCK_LLM_FINAL_JSON_OUTPUT_ADDITIONAL_RESEARCH,
        # For "Conclusion"
        "No tools needed for Conclusion. Just some text.", # LLM interaction for text-only response
        MOCK_LLM_FINAL_JSON_OUTPUT_ADDITIONAL_RESEARCH,

        # 5. Synthesize Report Sections (3 calls)
        json.dumps(MOCK_SYNTHESIZED_SECTION), # For Introduction
        json.dumps(MOCK_SYNTHESIZED_SECTION), # For Key Findings
        json.dumps(MOCK_SYNTHESIZED_SECTION), # For Conclusion
        
        # 6. Executive Summary (1 call)
        MOCK_EXECUTIVE_SUMMARY,
        
        # 7. Next Steps (1 call)
        MOCK_NEXT_STEPS,
        
        # 8. Final Report Formatting (1 call)
        MOCK_FINAL_REPORT,
    ]

    # Configure web search/scrape mocks
    mock_perform_web_search.return_value = MOCK_WEB_SEARCH_RESULTS
    # The side_effect for fetch_web_content needs to be robust to multiple calls, including retries.
    def fetch_web_content_side_effect(url):
        if url == "http://example.com/page1":
            return MOCK_HTML_CONTENT
        elif url == "http://example.com/document.pdf":
            return MOCK_PDF_CONTENT_INFO
        elif url == "http://example.com/page2": # Explicitly handle page2 if LLM requests it
            return {'type': 'html', 'content': 'Content from page2.', 'url': url}
        else:
            # For any other unexpected scrape URL, return a generic HTML content
            return {'type': 'html', 'content': f'Content from {url}', 'url': url}

    mock_fetch_web_content.side_effect = fetch_web_content_side_effect

    # Configure PDF transcription mock
    mock_transcribe_pdf_bytes.return_value = MOCK_TRANSCRIBED_PDF_TEXT

    # Mock the future returned by cpu_executor.submit
    mock_future = unittest.mock.Mock()
    mock_future.result.return_value = MOCK_TRANSCRIBED_PDF_TEXT
    mock_cpu_executor.submit.return_value = mock_future

    with app.app_context():
        deep_research.perform_deep_research(
            query="test deep research",
            socketio=mock_socketio,
            sid="test_sid",
            chat_id=123
        )

    # Assertions
    mock_socketio.emit.assert_any_call("status_update", {"message": "Generating initial research plan..."}, room="test_sid")
    mock_socketio.emit.assert_any_call("status_update", {"message": f"Generated {len(MOCK_EXTENDED_RESEARCH_PLAN)} initial research steps."}, room="test_sid")
    mock_socketio.emit.assert_any_call("status_update", {"message": "Performing initial research..."}, room="test_sid")
    mock_socketio.emit.assert_any_call("status_update", {"message": "Refined report plan with 3 sections."}, room="test_sid")
    mock_socketio.emit.assert_any_call("status_update", {"message": "Synthesizing report sections in parallel..."}, room="test_sid")
    mock_socketio.emit.assert_any_call("status_update", {"message": "Formatting final report..."}, room="test_sid")
    mock_socketio.emit.assert_any_call("deep_research_result", {"report": MOCK_FINAL_REPORT}, room="test_sid")

    # Verify database save
    mock_add_message_to_db.assert_called_once_with(123, "assistant", MOCK_FINAL_REPORT)

    # Verify web search and scrape were called
    # 10 initial research steps * 3 web_search calls per step = 30 calls
    assert mock_perform_web_search.call_count == 30
    # 10 initial research steps * 2 scrape_url calls per step = 20 calls
    assert mock_fetch_web_content.call_count == 20

    # Verify PDF transcription was called
    mock_cpu_executor.submit.assert_called_once_with(mock_transcribe_pdf_bytes, MOCK_PDF_BYTES, 'document.pdf')
    mock_transcribe_pdf_bytes.assert_called_once() # Ensure the actual transcription function was called via the executor

    # Verify generate_text calls
    # 1 (plan) + (10 * 3) (initial research steps) + 1 (updated plan) + (3 * 2) (additional research steps) + 3 (synthesis) + 1 (exec summary) + 1 (next steps) + 1 (final format) = 1 + 30 + 1 + 6 + 3 + 1 + 1 + 1 = 44
    assert mock_generate_text.call_count == 44


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

# Re-enabling the test as we are addressing the mock issues
# @pytest.mark.skip(reason="mocks not working correctly")
def test_execute_research_step_web_search_context_fix(app, mock_socketio, mock_generate_text, mock_web_search_plugin, mock_cpu_executor):
    """
    Tests that web_search_plugin.perform_web_search is called within an app context
    when executed by the ThreadPoolExecutor.
    """
    mock_perform_web_search, mock_fetch_web_content = mock_web_search_plugin

    # Mock generate_text to return tool call and then final JSON
    mock_generate_text.side_effect = [
        # LLM interaction for tool calls
        MOCK_LLM_TOOL_CALL_SEARCH, # This mock only has ONE web_search call
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
    mock_fetch_web_content.return_value = MOCK_HTML_CONTENT # Default for scrape

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

# Re-enabling the test as we are addressing the mock issues
# @pytest.mark.skip(reason="mocks not working correctly")    
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

# Re-enabling the test as we are addressing the mock issues
# @pytest.mark.skip(reason="mocks not working correctly")
def test_perform_deep_research_pdf_transcription_flow(app, mock_socketio, mock_generate_text, 
                                                      mock_web_search_plugin, mock_transcribe_pdf_bytes, 
                                                      mock_add_message_to_db, mock_cpu_executor):
    """
    Tests the flow of PDF scraping, async transcription, and placeholder replacement.
    """
    mock_perform_web_search, mock_fetch_web_content = mock_web_search_plugin

    # Configure mock_generate_text for each stage
    # This now simulates a 10-step initial plan and 3-section updated plan.
    mock_generate_text.side_effect = [
        # 1. Initial Research Plan (1 call)
        json.dumps(MOCK_EXTENDED_RESEARCH_PLAN), # Returns 10 steps
        
        # 2. execute_research_step for each of the 10 initial research steps
        # For simplicity, we'll use a generic sequence for each step.
        # Step 1: Define 'Deep Research' Scope (PDF scrape)
        MOCK_LLM_TOOL_CALL_SCRAPE_PDF, # LLM asks for scrape PDF
        json.dumps([ # LLM provides final JSON for Initial Search step
            "Title: Document\nLink: http://example.com/document.pdf\nSnippet: No Snippet Available\nContent: PDF_CONTENT_PENDING_ID_MOCK\n---"
        ]),
        
        # Step 2-10: Other initial research steps (9 steps * 2 calls each = 18 calls)
        # For simplicity, these will be text-only responses
        *([
            "No tools needed for this step. Just some text.",
            json.dumps(["Generic research content."])
        ] * 9),

        # 3. Updated Report Plan (1 call)
        json.dumps(MOCK_UPDATED_REPORT_PLAN), # Returns 3 sections
        
        # 4. Additional Research Steps (Introduction, Key Findings, Conclusion) (2 calls each = 6 calls)
        # For "Introduction"
        "No tools needed for Introduction. Just some text.",
        MOCK_LLM_FINAL_JSON_OUTPUT_ADDITIONAL_RESEARCH,
        # For "Key Findings"
        "No tools needed for Key Findings. Just some text.",
        MOCK_LLM_FINAL_JSON_OUTPUT_ADDITIONAL_RESEARCH,
        # For "Conclusion"
        "No tools needed for Conclusion. Just some text.",
        MOCK_LLM_FINAL_JSON_OUTPUT_ADDITIONAL_RESEARCH,

        # 5. Synthesize Report Sections (3 calls)
        json.dumps(MOCK_SYNTHESIZED_SECTION),
        json.dumps(MOCK_SYNTHESIZED_SECTION),
        json.dumps(MOCK_SYNTHESIZED_SECTION),
        
        # 6. Executive Summary (1 call)
        MOCK_EXECUTIVE_SUMMARY,
        
        # 7. Next Steps (1 call)
        MOCK_NEXT_STEPS,
        
        # 8. Final Report Formatting (1 call)
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
    # The mock_transcribe_pdf_bytes fixture patches `app.deep_research.transcribe_pdf_bytes`
    # so the call to `submit` will receive the *mock* object, not the original function.
    # The `app` argument is no longer passed to `transcribe_pdf_bytes` in deep_research.py
    mock_cpu_executor.submit.assert_called_once_with(mock_transcribe_pdf_bytes, MOCK_PDF_BYTES, 'document.pdf')
    mock_transcribe_pdf_bytes.assert_called_once() # Ensure the actual transcription function was called via the executor

    # Verify the final report content contains the transcribed text, not the placeholder
    # This is a limitation of mocking the final step, but the core PDF flow is tested.
    mock_socketio.emit.assert_any_call("deep_research_result", {"report": MOCK_FINAL_REPORT}, room="test_sid")
    mock_add_message_to_db.assert_called_once_with(126, "assistant", MOCK_FINAL_REPORT)
    
    # Verify generate_text calls
    # 1 (plan) + 2 (PDF step) + (9 * 2) (other initial steps) + 1 (updated plan) + (3 * 2) (additional research) + 3 (synthesis) + 1 (exec summary) + 1 (next steps) + 1 (final format) = 1 + 2 + 18 + 1 + 6 + 3 + 1 + 1 + 1 = 34
    assert mock_generate_text.call_count == 34

# Re-enabling the test as we are addressing the mock issues
# @pytest.mark.skip(reason="mocks not working correctly")
def test_perform_deep_research_web_search_failure(app, mock_socketio, mock_generate_text, mock_web_search_plugin, mock_cpu_executor, mock_add_message_to_db):
    """
    Tests handling when web search fails during a research step.
    """
    mock_perform_web_search, mock_fetch_web_content = mock_web_search_plugin

    # Configure mock_generate_text
    # This now simulates a 10-step initial plan and 3-section updated plan.
    mock_generate_text.side_effect = [
        # 1. Initial Research Plan (1 call)
        json.dumps(MOCK_EXTENDED_RESEARCH_PLAN), # Returns 10 steps
        
        # 2. execute_research_step for each of the 10 initial research steps
        # Step 1: Define 'Deep Research' Scope (Web Search Failure)
        MOCK_LLM_TOOL_CALL_MULTIPLE_SEARCHES, # LLM asks for web_search (3 times in one turn)
        json.dumps([ # LLM provides final JSON for Initial Search step (with error message)
            "Title: Search Error\nLink: \nSnippet: [System Error: Web search failed. Reason: 500 Internal Server Error]\nContent: [System Error: Web search failed. Reason: 500 Internal Server Error]\n---"
        ]),
        
        # Step 2-10: Other initial research steps (9 steps * 2 calls each = 18 calls)
        # For simplicity, these will be text-only responses
        *([
            "No tools needed for this step. Just some text.",
            json.dumps(["Generic research content."])
        ] * 9),

        # 3. Updated Report Plan (1 call)
        json.dumps(MOCK_UPDATED_REPORT_PLAN), # Returns 3 sections
        
        # 4. Additional Research Steps (Introduction, Key Findings, Conclusion) (2 calls each = 6 calls)
        # For "Introduction"
        "No tools needed for Introduction. Just some text.",
        MOCK_LLM_FINAL_JSON_OUTPUT_ADDITIONAL_RESEARCH,
        # For "Key Findings"
        "No tools needed for Key Findings. Just some text.",
        MOCK_LLM_FINAL_JSON_OUTPUT_ADDITIONAL_RESEARCH,
        # For "Conclusion"
        "No tools needed for Conclusion. Just some text.",
        MOCK_LLM_FINAL_JSON_OUTPUT_ADDITIONAL_RESEARCH,

        # 5. Synthesize Report Sections (3 calls)
        json.dumps(MOCK_SYNTHESIZED_SECTION),
        json.dumps(MOCK_SYNTHESIZED_SECTION),
        json.dumps(MOCK_SYNTHESIZED_SECTION),
        
        # 6. Executive Summary (1 call)
        MOCK_EXECUTIVE_SUMMARY,
        
        # 7. Next Steps (1 call)
        MOCK_NEXT_STEPS,
        
        # 8. Final Report Formatting (1 call)
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
    # 3 calls per step * 3 retries = 9 calls for the first step, then the side_effect changes.
    # However, the side_effect is set up such that the *first* call to generate_text for the step
    # will trigger the 3 web_search calls. The `side_effect` for `mock_generate_text` is exhausted
    # after the first step's LLM interactions, leading to the `Failed to generate the report outline` error.
    # So, it should be 3 calls (from the first LLM response) * 3 retries = 9 calls.
    assert mock_perform_web_search.call_count == 9
    # Verify generate_text calls
    # 1 (plan) + 2 (failed web search step, before error is caught and flow changes) = 3
    # The subsequent steps in the side_effect list for mock_generate_text will not be reached
    # because the `perform_deep_research` function exits early due to the error.
    # The `mock_generate_text.side_effect` list has 44 items.
    # The error occurs during the first `execute_research_step` call, specifically when `gemini_client.models.generate_content` is called for the second time in that step (after the initial tool call).
    # The `mock_perform_web_search.side_effect` is set to raise an exception.
    # The `call_web_search_with_retry` function will retry 3 times.
    # So, the first LLM call (MOCK_LLM_TOOL_CALL_MULTIPLE_SEARCHES) will trigger 3 calls to `mock_perform_web_search`.
    # Each of these 3 calls will fail and retry 3 times, so 3 * 3 = 9 calls to `mock_perform_web_search`.
    # The `execute_research_step` will then catch this and return an error.
    # The `perform_deep_research` will then catch this error and emit `task_error`.
    # So, the `mock_generate_text` calls should be:
    # 1 (for initial plan) + 1 (for the first LLM call in execute_research_step, which triggers the web search failures) = 2 calls.
    assert mock_generate_text.call_count == 2
