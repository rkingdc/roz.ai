import json
import logging
import re
from typing import List, Tuple, Any, Dict, Callable

# Imports for Task 1 & 2 (Retries, Parallelization)
import concurrent.futures
import functools
import os # For os.cpu_count() in Task 3
import uuid # For Task 3 (Async PDF Transcription)
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import requests # For requests.exceptions
from googleapiclient.errors import HttpError as GoogleHttpError # For Google API client errors


# Removed ThreadPoolExecutor and as_completed imports
from flask import current_app, g  # To access config and g for client caching
import google.genai as genai # For genai.Client initialization
from google.genai import types # For GenerateContentConfig

# Assuming ai_services.py and web_search.py are in the same directory
# or accessible via the Python path.
# Use appropriate import style for your project structure (e.g., relative imports if part of a package)
from .ai_services import (
    generate_text,
    transcribe_pdf_bytes, # Needed for processing scraped PDFs
    # llm_factory, # No longer used in this file
)
from app.plugins import web_search as web_search_plugin # For perform_web_search AND fetch_web_content
from .ai_services_lib.tool_definitions import WEB_SEARCH_TOOL, WEB_SCRAPE_TOOL # Added WEB_SCRAPE_TOOL
# perform_web_search is no longer directly imported


# Configure logging
logger = logging.getLogger(__name__)


# --- Helper Functions ---


def parse_llm_json_output(llm_output: str, expected_keys: List[str]) -> Any:
    """
    Attempts to parse JSON output from the LLM.
    Handles potential JSON decoding errors and missing keys.
    """
    logger.debug(f"Attempting to parse JSON output: {llm_output[:200]}...")
    # Attempt to find the JSON block
    match = re.search(r"```json\n(.*?)\n```", llm_output, re.DOTALL)
    if match:
        json_string = match.group(1)
        logger.debug("Found JSON block.")
    else:
        # Assume the entire output is JSON if no block is found
        json_string = llm_output
        logger.debug("No JSON block found, attempting to parse entire output.")

    try:
        # Clean up common issues before parsing
        json_string = json_string.strip()
        # Remove trailing commas in objects or arrays (basic attempt)
        json_string = re.sub(r",\s*([}\]])", r"\1", json_string)

        parsed_output = json.loads(json_string)
        logger.debug("JSON parsed successfully.")

        # Optional: Validate expected keys are present
        if isinstance(parsed_output, dict):
            if all(key in parsed_output for key in expected_keys):
                logger.debug("All expected keys found.")
                return parsed_output
            else:
                logger.warning(
                    f"Parsed JSON missing expected keys. Expected: {expected_keys}, Found: {list(parsed_output.keys())}"
                )
                return None  # Or raise an error, depending on desired strictness
        elif isinstance(parsed_output, list) and expected_keys:
            # If the expected output is a list of objects, check keys in the first item
            if parsed_output and isinstance(parsed_output[0], dict):
                if all(key in parsed_output[0] for key in expected_keys):
                    logger.debug(
                        "List of objects parsed, first item has expected keys."
                    )
                    return parsed_output
                else:
                    logger.warning(
                        f"Parsed JSON list items missing expected keys. Expected: {expected_keys}, Found in first item: {list(parsed_output[0].keys())}"
                    )
                    return None
            # If it's a list (e.g. list of strings, or empty list) and expected_keys is empty, it's valid.
            # Or if it's a list of dicts but expected_keys was empty (meaning any list of dicts is fine).
            else: 
                logger.debug(
                    "Parsed JSON is a list (e.g. of strings, or dicts with no specific key check, or empty), returning as is."
                )
                return parsed_output
        # This case handles lists of non-dict items when expected_keys is empty, or any list if expected_keys is empty.
        # It's largely covered by the above 'else' now, but kept for safety for other non-dict/non-list types.
        elif isinstance(parsed_output, list) and not expected_keys: 
             return parsed_output
        else: # Handles non-dict, non-list types when expected_keys might be present (though less common)
            logger.debug(
                "Parsed JSON is not a dict or list, or no expected keys specified."
            )
            return parsed_output  # Return the parsed output as is

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON output: {e}")
        return None
    except Exception as e:
        logger.error(
            f"An unexpected error occurred during JSON parsing: {e}", exc_info=True
        )
        return None


# --- Research Plan Generation ---


# This function would typically call an LLM to generate a research plan
# based on the user's query. The LLM output would be parsed JSON.
# Example structure: [{"step_name": "...", "step_description": "..."}, ...]
def query_to_research_plan(query: str) -> List[Tuple[str, str]]:
    """
    Takes a user query and uses an LLM to generate a research plan.
    Expects the LLM to return a JSON list of [step_name, step_description] pairs.
    """
    logger.info(f"Generating research plan for query: '{query}'")
    prompt = f"""
    Based on the user query below, create a step-by-step research plan to thoroughly investigate the topic.
    Each step should have a concise 'step_name' and a detailed 'step_description' outlining the specific information to find.
    Return the plan as a JSON list of lists, where each inner list is [step_name, step_description].

    Example Format:
    ```json
    [
      ["Understand Core Concepts", "Define the fundamental principles and terminology related to the query."],
      ["Identify Key Players", "Find the main individuals, companies, or organizations involved."],
      ["Analyze Current Trends", "Research the latest developments, challenges, and opportunities."]
    ]
    ```

    User Query: "{query}"

    Research Plan (JSON):
    """
    try:
        llm_response = generate_text(prompt)
        if (
            not llm_response
            or llm_response.startswith("[Error")
            or llm_response.startswith("[System Note")
        ):
            logger.error(f"LLM failed to generate research plan: {llm_response}")
            return []

        # Basic parsing attempt (assuming JSON list of lists)
        parsed_plan = parse_llm_json_output(
            llm_response, expected_keys=[]
        )  # No specific keys for outer list

        if isinstance(parsed_plan, list) and all(
            isinstance(item, list) and len(item) == 2 for item in parsed_plan
        ):
            logger.info(
                f"Successfully generated research plan with {len(parsed_plan)} steps."
            )
            # Convert inner lists to tuples
            return [tuple(step) for step in parsed_plan]
        else:
            logger.error(
                f"LLM response for research plan was not in the expected format: {llm_response}"
            )
            # Fallback: Try simple line splitting if JSON fails? (Less reliable)
            # lines = llm_response.strip().split('\n')
            # plan = []
            # for line in lines:
            #     parts = line.split(':', 1)
            #     if len(parts) == 2:
            #         plan.append((parts[0].strip(), parts[1].strip()))
            # if plan: return plan
            return []

    except Exception as e:
        logger.error(f"Error in query_to_research_plan: {e}", exc_info=True)
        return []


