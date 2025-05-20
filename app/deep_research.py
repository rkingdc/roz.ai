import json
import logging
import re
from typing import List, Tuple, Any, Dict, Callable # Import Callable

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
            else:
                logger.debug(
                    "Parsed JSON is a list, but not a list of objects, or list is empty."
                )
                return parsed_output  # Return the list as is
        else:
            logger.debug(
                "Parsed JSON is not a dict or list of dicts, or no expected keys specified."
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


def determine_research_queries(
    step_description: str, num_queries: int = 3
) -> List[str]:
    """
    Takes a research step description and uses an LLM to generate relevant search queries.
    Expects the LLM to return a JSON list of query strings.
    """
    logger.info(f"Generating search queries for step: '{step_description[:50]}...'")
    prompt = f"""
    Based on the research step description below, generate {num_queries} distinct and effective Google search queries to find relevant information.
    Focus on keywords and specific phrases that would yield high-quality results.
    Return the queries as a JSON list of strings.

    Example Format:
    ```json
    [
      "definition of [core concept]",
      "history of [topic]",
      "key figures in [field]"
    ]
    ```

    Research Step Description: "{step_description}"

    Search Queries (JSON):
    """
    try:
        llm_response = generate_text(prompt)
        if (
            not llm_response
            or llm_response.startswith("[Error")
            or llm_response.startswith("[System Note")
        ):
            logger.error(f"LLM failed to generate search queries: {llm_response}")
            return []

        parsed_queries = parse_llm_json_output(
            llm_response, expected_keys=[]
        )  # No specific keys for outer list

        if isinstance(parsed_queries, list) and all(
            isinstance(q, str) for q in parsed_queries
        ):
            logger.info(f"Successfully generated {len(parsed_queries)} search queries.")
            return parsed_queries
        else:
            logger.error(
                f"LLM response for search queries was not in the expected format: {llm_response}"
            )
            # Fallback: Split by newline?
            # queries = [q.strip() for q in llm_response.strip().split('\n') if q.strip()]
            # if queries: return queries
            return []

    except Exception as e:
        logger.error(f"Error in determine_research_queries: {e}", exc_info=True)
        return []


# --- Web Search Execution (Calls the plugin) ---


def web_search(search_query: str, num_results: int = 10) -> Tuple[List[str], List[Dict]]:
    """
    Performs a web search using the LLM's tool-calling ability and processes the results.
    Returns a tuple:
    - A list of strings suitable for further processing (e.g., by an LLM),
      including notes for non-text content like PDFs.
    - A list of the raw result dictionaries from the underlying search tool function,
      useful for generating the works cited section.
    """
    logger.info(
        f"Performing web search via LLM for query: {search_query} (requesting {num_results} results)"
    )
    raw_results_dicts = []
    processed_content_list = []

    try:
        # --- Client Acquisition ---
        api_key = current_app.config.get("API_KEY")
        if not api_key:
            logger.error("API_KEY is missing from current_app.config for web_search.")
            return ("[System Error: AI Service API Key not configured]", [])

        if "genai_client" not in g:
            logger.info("web_search: Creating new genai.Client and caching in 'g'.")
            try:
                g.genai_client = genai.Client(api_key=api_key)
            except Exception as e:
                logger.error(f"web_search: Failed to initialize genai.Client: {e}", exc_info=True)
                if "api key not valid" in str(e).lower():
                    return ("[Error: Invalid Gemini API Key for web_search]", [])
                return ("[Error: Failed to initialize AI client for web_search]", [])
        
        gemini_client = g.genai_client
        if not gemini_client: # Should ideally not be reached if above logic is correct
            logger.error("LLM client (g.genai_client) is unexpectedly None after init attempt in web_search.")
            return ("[System Error: LLM client not available after init attempt]", [])
        # --- End Client Acquisition ---

        prompt_text = (
            f"Please search the web for information on: '{search_query}'. "
            f"Provide up to {num_results} relevant results."
        )

        # Make LLM call to trigger the web_search tool
        # Determine the model to use, similar to generate_text
        raw_model_name = current_app.config.get("DEFAULT_MODEL", "gemini-2.5-flash-preview-04-17") # Fallback if not in config
        model_to_use = (
            f"models/{raw_model_name}"
            if not raw_model_name.startswith("models/")
            else raw_model_name
        )
        logger.info(f"web_search: Using model '{model_to_use}' for tool call.")

        generation_config = types.GenerateContentConfig(
            tools=[WEB_SEARCH_TOOL]
            # Add other generation parameters here if needed, e.g., temperature, max_output_tokens
        )
        
        response = gemini_client.models.generate_content(
            model=model_to_use,
            contents=prompt_text,
            config=generation_config
        )

        if not response.candidates or not response.candidates[0].content.parts:
            logger.warning("LLM did not return parts for web_search tool call.")
            return ("[System Note: LLM did not initiate web search tool.]", [])

        part = response.candidates[0].content.parts[0]
        if not part.function_call or part.function_call.name != "web_search":
            logger.warning(
                f"LLM did not call 'web_search' tool as expected. Called: {part.function_call.name if part.function_call else 'None'}"
            )
            if part.text:
                 return ([f"[System Note: LLM provided text instead of using web_search tool: {part.text}]", []])
            return ("[System Note: LLM did not use the web_search tool correctly.]", [])

        # Execute the function call
        fc = part.function_call
        tool_args = dict(fc.args)
        
        # Use query from tool call, fallback to original if not provided by LLM (though tool schema requires it)
        query_for_tool = tool_args.get("query", search_query)
        # Use num_results from tool call, fallback to function's parameter if not specified by LLM
        num_results_for_tool = tool_args.get("num_results", num_results)


        # Call the actual Python function associated with the "web_search" tool
        # This function (app.plugins.web_search.perform_web_search) returns List[Dict]
        # where each dict contains 'title', 'link', 'snippet', and 'fetch_result'.
        actual_search_results = web_search_plugin.perform_web_search(
            query=query_for_tool, num_results=num_results_for_tool
        )
        
        raw_results_dicts.extend(actual_search_results)

        if not raw_results_dicts:
            logger.info("Web search tool returned no results.")
            return [], []

        for i, result_item in enumerate(raw_results_dicts):
            # Ensure the item is a dictionary
            if not isinstance(result_item, dict):
                logger.warning(
                    f"Unexpected item type in search results: {type(result_item)}. Skipping."
                )
                processed_content_list.append(
                    f"[System Note: Skipped unexpected search result format for item {i+1}]"
                )
                continue

            title = result_item.get("title", "No Title")
            link = result_item.get("link", "No Link")
            snippet = result_item.get("snippet", "No Snippet Available")

            # Create a formatted string with the search result metadata.
            # Actual content fetching is deferred to the WEB_SCRAPE_TOOL.
            result_summary = (
                f"Source {i+1}:\n"
                f"Title: {title}\n"
                f"Link: {link}\n"
                f"Snippet: {snippet}\n---"
            )
            processed_content_list.append(result_summary)
            logger.debug(f"Added search result summary for item {i+1}: {title}")

        # Return the list of summaries and the original list of dictionaries
        return processed_content_list, raw_results_dicts

    except Exception as e:
        logger.error(
            f"An unexpected error occurred during web search (tool-based) in deep_research: {e}",
            exc_info=True,
        )
        # Return a list containing a single error string and an empty dict list
        return [
            f"[System Error: An unexpected error occurred during web search: {type(e).__name__}]"
        ], []


# --- Helper for Scraping and Processing URL ---
def _scrape_and_process_url(
    search_result_meta: Dict, # Contains title, link, snippet
    source_index: int, # For "Source N"
    is_cancelled_callback: Callable[[], bool],
    socketio, # For emit_status
    sid,
    app_context # Pass Flask app context for background thread safety
) -> str:
    """
    Uses WEB_SCRAPE_TOOL to fetch content from a URL, transcribes if PDF,
    and returns a formatted string with all information.
    Must be called within an active Flask app context.
    """
    link_to_scrape = search_result_meta.get("link")
    title = search_result_meta.get("title", "No Title")
    original_snippet = search_result_meta.get("snippet", "No Snippet")
    source_identifier = f"Source {source_index + 1}" # 0-indexed to 1-indexed

    base_info = f"{source_identifier}: {title}\nLink: {link_to_scrape}\nSnippet: {original_snippet}\n"

    if not link_to_scrape or link_to_scrape == "no link" or not link_to_scrape.startswith(('http://', 'https://')):
        logger.warning(f"Skipping scrape for '{title}' due to missing or invalid link: {link_to_scrape}")
        return base_info + "Content: [Could not scrape, link missing or invalid]\n---"

    if is_cancelled_callback():
        logger.info(f"Scraping cancelled by user for {link_to_scrape}")
        return base_info + "Content: [Scraping cancelled by user]\n---"

    if socketio and sid:
        socketio.emit("status_update", {"message": f"Scraping: {title[:30]}..."}, room=sid)

    # Ensure we are in app context for config and g
    with app_context:
        try:
            if "genai_client" not in g:
                logger.error("genai_client not in g for _scrape_and_process_url. Initializing.")
                # Attempt to initialize client (basic version, assumes API_KEY is in config)
                api_key = current_app.config.get("API_KEY")
                if not api_key:
                    return base_info + "Content: [Scraping Error: AI Service API Key not configured]\n---"
                g.genai_client = genai.Client(api_key=api_key)
            
            gemini_client = g.genai_client
            
            raw_model_name = current_app.config.get("DEFAULT_MODEL", "gemini-2.5-flash-preview-04-17")
            model_to_use = f"models/{raw_model_name}" if not raw_model_name.startswith("models/") else raw_model_name

            scrape_prompt_text = f"Please scrape the content from the following URL: {link_to_scrape}"
            scrape_generation_config = types.GenerateContentConfig(tools=[WEB_SCRAPE_TOOL])

            scrape_response = gemini_client.models.generate_content(
                model=model_to_use,
                contents=scrape_prompt_text,
                config=scrape_generation_config
            )

            if not scrape_response.candidates or not scrape_response.candidates[0].content.parts:
                logger.warning(f"LLM did not return parts for WEB_SCRAPE_TOOL call for {link_to_scrape}.")
                return base_info + "Content: [Scraping Error: LLM did not initiate scrape tool]\n---"

            scrape_part = scrape_response.candidates[0].content.parts[0]
            if not scrape_part.function_call or scrape_part.function_call.name != "scrape_url":
                logger.warning(f"LLM did not call 'scrape_url' tool as expected for {link_to_scrape}. Called: {scrape_part.function_call.name if scrape_part.function_call else 'None'}")
                return base_info + "Content: [Scraping Error: LLM did not use scrape tool correctly]\n---"

            fc_scrape = scrape_part.function_call
            tool_args_scrape = dict(fc_scrape.args)
            url_from_tool = tool_args_scrape.get("url")

            if not url_from_tool:
                logger.error(f"LLM tool call for 'scrape_url' missing 'url' argument for {link_to_scrape}.")
                return base_info + "Content: [Scraping Error: LLM tool call missing URL]\n---"

            # Execute the actual scrape function (fetch_web_content from web_search_plugin)
            scraped_data_dict = web_search_plugin.fetch_web_content(url=url_from_tool)

            actual_content_str = ""
            if scraped_data_dict['type'] == 'html':
                actual_content_str = scraped_data_dict['content']
                if not actual_content_str or not actual_content_str.strip():
                    actual_content_str = "[No textual content extracted from HTML]"
            elif scraped_data_dict['type'] == 'pdf':
                pdf_bytes = scraped_data_dict['content']
                pdf_filename = scraped_data_dict.get('filename', 'document.pdf')
                if socketio and sid:
                    socketio.emit("status_update", {"message": f"Transcribing PDF: {pdf_filename[:30]}..."}, room=sid)
                # transcribe_pdf_bytes is imported from .ai_services
                actual_content_str = transcribe_pdf_bytes(pdf_bytes, pdf_filename)
                if actual_content_str.startswith(("[Error", "[System Note")):
                    logger.warning(f"PDF transcription failed for {pdf_filename}: {actual_content_str}")
            elif scraped_data_dict['type'] == 'error':
                actual_content_str = f"[Scraping Error on URL {url_from_tool}: {scraped_data_dict['content']}]"
                logger.warning(actual_content_str)
            else:
                actual_content_str = f"[Scraping Error: Unknown content type '{scraped_data_dict['type']}' from URL {url_from_tool}]"
                logger.warning(actual_content_str)
            
            return base_info + f"Content:\n{actual_content_str.strip()}\n---"

        except Exception as e_scrape:
            logger.error(f"Error during scraping/processing of {link_to_scrape}: {e_scrape}", exc_info=True)
            return base_info + f"Content: [Scraping/Processing Exception: {type(e_scrape).__name__}]\n---"


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
    with app.app_context():
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
    )  # Stores processed content strings per *initial* step name
    collected_raw_results: Dict[str, List[Dict]] = (
        {}
    )  # Stores raw result dicts per *initial* step name

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
        logger.debug(f"Description: {step_description}")
        all_processed_content_for_step = []
        all_raw_dicts_for_step = []
        try:
            # a. Determine Search Queries
            search_queries: List[str] = determine_research_queries(step_description) # Needs app context, no cancellation check
            if not search_queries:
                logger.warning(f"No search queries generated for step: {step_name}")
                collected_research[step_name] = []
                collected_raw_results[step_name] = []
                continue  # Move to the next step

            # b. Perform Web Search for each query to get metadata
            current_step_raw_meta_results = [] # Store metadata from all queries for this step
            for search_query_idx, search_query in enumerate(search_queries):
                # --- Cancellation Check (before each web search) ---
                if is_cancelled_callback():
                    return emit_cancellation_or_error(f"[AI Info: Deep research cancelled during step '{step_name}' before web search for '{search_query}'.]", is_cancel=True)
                
                emit_status(f"Searching: {search_query[:40]}... (Query {search_query_idx+1}/{len(search_queries)})")
                # web_search returns summaries (which we ignore here) and raw metadata dicts
                _, raw_meta_dicts_for_query = web_search(search_query) 

                if raw_meta_dicts_for_query:
                    current_step_raw_meta_results.extend(raw_meta_dicts_for_query)
                else:
                    logger.debug(f"No search results from web_search for query '{search_query}' in step '{step_name}'")
            
            # c. Scrape content for each unique link found in the step's search results
            # Use a set to avoid scraping the same link multiple times if returned by different queries
            unique_links_to_scrape_meta = {item['link']: item for item in current_step_raw_meta_results if item.get('link')}.values()
            
            scraped_content_count_for_step = 0
            for meta_item_idx, meta_item in enumerate(unique_links_to_scrape_meta):
                 # --- Cancellation Check (before each scrape) ---
                if is_cancelled_callback():
                    return emit_cancellation_or_error(f"[AI Info: Deep research cancelled during step '{step_name}' before scraping '{meta_item.get('link')}'.]", is_cancel=True)

                # The source_index for _scrape_and_process_url should be relative to the items being processed for this step
                full_content_string = _scrape_and_process_url(
                    meta_item,
                    source_index=scraped_content_count_for_step, # Index for "Source N"
                    is_cancelled_callback=is_cancelled_callback,
                    socketio=socketio,
                    sid=sid,
                    app_context=app.app_context() # Pass the app context
                )
                if full_content_string:
                    all_processed_content_for_step.append(full_content_string)
                    scraped_content_count_for_step +=1

            collected_research[step_name] = all_processed_content_for_step
            # collected_raw_results stores the initial search metadata (title, link, snippet)
            # This can be useful for a "Works Cited" that lists initial hits, distinct from full scraped content.
            collected_raw_results[step_name] = list(unique_links_to_scrape_meta) # Store the unique metadata items
            logger.info(
                f"--- Finished Research Step: {step_name} - Collected {len(all_processed_content_for_step)} scraped/processed items from {len(unique_links_to_scrape_meta)} unique links ---"
            )

        except Exception as e:
            logger.error(
                f"Error executing research step '{step_name}' (SID: {sid}): {e}",
                exc_info=True,
            )
            # Log error but continue to next step if possible
            error_msg = f"[System Error: Failed during research step '{step_name}': {type(e).__name__}]"
            collected_research[step_name] = [error_msg]
            collected_raw_results[step_name] = [{"error": error_msg}]

    logger.info(
        f"--- Finished Sequential Execution of Initial Research Steps (SID: {sid}) ---"
    )
    emit_status("Initial research complete. Refining report plan...")

    # --- Cancellation Check ---
    if is_cancelled_callback():
        return emit_cancellation_or_error("[AI Info: Deep research cancelled before refining plan.]", is_cancel=True)

    # Log collected research summary
    for step, items in collected_research.items():
        raw_count = len(collected_raw_results.get(step, []))
        logger.debug(
            f"Step '{step}': Collected {len(items)} processed items, {raw_count} raw items."
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
            if section_name not in collected_raw_results:
                collected_raw_results[section_name] = []
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
            processed_content_for_section = []
            raw_dicts_for_section = []
            try:
                # a. Determine Search Queries for the new section
                search_queries: List[str] = determine_research_queries(
                    section_description
                )
                if not search_queries:
                    logger.warning(
                        f"No search queries generated for new section: {section_name}"
                    )
                    # collected_research/raw_results already initialized, just continue
                    continue

                # b. Perform Web Search for each query to get metadata
                current_section_raw_meta_results = []
                for search_query_idx, search_query in enumerate(search_queries):
                    # --- Cancellation Check (before each web search) ---
                    if is_cancelled_callback():
                        return emit_cancellation_or_error(f"[AI Info: Deep research cancelled during additional research for '{section_name}' before web search for '{search_query}'.]", is_cancel=True)

                    emit_status(f"Add. Search: {search_query[:30]}... (Query {search_query_idx+1}/{len(search_queries)})")
                    _, raw_meta_dicts_for_query = web_search(search_query)

                    if raw_meta_dicts_for_query:
                        current_section_raw_meta_results.extend(raw_meta_dicts_for_query)
                    else:
                        logger.debug(f"No search results from web_search for query '{search_query}' in new section '{section_name}'")

                # c. Scrape content for each unique link found
                unique_links_to_scrape_meta_new_section = {item['link']: item for item in current_section_raw_meta_results if item.get('link')}.values()
                
                scraped_content_count_for_new_section = 0
                for meta_item_idx, meta_item in enumerate(unique_links_to_scrape_meta_new_section):
                    # --- Cancellation Check (before each scrape) ---
                    if is_cancelled_callback():
                        return emit_cancellation_or_error(f"[AI Info: Deep research cancelled during additional research for '{section_name}' before scraping '{meta_item.get('link')}'.]", is_cancel=True)
                    
                    full_content_string = _scrape_and_process_url(
                        meta_item,
                        source_index=scraped_content_count_for_new_section, # Index for "Source N"
                        is_cancelled_callback=is_cancelled_callback,
                        socketio=socketio,
                        sid=sid,
                        app_context=app.app_context() # Pass the app context
                    )
                    if full_content_string:
                        # Ensure collected_research[section_name] is a list
                        if section_name not in collected_research or not isinstance(collected_research[section_name], list):
                            collected_research[section_name] = []
                        collected_research[section_name].append(full_content_string)
                        scraped_content_count_for_new_section +=1
                
                # Store the unique metadata items for this new section as well
                if section_name not in collected_raw_results or not isinstance(collected_raw_results[section_name], list):
                    collected_raw_results[section_name] = []
                collected_raw_results[section_name].extend(list(unique_links_to_scrape_meta_new_section))

                logger.info(
                    f"--- Finished Additional Research Step: {section_name} - Collected {scraped_content_count_for_new_section} scraped/processed items from {len(unique_links_to_scrape_meta_new_section)} unique links ---"
                )

            except Exception as e:
                logger.error(
                    f"Error during additional research step for section '{section_name}': {e}",
                    exc_info=True,
                )
                # Log error but continue if possible

        logger.info(
            f"--- Finished sequential execution of additional research for {len(new_sections_to_research)} section(s) (SID: {sid}) ---"
        )
        emit_status("Additional research complete.")
    else:
        logger.info(
            f"--- No new sections required additional research (SID: {sid}) ---"
        )
        emit_status("No additional research needed.")

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
            # Call the synthesis function directly
            report_section_text, section_refs = synthesize_research_into_report_section(
                section_name,
                section_description,
                collected_research[section_name],
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