# --- Unified Research Step Execution ---
def execute_research_step(
    step_description: str,
    is_cancelled_callback: Callable[[], bool],
    socketio, # For emit_status
    sid,
    app_context, # Pass Flask app context for background thread safety
    cpu_executor: concurrent.futures.ProcessPoolExecutor # For Task 3
) -> Tuple[List[str], List[Dict]]: # Returns (llm_summary_strings, pdf_futures_info_list)
    """
    Executes a single research step using an LLM to orchestrate web searches and scraping.
    Returns:
        - A list of strings, where each string is a formatted summary of a processed source (may contain placeholders for PDFs).
        - A list of dictionaries, each containing info about a submitted PDF transcription task 
          (e.g., {'placeholder': str, 'future': Future, 'original_url': str, 'original_filename': str}).
    Must be called within an active Flask app context.
    """
    logger.info(f"Executing research step: {step_description[:100]}...")
    processed_research_items = []

    with app_context:
        try:
            # --- Client Acquisition (copied from old web_search, ensure it's robust) ---
            api_key = current_app.config.get("API_KEY")
            if not api_key:
                logger.error("API_KEY is missing from current_app.config for execute_research_step.")
                return ["[System Error: AI Service API Key not configured]"]

            if "genai_client" not in g:
                logger.info("execute_research_step: Creating new genai.Client and caching in 'g'.")
                try:
                    g.genai_client = genai.Client(api_key=api_key)
                except Exception as e_client:
                    logger.error(f"execute_research_step: Failed to initialize genai.Client: {e_client}", exc_info=True)
                    return [f"[System Error: Failed to initialize AI client: {type(e_client).__name__}]"]
            
            gemini_client = g.genai_client
            if not gemini_client:
                logger.error("LLM client (g.genai_client) is unexpectedly None in execute_research_step.")
                return ["[System Error: LLM client not available after init attempt]"]
            # --- End Client Acquisition ---

            raw_model_name = current_app.config.get("DEFAULT_MODEL", "gemini-2.5-flash-preview-04-17")
            model_to_use = f"models/{raw_model_name}" if not raw_model_name.startswith("models/") else raw_model_name
            logger.info(f"execute_research_step: Using model '{model_to_use}' for research step.")

            # Prompt for Phase 1-3: Tool usage and information gathering
            tool_usage_prompt = f"""
You are an AI research assistant. Your task is to execute a research step: "{step_description}"
Follow these phases strictly:

Phase 1: Plan Search Queries
- Based on the step description, formulate 2-3 targeted search queries.

Phase 2: Execute Searches and Identify Promising URLs
- Use the `web_search` tool for each query. This tool returns search result metadata (title, link, snippet).
- Review the (title, link, snippet) for all search results.
- Identify a list of promising URLs that seem most relevant for full content extraction.

Phase 3: Scrape Content from Promising URLs
- For each promising URL identified in Phase 2, use the `scrape_url` tool to fetch its full content.
- If `scrape_url` tool returns HTML, use the extracted text.
- If `scrape_url` tool returns raw PDF data, note that it's a PDF document (include its title and link) and that its content cannot be directly read by you in this step.
- If scraping fails for a URL or a page has no useful content, note this.

After completing these three phases and all necessary tool calls, you will be asked to compile the final JSON output in a subsequent step. For now, focus on executing the research using the tools.
Indicate you are ready for the final compilation step once all searches and scraping are done.
            """

            if is_cancelled_callback():
                logger.info("Research step cancelled before LLM tool usage call.")
                return ["[AI Info: Research step cancelled by user.]"]

            # Config for tool execution phase - Manual Loop
            # Note: max_output_tokens is not strictly necessary here as we expect tool calls or short text.
            # response_mime_type is also not critical for this phase.
            tool_execution_config = types.GenerateContentConfig(
                tools=[WEB_SEARCH_TOOL, WEB_SCRAPE_TOOL], 
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)
            )
            
            if socketio and sid:
                socketio.emit("status_update", {"message": f"Researching (Tool Phase): {step_description[:30]}..."}, room=sid)

            # Step A: Manual Tool Execution Loop
            conversation_history = [types.Content(parts=[types.Part.from_text(text=tool_usage_prompt)], role="user")]
            
            MAX_TOOL_TURNS = 15 
            MAX_CONSECUTIVE_EMPTY_TOOL_CALL_TURNS = 2
            consecutive_empty_tool_turns = 0
            
            submitted_pdf_futures_info = [] # For Task 3

            # Define retryable exceptions for network/API issues (used by retry-wrapped callables)
            RETRYABLE_EXCEPTIONS = (
                requests.exceptions.Timeout,
                requests.exceptions.ConnectionError,
                requests.exceptions.RequestException, 
                GoogleHttpError, 
            )

            # Retry-wrapped callables (defined once, used in the loop)
            @retry(
                stop=stop_after_attempt(3),
                wait=wait_exponential(multiplier=1, min=2, max=10),
                retry=retry_if_exception_type(RETRYABLE_EXCEPTIONS),
                reraise=True
            )
            def call_web_search_with_retry(query_arg, num_results_arg):
                logger.info(f"Attempting web_search for '{query_arg}' (retriable)")
                return web_search_plugin.perform_web_search(query=query_arg, num_results=num_results_arg)

            @retry(
                stop=stop_after_attempt(3),
                wait=wait_exponential(multiplier=1, min=2, max=10),
                retry=retry_if_exception_type(RETRYABLE_EXCEPTIONS),
                reraise=True
            )
            def call_fetch_web_content_with_retry(url_arg):
                logger.info(f"Attempting fetch_web_content for '{url_arg}' (retriable)")
                return web_search_plugin.fetch_web_content(url=url_arg)

            for turn_count in range(MAX_TOOL_TURNS):
                if is_cancelled_callback():
                    logger.info("Research step cancelled during manual tool loop.")
                    processed_research_items.append("[AI Info: Research step cancelled by user.]")
                    return processed_research_items

                logger.info(f"Manual tool loop turn {turn_count + 1}/{MAX_TOOL_TURNS} for step: {step_description[:30]}...")
                
                response_from_model_turn = gemini_client.models.generate_content(
                    model=model_to_use,
                    contents=conversation_history,
                    config=tool_execution_config 
                )

                if not response_from_model_turn.candidates or not response_from_model_turn.candidates[0].content:
                    logger.error("No valid candidate/content in LLM's turn response during tool phase.")
                    processed_research_items.append("[System Error: LLM response missing content during tool phase.]")
                    break 
                
                model_response_content = response_from_model_turn.candidates[0].content
                conversation_history.append(model_response_content)

                tasks_for_this_llm_response = []
                for part in model_response_content.parts:
                    if part.function_call:
                        fc = part.function_call
                        fc_name = fc.name
                        fc_args = dict(fc.args)
                        logger.info(f"LLM requested tool call: {fc_name} with args: {fc_args}")
                        
                        callable_task = None
                        if fc_name == "web_search":
                            query = fc_args.get("query", "")
                            num_results = fc_args.get("num_results", 5)
                            callable_task = functools.partial(call_web_search_with_retry, query_arg=query, num_results_arg=num_results)
                        elif fc_name == "scrape_url":
                            url_to_scrape = fc_args.get("url")
                            if url_to_scrape:
                                callable_task = functools.partial(call_fetch_web_content_with_retry, url_arg=url_to_scrape)
                            else:
                                logger.error(f"scrape_url call from LLM missing 'url' argument: {fc_args}")
                                # Immediately prepare an error response for this specific bad call
                                err_resp_part = types.Part.from_function_response(
                                    name=fc_name, 
                                    response={"error": {"type": "argument_error", "message": "URL not provided for scrape_url"}}
                                )
                                conversation_history.append(types.Content(parts=[err_resp_part], role="tool"))
                                continue # to next part in model_response_content.parts
                        else:
                            logger.warning(f"LLM requested unknown tool: {fc_name}")
                            err_resp_part = types.Part.from_function_response(
                                name=fc_name, 
                                response={"error": {"type": "unknown_tool", "message": f"Unknown tool: {fc_name}"}}
                            )
                            conversation_history.append(types.Content(parts=[err_resp_part], role="tool"))
                            continue
                        
                        if callable_task:
                            tasks_for_this_llm_response.append({'callable': callable_task, 'original_fc': fc})
                
                if not tasks_for_this_llm_response:
                    # LLM did not request any tools in this turn, it might have provided text.
                    logger.info("LLM provided text response or no tools in this turn, exiting manual tool loop.")
                    consecutive_empty_tool_turns +=1
                    if consecutive_empty_tool_turns >= MAX_CONSECUTIVE_EMPTY_TOOL_CALL_TURNS:
                        logger.warning(f"LLM provided no tool calls for {MAX_CONSECUTIVE_EMPTY_TOOL_CALL_TURNS} consecutive turns. Breaking tool loop.")
                        break
                    # If it's just one turn of no tools, maybe it's thinking or summarizing before a final JSON.
                    # The main loop break condition is if LLM outputs text (no function_call).
                    # If there was any text part in model_response_content.parts, we assume it's done.
                    has_text_part = any(part.text for part in model_response_content.parts if hasattr(part, 'text'))
                    if has_text_part:
                        break # Exit loop, proceed to final JSON generation
                    else: # No text and no tools, this is an empty response from LLM.
                        logger.warning("LLM returned no tools and no text. Continuing tool loop for now.")
                        continue # Next turn of the tool loop
                else:
                    consecutive_empty_tool_turns = 0 # Reset counter if tools were called
                    
                    function_response_parts_batch = []
                    # Max workers for I/O bound tasks like web requests
                    # TODO: Consider making this configurable or dynamic
                    num_workers = min(len(tasks_for_this_llm_response), 10) 
                    
                    if socketio and sid:
                        socketio.emit("status_update", {"message": f"Executing {len(tasks_for_this_llm_response)} tool(s) in parallel..."}, room=sid)

                    with concurrent.futures.ThreadPoolExecutor(max_workers=num_workers) as executor:
                        future_to_fc_info = {
                            executor.submit(task_info['callable']): task_info['original_fc']
                            for task_info in tasks_for_this_llm_response
                        }

                        for future in concurrent.futures.as_completed(future_to_fc_info):
                            original_fc = future_to_fc_info[future]
                            fc_name = original_fc.name
                            function_response_data_for_llm = {}
                            try:
                                tool_call_result_data = future.result() # This is the direct return from the plugin function

                                if fc_name == "web_search":
                                    function_response_data_for_llm = {"results": tool_call_result_data}
                                elif fc_name == "scrape_url":
                                    if tool_call_result_data['type'] == 'pdf' and isinstance(tool_call_result_data['content'], bytes):
                                        pdf_bytes = tool_call_result_data['content']
                                        pdf_filename = tool_call_result_data.get('filename', 'scraped.pdf')
                                        original_url = tool_call_result_data.get('url', 'unknown_url')
                                        placeholder_id = str(uuid.uuid4())
                                        placeholder_string_for_llm = f"PDF_CONTENT_PENDING_ID_{placeholder_id}"
                                        
                                        logger.info(f"Submitting PDF for async transcription: {pdf_filename}, placeholder: {placeholder_string_for_llm}")
                                        if socketio and sid:
                                            socketio.emit("status_update", {"message": f"PDF queued for transcription: {pdf_filename[:25]}..."}, room=sid)
                                        
                                        transcription_future = cpu_executor.submit(transcribe_pdf_bytes, pdf_bytes, pdf_filename)
                                        submitted_pdf_futures_info.append({
                                            'placeholder': placeholder_string_for_llm,
                                            'future': transcription_future,
                                            'original_url': original_url, # Store for context
                                            'original_filename': pdf_filename
                                        })
                                        # Respond to LLM that transcription is pending
                                        function_response_data_for_llm = {
                                            "status": "pdf_transcription_submitted", 
                                            "url": original_url, 
                                            "filename": pdf_filename, 
                                            "content_placeholder": placeholder_string_for_llm
                                        }
                                    else: # HTML or error from scrape
                                        function_response_data_for_llm = {"scraped_data": tool_call_result_data}
                                else: 
                                    function_response_data_for_llm = {"error": f"Unknown tool {fc_name} result processing."}
                                
                            except RETRYABLE_EXCEPTIONS as retry_exc:
                                error_msg = f"Tool call {fc_name} failed after multiple retries: {type(retry_exc).__name__} - {str(retry_exc)}"
                                logger.error(error_msg, exc_info=False) # No need for full exc_info for retries
                                function_response_data_for_llm = {"error": {"type": "tool_retry_failed", "message": error_msg}}
                            except Exception as exc:
                                error_msg = f"Exception executing tool {fc_name} in parallel: {type(exc).__name__} - {str(exc)}"
                                logger.error(error_msg, exc_info=True)
                                function_response_data_for_llm = {"error": {"type": "parallel_tool_execution_error", "message": error_msg}}
                            
                            function_response_parts_batch.append(
                                types.Part.from_function_response(name=fc_name, response=function_response_data_for_llm)
                            )
                    
                    if function_response_parts_batch:
                        conversation_history.append(types.Content(parts=function_response_parts_batch, role="tool"))
                    # Continue to the next turn of the tool loop
            else: # Loop finished due to MAX_TOOL_TURNS
                logger.warning(f"Exceeded MAX_TOOL_TURNS ({MAX_TOOL_TURNS}). Proceeding to final JSON generation.")


            if is_cancelled_callback():
                logger.info("Research step cancelled after manual tool loop, before final JSON generation.")
                processed_research_items.append("[AI Info: Research step cancelled by user.]")
                return processed_research_items

            # Step B: Final JSON Generation
            final_json_prompt_text = """
Based on our entire preceding interaction, including all search queries, search results, and scraped content:
Compile all the gathered information. For each distinct source of information you considered (whether successfully scraped, a PDF, failed scrape, or snippet-only), format it as a string:
"Title: [Title]\nLink: [URL]\nSnippet: [Original snippet]\nContent: [Summary of scraped content / 'PDF document, content not directly viewable.' / 'Scraping failed.' / 'Snippet only.']\n---"

Your *FINAL and ONLY* output for this entire multi-phase task MUST be a single JSON list containing all these formatted source strings.
This JSON list should be the *only content* in your response. Do not include any other text, commentary, or acknowledgments.
"""
            # Add this new instruction to the conversation history
            conversation_history.append(types.Content(parts=[types.Part.from_text(text=final_json_prompt_text)], role="user"))

            max_tokens_final = current_app.config.get("DEFAULT_MAX_OUTPUT_TOKENS", 8192)
            final_json_generation_config = types.GenerateContentConfig(
                tool_config=types.ToolConfig(
                    function_calling_config=types.FunctionCallingConfig(mode=types.FunctionCallingConfigMode.NONE)
                ),
                max_output_tokens=max_tokens_final,
                response_mime_type='text/plain'
            )

            if socketio and sid:
                socketio.emit("status_update", {"message": f"Compiling research: {step_description[:30]}..."}, room=sid)
            
            final_response = gemini_client.models.generate_content(
                model=model_to_use,
                contents=conversation_history, # Pass the whole history
                config=final_json_generation_config
            )

            final_model_output_text = None
            if final_response.candidates and final_response.candidates[0].content and final_response.candidates[0].content.parts:
                # The model's final textual reply should be the last part.
                for part in reversed(final_response.candidates[0].content.parts): # Check the last response's parts
                    if part.text:
                        final_model_output_text = part.text
                        break
                if not final_model_output_text and final_response.text:
                     logger.info("Using final_response.text as fallback for final JSON output.")
                     final_model_output_text = final_response.text


            if final_model_output_text:
                logger.debug(f"LLM final JSON output text for research step: {final_model_output_text[:500]}")
                parsed_items = parse_llm_json_output(final_model_output_text, expected_keys=[]) # Expecting a list of strings
                if isinstance(parsed_items, list) and all(isinstance(item, str) for item in parsed_items):
                    processed_research_items.extend(parsed_items)
                    logger.info(f"Successfully processed {len(parsed_items)} items for research step.")
                else:
                    logger.error(f"LLM response for final JSON was not a JSON list of strings: {final_model_output_text[:500]}")
                    processed_research_items.append(f"[System Error: LLM did not return a valid JSON list of research items for '{step_description}'. Raw response: {final_model_output_text[:200]}]")
            else:
                logger.warning(f"LLM returned no discernible final JSON text for research step: {step_description}")
                if final_response.prompt_feedback and final_response.prompt_feedback.block_reason:
                    reason = final_response.prompt_feedback.block_reason
                    msg = final_response.prompt_feedback.block_reason_message
                    logger.error(f"Prompt blocked for final JSON generation. Reason: {reason}, Message: {msg}")
                    processed_research_items.append(f"[System Error: Prompt blocked by API for final JSON - {reason}.]")
                else:
                    processed_research_items.append(f"[System Error: LLM returned no usable JSON output for '{step_description}'.]")

        except Exception as e:
            logger.error(f"Error during execute_research_step for '{step_description}': {e}", exc_info=True)
            processed_research_items.append(f"[System Error: Exception during research step execution - {type(e).__name__}]")

        return processed_research_items, submitted_pdf_futures_info


# --- Research Plan Update ---


# This function would call an LLM to update the research plan
# based on the initial search results.
def query_and_research_to_updated_plan(
    query: str, collected_research: Dict[str, List[str]]
) -> List[Tuple[str, str]]:
    """
    Takes the original query and collected research, asks an LLM to refine the research plan
    into a report outline. Expects JSON list of [section_name, section_description] pairs.
    """
    logger.info("Generating updated report plan based on collected research.")

    # Format the collected research for the prompt (provide snippets or summaries)
    research_summary = str(collected_research)

    prompt = f"""
Given the original user query and the collected research snippets below, create a **detailed and comprehensive** plan for writing a final report. This plan should outline the **main sections** of the report, **reflecting the key areas identified in the query and the significant findings from the research.**

**Ensure the plan is broken down into multiple logical sections that cover the breadth of the research findings relevant to the user query. Avoid collapsing distinct topics or significant findings into a single section if the research provides sufficient information for separate discussion.**

Each step should represent a distinct section of the report and have a concise 'section_name' (suitable as a report heading). The 'section_description' for each step should outline the key points to cover in that specific section, **based *only* on the research gathered. Elaborate on the findings within each section description.**

Return the plan as a JSON list of lists, where each inner list is [section_name, section_description].

Example Format:
```json
[
  ["Introduction", "Define the core concepts based on research findings and state the report's purpose, drawing from the query and snippets."],
  ["Historical Context of [Topic]", "Based on research, detail the background and evolution of the topic."],
  ["Key Drivers and Factors", "Summarize the main influences and contributing factors identified in the snippets."],
  ["Challenges and Obstacles", "Outline the primary difficulties and impediments found in the research."],
  ["Potential Solutions or Approaches", "Describe possible ways to address the challenges, if supported by research."],
  ["Future Outlook/Trends", "Present any forward-looking insights or observed trends from the snippets."],
  ["Conclusion", "Synthesize the main findings from the research snippets and summarize the report's key takeaways."]
]


Note: This example structure is illustrative and the actual sections should be derived directly from the research and query.

Original User Query: "{query}"

Collected Research Snippets:
{research_summary}

Refined Report Plan (JSON):
    """
    try:
        llm_response = generate_text(prompt)
        if (
            not llm_response
            or llm_response.startswith("[Error")
            or llm_response.startswith("[System Note")
        ):
            logger.error(f"LLM failed to generate updated plan: {llm_response}")
            return []

        parsed_plan = parse_llm_json_output(llm_response, expected_keys=[])

        if isinstance(parsed_plan, list) and all(
            isinstance(item, list) and len(item) == 2 for item in parsed_plan
        ):
            logger.info(
                f"Successfully generated updated report plan with {len(parsed_plan)} sections."
            )
            # Convert inner lists to tuples
            return [tuple(step) for step in parsed_plan]
        else:
            logger.error(
                f"LLM response for updated plan was not in the expected format: {llm_response}"
            )
            return []

    except Exception as e:
        logger.error(f"Error in query_and_research_to_updated_plan: {e}", exc_info=True)
        return []


# --- Report Synthesis ---

# These functions would call an LLM to synthesize research into report sections.


def synthesize_research_into_report_section(
    section_name: str, section_description: str, all_raw_research_items: List[str]
) -> Tuple[str, List[str]]:
    """
    Uses an LLM to synthesize collected research (provided as raw dicts) into a coherent report section.
    Also extracts or generates references used in the section.
    Expects LLM to return JSON: {"report_section": "...", "references": ["ref1", "ref2"]}
    """
    logger.info(f"Synthesizing research for section: '{section_name}'")

    # Format research for the prompt using the raw dictionaries
    # Ensure content extraction handles different types (text, transcription, error notes)

    formatted_research = "\n\n---\n\n".join(all_raw_research_items)

    prompt = f"""
You are a research assistant writing a section for a report.
Your task is to synthesize the provided research findings into a well-structured report section and include inline citations using a specific Markdown link format.

Section Name: "{section_name}"
Section Description (Key points to cover): "{section_description}"

Provided Research (Multiple sources, including URLs, snippets, and content):
--- START RESEARCH ---
{formatted_research}
--- END RESEARCH ---

*Note: Each source in 'Provided Research' starts with "Source N:", followed by Title, Link, Snippet, and Content.*

Instructions:
1.  Write the report section based *only* on the information contained within the `Provided Research`. Focus on the 'Content' part of each source, but use Title/Snippet for context if needed. Do not include outside knowledge.
2.  Structure the section logically using Markdown (headings, paragraphs, lists, bolding). Start with a Level 2 Heading (## {section_name}).
3.  Accurately and factually reflect the information found in the sources.
4.  **Crucially: Include inline citations for all factual claims, statistics, and significant information derived from the research.**
    *   Cite the original source(s) immediately after the sentence, clause, or fact it supports.
    *   Use the Markdown link format `[[SourceNumber]](URL)`.
    *   The `SourceNumber` is the number from the 'Source N:' identifier (e.g., use `1` for 'Source 1:', `2` for 'Source 2:').
    *   The `URL` is the 'Link:' provided for that specific source in the `Provided Research` section. If a link is missing or invalid (e.g., "No Link Provided"), cite as `[[N]]()` or just `[Source N]` without a link.
    *   The Markdown format `[[N]](URL)` means the rendered text will be `[N]` (including the brackets), and this entire `[N]` will be a clickable link to the URL.
    *   If a piece of information is supported by multiple sources, include multiple citations sequentially (e.g., `...key finding.[[1]](url1)[[3]](url3)`).
5.  After writing the section, list the identifiers of the sources (using the "Source N" format, e.g., "Source 1", "Source 3") that were *actually cited* within the section content.

Return your response as a JSON object with two keys:
-   `report_section`: A string containing the full Markdown text of the report section, including the inline citations formatted as `[[Number]](URL)` (or `[[Number]]()` if no valid URL).
-   `references`: A JSON list of strings, where each string is the identifier of a source that was cited in the `report_section` (e.g., `["Source 1", "Source 2"]`).

Example JSON Output:
```json
{{
  "report_section": "## Example Section Title\\n\\nBased on initial findings, the project aims to address key challenges identified in the market [[1]](https://example.com/source1). These challenges include regulatory hurdles [[2]](https://example.com/source2) and funding limitations [[1]](https://example.com/source1). A recent study highlights that similar projects faced significant delays [[3]](https://example.com/source3). The team is exploring alternative strategies [[1]](https://example.com/source1)[[2]](https://example.com/source2).\\n\\nFurthermore, stakeholder feedback emphasized the need for greater transparency [[4]](https://example.com/source4).",
  "references": ["Source 1", "Source 2", "Source 3", "Source 4"]
}}


JSON Output:
    """
    try:
        llm_response = generate_text(prompt)
        if (
            not llm_response
            or llm_response.startswith("[Error")
            or llm_response.startswith("[System Note")
        ):
            logger.error(
                f"LLM failed to synthesize report section '{section_name}': {llm_response}"
            )
            return (
                f"## {section_name}\n\n[Error: LLM failed to generate this section.]\n",
                [],
            )

        parsed_data = parse_llm_json_output(
            llm_response, expected_keys=["report_section", "references"]
        )

        if (
            parsed_data
            and isinstance(parsed_data.get("report_section"), str)
            and isinstance(parsed_data.get("references"), list)
        ):
            section_text = parsed_data["report_section"]
            references = parsed_data["references"]
            logger.info(
                f"Successfully synthesized section '{section_name}' (Length: {len(section_text)}, References: {len(references)})."
            )
            return section_text, references
        else:
            logger.error(
                f"LLM response for section synthesis was not in the expected format: {llm_response}"
            )
            # Fallback: return the raw response as the section?
            return (
                f"## {section_name}\n\n[Error: Failed to parse LLM response for this section. Raw response below.]\n\n{llm_response}\n",
                [],
            )

    except Exception as e:
        logger.error(
            f"Error in synthesize_research_into_report_section for '{section_name}': {e}",
            exc_info=True,
        )
        return (
            f"## {section_name}\n\n[Error: Exception during section synthesis: {e}]\n",
            [],
        )


def create_exec_summary(report_content: str) -> str:
    """Uses an LLM to create an executive summary from the full report content."""
    logger.info("Generating executive summary.")
    prompt = f"""
    Based on the full report content provided below, write a concise executive summary.
    The summary should briefly introduce the topic, highlight the key findings from each section, and state the main conclusions.
    Use Markdown formatting. Start with a Level 1 Heading: # Executive Summary.

    Full Report Content:
    --- START REPORT ---
    {report_content}
    --- END REPORT ---

    Executive Summary (Markdown):
    """
    try:
        summary = generate_text(prompt)
        if (
            summary
            and not summary.startswith("[Error")
            and not summary.startswith("[System Note")
        ):
            logger.info("Successfully generated executive summary.")
            return summary
        else:
            logger.error(f"Failed to generate executive summary: {summary}")
            return "# Executive Summary\n\n[Error: Failed to generate executive summary.]\n"
    except Exception as e:
        logger.error(f"Error in create_exec_summary: {e}", exc_info=True)
        return f"# Executive Summary\n\n[Error: Exception during summary generation - {e}]\n"


def create_next_steps(report_content: str) -> str:
    """Uses an LLM to suggest next steps or further research based on the report."""
    logger.info("Generating next steps section.")
    prompt = f"""
    Based on the full report content provided below, suggest potential next steps or areas for further research.
    Consider any gaps identified, unanswered questions, or logical extensions of the findings.
    Use Markdown formatting. Start with a Level 1 Heading: # Next Steps / Further Research.

    Full Report Content:
    --- START REPORT ---
    {report_content}
    --- END REPORT ---

    Next Steps / Further Research (Markdown):
    """
    try:
        next_steps = generate_text(prompt)
        if (
            next_steps
            and not next_steps.startswith("[Error")
            and not next_steps.startswith("[System Note")
        ):
            logger.info("Successfully generated next steps.")
            return next_steps
        else:
            logger.error(f"Failed to generate next steps: {next_steps}")
            return "# Next Steps / Further Research\n\n[Error: Failed to generate next steps.]\n"
    except Exception as e:
        logger.error(f"Error in create_next_steps: {e}", exc_info=True)
        return f"# Next Steps / Further Research\n\n[Error: Exception during next steps generation - {e}]\n"





def final_report(
    executive_summary: str, report_body: str, next_steps: str,
) -> str:
    """Uses an LLM to assemble and format the final report from its components."""
    logger.info("Formatting final report using LLM.")

    prompt = f"""
You are tasked with assembling and formatting a final research report from its constituent parts using Markdown.
Ensure the report flows logically, uses appropriate headings (e.g., #, ##), and applies selective bolding for emphasis on key terms or findings. Make sure to add a sensible title.

Here are the components:

**1. Executive Summary:**
--- START ---
{executive_summary}
--- END ---

**2. Report Body (contains the main sections):**
--- START ---
{report_body}
--- END ---

**3. Next Steps / Further Research:**
--- START ---
{next_steps}
--- END ---


**Instructions:**
1. Combine these sections into a single, coherent Markdown document.
2. Use appropriate Markdown heading levels (e.g., `# Executive Summary`, `## Section Title`, `# Next Steps / Further Research`).
3. Conservatively apply selective **bolding** to highlight important terms, concepts, or conclusions within the text.
4. Do not add any commentary outside the report content itself.

**Final Formatted Report (Markdown):**
"""

    try:
        formatted_report = generate_text(prompt)
        if (
            formatted_report
            and not formatted_report.startswith("[Error")
            and not formatted_report.startswith("[System Note")
        ):
            logger.info("Successfully formatted final report using LLM.")
            # Clean up potential markdown code block fences if the LLM adds them
            formatted_report = re.sub(
                r"^```markdown\n?", "", formatted_report, flags=re.IGNORECASE
            )
            formatted_report = re.sub(r"\n?```$", "", formatted_report)
            return formatted_report.strip()
        else:
            logger.error(f"LLM failed to format the final report: {formatted_report}")
            # Fallback to basic concatenation if LLM fails
            return f"{executive_summary}\n\n---\n\n{report_body}\n\n---\n\n{next_steps}\n\n---".strip()
    except Exception as e:
        logger.error(f"Error during final report formatting: {e}", exc_info=True)
        # Fallback to basic concatenation on exception
        return f"{executive_summary}\n\n---\n\n{report_body}\n\n---\n\n{next_steps}\n\n---".strip()


from typing import Callable # Import Callable

# --- Main Deep Research Orchestration ---
def perform_deep_research(
    query: str,
    socketio=None,
    sid=None,
    chat_id=None,
    is_cancelled_callback: Callable[[], bool] = lambda: False # Add callback
) -> None:
    """
    Orchestrates the deep research process from query to final report.
    Checks for cancellation periodically.
    Emits results ('deep_research_result'), cancellation ('generation_cancelled'), or errors ('task_error') via SocketIO.
    Saves the final report/error to the database.
    """
    logger.info(
        f"--- Starting Deep Research for Query: '{query}' (SID: {sid}, ChatID: {chat_id}) ---"
    )

    final_report_content = None  # To store the final report or error for DB saving

    def emit_status(message):
        if socketio and sid:
            logger.info(f"Status Update (SID: {sid}): {message}")
            socketio.emit("status_update", {"message": message}, room=sid)

    def emit_cancellation_or_error(message, is_cancel=False, save_to_db=True):
        nonlocal final_report_content
        log_level = logging.INFO if is_cancel else logging.ERROR
        log_prefix = "Cancelled" if is_cancel else "Error"
        logger.log(
            log_level,
            f"Deep Research {log_prefix} (SID: {sid}, ChatID: {chat_id}): {message}"
        )
        final_report_content = message # Store message for DB saving
        if socketio and sid:
            if is_cancel:
                socketio.emit("generation_cancelled", {"message": message, "chat_id": chat_id}, room=sid)
            else:
                socketio.emit("task_error", {"error": message}, room=sid)
        # Save message to DB if requested
        if save_to_db and chat_id is not None:
            try:
                logger.info(
                    f"Attempting to save deep research error message for chat {chat_id}."
                )
                from . import (
                    database as db,
                )  # Local import to avoid circular dependency issues at top level

                db.add_message_to_db(chat_id, "assistant", final_report_content)
            except Exception as db_err:
                logger.error(
                    f"Failed to save deep research {'cancellation' if is_cancel else 'error'} to DB for chat {chat_id}: {db_err}",
                    exc_info=True,
                )
        return None # Indicate failure/cancellation

    # --- Check for socketio/sid ---
    if not socketio or not sid:
        logger.error("perform_deep_research called without socketio or sid.")
        # Cannot emit error, just log and return
        return

    # --- Get Flask app context ---
    # This is necessary because this function runs in a background thread started by SocketIO
    # and needs access to app.config, g, etc. for the AI/DB calls.
    app = current_app._get_current_object()
    
    # Task 3: Initialize ProcessPoolExecutor for CPU-bound tasks (PDF transcription)
    # Determine a reasonable number of workers, e.g., half of CPU cores or a fixed small number
    # os.cpu_count() might be None, so provide a fallback.
    num_cpu_workers = max(1, (os.cpu_count() or 4) // 2) 
    logger.info(f"Initializing ProcessPoolExecutor with {num_cpu_workers} workers for PDF transcription.")
    # cpu_executor should be managed within the app_context if it needs app context itself,
    # or if transcribe_pdf_bytes needs it. Assuming transcribe_pdf_bytes is self-contained or gets context.
    # For simplicity, let's create it here. It will be passed to execute_research_step.
    
    all_pending_pdf_details = [] # To store {'placeholder': str, 'future': Future, 'step_name': str, 'item_indices_in_step': List[int]}
    PDF_TRANSCRIPTION_TIMEOUT = 120 # seconds

    with app.app_context(), concurrent.futures.ProcessPoolExecutor(max_workers=num_cpu_workers) as cpu_executor:
        try:
            # --- Start Actual Research Process ---

            # --- Cancellation Check ---
        if is_cancelled_callback():
            return emit_cancellation_or_error("[AI Info: Deep research cancelled before starting.]", is_cancel=True)

        emit_status("Generating initial research plan...")
        # 1. Generate Initial Research Plan
        research_plan: List[Tuple[str, str]] = query_to_research_plan(query) # Needs app context, but not cancellation check
        if not research_plan:
            return emit_cancellation_or_error(
                "[Error: Could not generate initial research plan.]", is_cancel=False
            )
        logger.info(
            f"Initial Research Plan (SID: {sid}):\n{json.dumps(research_plan, indent=2)}"
        )
        emit_status(f"Generated {len(research_plan)} initial research steps.")

        # 2. Prepare for Research Execution
    collected_research: Dict[str, List[str]] = (
        {}
    )  # Stores lists of formatted research item strings per step name

    # 3. Execute Initial Research Steps Sequentially
    logger.info(
        f"--- Executing {len(research_plan)} Initial Research Steps Sequentially (SID: {sid}) ---"
    )
    emit_status("Performing initial research...")
    step_counter = 0
    for step_name, step_description in research_plan:
        # --- Cancellation Check (before each step) ---
        if is_cancelled_callback():
            return emit_cancellation_or_error(f"[AI Info: Deep research cancelled before step '{step_name}'.]", is_cancel=True)

        step_counter += 1
        emit_status(
            f"Research Step {step_counter}/{len(research_plan)}: {step_name}..."
        )
        logger.info(f"--- Starting Research Step: {step_name} (SID: {sid}) ---")
        
        try:
            llm_summary_strings, step_pdf_futures_info = execute_research_step(
                step_description,
                is_cancelled_callback,
                socketio,
                sid,
                app.app_context(), # Pass the app context
                cpu_executor # Pass the executor
            )
            collected_research[step_name] = llm_summary_strings
            if step_pdf_futures_info:
                for pdf_info in step_pdf_futures_info:
                    all_pending_pdf_details.append({**pdf_info, "step_name": step_name})
                logger.info(f"Queued {len(step_pdf_futures_info)} PDFs for transcription from step '{step_name}'.")
            
            logger.info(
                f"--- Finished Research Step: {step_name} - Collected {len(llm_summary_strings)} initial items (PDFs pending) ---"
            )

        except Exception as e:
            logger.error(
                f"Error executing research step '{step_name}' (SID: {sid}): {e}",
                exc_info=True,
            )
            error_msg = f"[System Error: Failed during research step '{step_name}': {type(e).__name__}]"
            collected_research[step_name] = [error_msg]

    logger.info(
        f"--- Finished Sequential Execution of Initial Research Steps (SID: {sid}) ---"
    )
    emit_status("Initial research complete. Refining report plan...")

    # --- Cancellation Check ---
    if is_cancelled_callback():
        return emit_cancellation_or_error("[AI Info: Deep research cancelled before refining plan.]", is_cancel=True)

    # Log collected research summary
    for step, items in collected_research.items():
        logger.debug(
            f"Step '{step}': Collected {len(items)} research items."
        )

    # 4. Generate Updated Report Plan (Outline) based on initial findings
    # Note: query_and_research_to_updated_plan expects Dict[str, List[str]]
    # where the list contains strings (snippets/content). Our collected_research matches this.
    updated_report_plan: List[Tuple[str, str]] = query_and_research_to_updated_plan(
        query, collected_research
    )
    if not updated_report_plan:
        # Handle case where updated plan generation fails
        logger.error(
            f"Failed to generate updated report plan (SID: {sid}). Aborting synthesis."
        )
        # Combine collected research into a basic error report
        error_report_body = "\n\n".join(
            [
                f"## {step}\n\n" + "\n".join(content)
                for step, content in collected_research.items()
            ]
        )
        error_msg = f"# Deep Research Error\n\nFailed to generate the report outline after initial research.\n\n## Collected Research Snippets:\n\n{error_report_body}"
        return emit_cancellation_or_error(error_msg, is_cancel=False)

    logger.info(
        f"Updated Report Plan (SID: {sid}):\n{json.dumps(updated_report_plan, indent=2)}"
    )
    emit_status(f"Refined report plan with {len(updated_report_plan)} sections.")

    # 4.5 Perform additional research for *new* sections identified in the updated plan (Sequentially).
    logger.info(
        f"--- Checking for and executing additional research based on updated plan (Sequentially) (SID: {sid}) ---"
    )
    original_step_names = {name for name, desc in research_plan}
    new_sections_to_research = []

    # Identify sections needing research
    for section_name, section_description in updated_report_plan:
        if section_name not in original_step_names:
            new_sections_to_research.append((section_name, section_description))
            # Initialize result lists immediately to avoid key errors later
            if section_name not in collected_research:
                collected_research[section_name] = []
            # collected_raw_results is removed
        else:
            logger.debug(
                f"Section '{section_name}' was part of initial research, skipping additional search."
            )

        # Execute research for new sections sequentially
    if new_sections_to_research:
        step_counter = 0
        for section_name, section_description in new_sections_to_research:
            # --- Cancellation Check (before each additional step) ---
            if is_cancelled_callback():
                return emit_cancellation_or_error(f"[AI Info: Deep research cancelled before additional research for '{section_name}'.]", is_cancel=True)

            step_counter += 1
            emit_status(
                f"Additional Research {step_counter}/{len(new_sections_to_research)}: {section_name}..."
            )
            logger.info(
                f"--- Starting Additional Research Step: {section_name} (SID: {sid}) ---"
            )
            logger.debug(f"Description: {section_description}")
            try:
                llm_summary_strings, step_pdf_futures_info = execute_research_step(
                    section_description, # Renamed from step_description for clarity in this loop
                    is_cancelled_callback,
                    socketio,
                    sid,
                    app.app_context(), # Pass the app context
                    cpu_executor # Pass the executor
                )
                # Ensure collected_research[section_name] is a list and extend it
                if section_name not in collected_research or not isinstance(collected_research[section_name], list):
                    collected_research[section_name] = []
                collected_research[section_name].extend(llm_summary_strings)
                
                if step_pdf_futures_info:
                    for pdf_info in step_pdf_futures_info:
                        all_pending_pdf_details.append({**pdf_info, "step_name": section_name})
                    logger.info(f"Queued {len(step_pdf_futures_info)} PDFs for transcription from additional research step '{section_name}'.")

                logger.info(
                    f"--- Finished Additional Research Step: {section_name} - Collected {len(llm_summary_strings)} initial items (PDFs pending) ---"
                )
            except Exception as e:
                logger.error(
                    f"Error executing research step '{section_name}' (SID: {sid}): {e}",
                    exc_info=True,
                )
                # If execute_research_step itself fails catastrophically
                if section_name not in collected_research or not isinstance(collected_research[section_name], list):
                    collected_research[section_name] = [] # Initialize if not already
                collected_research[section_name].append(f"[System Error: Unhandled exception during research for '{section_name}': {type(e).__name__}]")

        logger.info(
            f"--- Finished sequential execution of additional research for {len(new_sections_to_research)} section(s) (SID: {sid}) ---"
        )
        emit_status("Additional research complete.")
    else:
        logger.info(
            f"--- No new sections required additional research (SID: {sid}) ---"
        )
        emit_status("No additional research needed.")

    # Task 3: Process Pending PDF Transcriptions
    if all_pending_pdf_details:
        emit_status(f"Processing {len(all_pending_pdf_details)} pending PDF transcriptions...")
        logger.info(f"Waiting for {len(all_pending_pdf_details)} PDF transcription tasks to complete...")
        
        for detail_idx, detail in enumerate(all_pending_pdf_details):
            if is_cancelled_callback():
                logger.info("PDF transcription processing cancelled.")
                # Potentially mark remaining items as cancelled if needed, or just stop.
                break 
            
            placeholder = detail['placeholder']
            future = detail['future']
            step_name_for_pdf = detail['step_name']
            original_url = detail.get('original_url', 'N/A')
            original_filename = detail.get('original_filename', 'N/A')

            emit_status(f"Waiting for PDF transcription {detail_idx + 1}/{len(all_pending_pdf_details)}: {original_filename[:30]}...")
            logger.info(f"Waiting for transcription: {placeholder} (URL: {original_url})")
            
            transcribed_text = f"[Error: PDF transcription result not processed for {placeholder}]" # Default
            try:
                # Wait for the transcription future to complete with a timeout
                transcribed_text_result = future.result(timeout=PDF_TRANSCRIPTION_TIMEOUT)
                if transcribed_text_result.startswith(("[Error", "[System Note")):
                    logger.warning(f"Transcription for {placeholder} (URL: {original_url}) failed with note: {transcribed_text_result}")
                    transcribed_text = f"[Transcription Error for {original_filename}: {transcribed_text_result}]"
                else:
                    transcribed_text = transcribed_text_result.strip()
                    logger.info(f"Successfully transcribed {placeholder} (URL: {original_url}). Length: {len(transcribed_text)}")
            except TimeoutError:
                logger.error(f"PDF transcription timed out for {placeholder} (URL: {original_url}) after {PDF_TRANSCRIPTION_TIMEOUT}s.")
                transcribed_text = f"[Error: PDF transcription timed out for {original_filename}]"
            except Exception as e_trans:
                logger.error(f"PDF transcription failed for {placeholder} (URL: {original_url}): {e_trans}", exc_info=True)
                transcribed_text = f"[Error: PDF transcription failed for {original_filename} - {type(e_trans).__name__}]"

            # Update the collected_research item containing the placeholder
            if step_name_for_pdf in collected_research:
                updated_items_for_step = []
                found_placeholder = False
                for item_string in collected_research[step_name_for_pdf]:
                    if placeholder in item_string:
                        # Replace the placeholder part. Assuming format "Content: PDF_CONTENT_PENDING_ID_xxx\n---"
                        # This replacement needs to be robust.
                        # A simple replace might be "Content: " + placeholder -> "Content: " + transcribed_text
                        # Or more specifically: item_string.replace(placeholder, transcribed_text)
                        # Let's assume the placeholder is unique enough.
                        new_item_string = item_string.replace(placeholder, transcribed_text)
                        if new_item_string == item_string: # If replace didn't happen (e.g. placeholder format mismatch)
                            logger.warning(f"Placeholder '{placeholder}' not found as expected in research item for step '{step_name_for_pdf}'. Item: {item_string[:100]}")
                            updated_items_for_step.append(item_string) # Keep original
                        else:
                            updated_items_for_step.append(new_item_string)
                            found_placeholder = True
                            logger.info(f"Updated item in step '{step_name_for_pdf}' with transcription for '{placeholder}'.")
                    else:
                        updated_items_for_step.append(item_string)
                if not found_placeholder:
                     logger.warning(f"Could not find placeholder '{placeholder}' in any research items for step '{step_name_for_pdf}'. Transcription for {original_url} might be lost.")
                collected_research[step_name_for_pdf] = updated_items_for_step
            else:
                logger.warning(f"Step name '{step_name_for_pdf}' for PDF placeholder '{placeholder}' not found in collected_research.")
        
        emit_status("PDF transcription processing complete.")
        logger.info("Finished processing all PDF transcription tasks.")

    # 5. Synthesize Report Sections based on the *updated* plan (Sequentially)
    logger.info(
        f"--- Synthesizing {len(updated_report_plan)} Report Sections Sequentially (SID: {sid}) ---"
    )
    emit_status("Synthesizing report sections...")
    report_sections_results: Dict[str, str] = {}  # Stores generated section text
    report_references_results: Dict[str, List[str]] = (
        {}
    )  # Stores references used per section

    # Execute synthesis sequentially
    step_counter = 0
    for section_name, section_description in updated_report_plan:
        step_counter += 1
        emit_status(
            f"Synthesizing Section {step_counter}/{len(updated_report_plan)}: {section_name}..."
        )
        logger.info(f"--- Starting Section Synthesis: {section_name} (SID: {sid}) ---")
        try:
            # Prepare research items with "Source N:" prefix for synthesis
            items_for_synthesis = []
            if section_name in collected_research and collected_research[section_name]:
                for i, item_content in enumerate(collected_research[section_name]):
                    # Prepend "Source N:" to each research item string
                    # The item_content itself should already contain Title, Link, Snippet, Content
                    items_for_synthesis.append(f"Source {i+1}:\n{item_content}")
            else:
                items_for_synthesis.append("[No research material found for this section.]")

            report_section_text, section_refs = synthesize_research_into_report_section(
                section_name,
                section_description,
                items_for_synthesis, # Pass the prefixed items
            )
            report_sections_results[section_name] = report_section_text
            # Store references under the specific key format
            report_references_results[section_name + "_references"] = section_refs
            logger.info(
                f"--- Finished Section Synthesis: {section_name} (Length: {len(report_section_text)}, Refs: {len(section_refs)}) ---"
            )
        except Exception as e:
            logger.error(
                f"Error during synthesis step for section '{section_name}': {e}",
                exc_info=True,
            )
            error_msg = f"## {section_name}\n\n[System Error: Failed during synthesis for section '{section_name}': {type(e).__name__}]\n"
            # Store error message as section text and empty refs
            report_sections_results[section_name] = error_msg
            report_references_results[section_name + "_references"] = []
            # Optionally emit non-fatal warning

    logger.info(
        f"--- Finished Sequential Execution of Section Synthesis (SID: {sid}) ---"
    )
    emit_status("Section synthesis complete. Assembling final report...")

    # --- Cancellation Check ---
    if is_cancelled_callback():
        return emit_cancellation_or_error("[AI Info: Deep research cancelled before final assembly.]", is_cancel=True)

    # Ensure sections are assembled in the order defined by updated_report_plan
    ordered_section_texts = [
        report_sections_results.get(
            name, f"## {name}\n\n[Error: Section not generated.]\n"
        )
        for name, desc in updated_report_plan
    ]
    full_report_body = "\n\n".join(ordered_section_texts)

    # 6. Assemble Final Report Components
    # full_report_body is now assembled above
    executive_summary = create_exec_summary(full_report_body)
    next_steps = create_next_steps(full_report_body)


    # 7. Generate Final Report using LLM for formatting and citation linking
    emit_status("Formatting final report...")
    final_report_output = final_report(
        executive_summary, full_report_body, next_steps, 
    )

    # Check if final formatting failed (returned fallback content)
    if "[Error:" in final_report_output and "Failed to generate" in final_report_output:
        logger.error(
            f"Final report formatting failed for SID {sid}. Using concatenated content."
        )
        # Use the concatenated version as the final content
        final_report_content = f"{executive_summary}\n\n---\n\n{full_report_body}\n\n---\n\n{next_steps}\n\n---".strip()
        emit_status("Final formatting failed, using raw assembly.")
    else:
        final_report_content = (
            final_report_output  # Store the successfully formatted report
        )
        emit_status("Final report formatting complete.")

    # --- Emit Final Result ---
    logger.info(f"--- Deep Research Complete for Query: '{query}' (SID: {sid}) ---")
    socketio.emit("deep_research_result", {"report": final_report_content}, room=sid)

    # --- Save Final Result to DB ---
    if chat_id is not None:
        try:
            logger.info(
                f"Attempting to save final deep research report for chat {chat_id}."
            )
            from . import database as db  # Local import

            db.add_message_to_db(chat_id, "assistant", final_report_content)
        except Exception as db_err:
            logger.error(
                f"Failed to save final deep research report to DB for chat {chat_id}: {db_err}",
                exc_info=True,
            )
        finally: # This finally corresponds to the try block starting after cpu_executor is created
            logger.info(f"Deep research process for SID {sid} concluded within cpu_executor context.")
    # cpu_executor is automatically shut down here by the 'with' statement.
        finally:
            # This finally block is for the `with app.app_context():`
            # The cpu_executor is managed by its own `with` statement if created inside the main try.
            # If cpu_executor was created outside the try/finally of the main research process,
            # it would need shutdown here.
            # However, with the current structure, it's managed by its `with` block.
            logger.info(f"Deep research process for SID {sid} concluded.")
