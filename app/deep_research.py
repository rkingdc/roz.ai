import json
import logging
import re
from typing import List, Tuple, Any, Dict

import tempfile # For potential future use if needed directly here
import os # For potential future use if needed directly here
from flask import current_app # To access config for model names if needed

# Assuming ai_services.py and web_search.py are in the same directory
# or accessible via the Python path.
# Use appropriate import style for your project structure (e.g., relative imports if part of a package)
from .ai_services import generate_text, transcribe_pdf_bytes # Import the new function
from .plugins.web_search import (
    perform_web_search,
    # fetch_web_content is now called internally by perform_web_search
)  # For web searching and scraping


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
                    logger.debug("List of objects parsed, first item has expected keys.")
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
    Generates a research plan (list of steps) from a user query using an LLM.
    Returns a list of tuples [(step_name, step_description), ...].
    """
    logger.info(f"Generating research plan for query: {query}")
    # Placeholder: In a real app, this would call an LLM service
    # For now, return a dummy plan
    dummy_plan = [
        ("Identify Key Concepts", f"Identify the main concepts and keywords in the query: '{query}'."),
        ("Perform Initial Web Search", "Perform a broad web search using the identified keywords."),
        ("Synthesize Findings", "Synthesize the information from the search results into a coherent report."),
        ("Identify Next Steps", "Based on the synthesized information, suggest potential next steps or related areas for further research."),
        ("Compile Works Cited", "List the sources used in the research.")
    ]
    logger.info(f"Generated dummy research plan: {dummy_plan}")
    return dummy_plan

# --- Query Generation for Research Steps ---

# This function would call an LLM to generate specific search queries
# for a given research step description.
def determine_research_queries(
    step_description: str, num_queries: int = 3
) -> List[str]:
    """
    Determines specific search queries for a research step using an LLM.
    Returns a list of query strings.
    """
    logger.info(f"Determining {num_queries} research queries for step: {step_description}")
    # Placeholder: In a real app, this would call an LLM service
    # For now, return dummy queries based on the description
    dummy_queries = [f"{step_description} search query {i+1}" for i in range(num_queries)]
    logger.info(f"Generated dummy queries: {dummy_queries}")
    return dummy_queries

# --- Web Search Execution (Calls the plugin) ---

def web_search(search_query: str, num_results: int = 3) -> Tuple[List[str], List[Dict]]:
    """
    Performs a web search using the plugin and processes the results.
    Returns a tuple:
    - A list of strings suitable for further processing (e.g., by an LLM),
      including notes for non-text content like PDFs.
    - A list of the raw result dictionaries from perform_web_search,
      useful for generating the works cited section.
    """
    logger.info(f"Performing web search for query: {search_query} (requesting {num_results} results)")
    raw_results_dicts = []
    processed_content_list = []

    try:
        # perform_web_search now returns List[Dict]
        raw_results_dicts = perform_web_search(search_query, num_results)

        if not raw_results_dicts:
             logger.info("Web search returned no results.")
             # Check if it's the old system error string format (shouldn't happen with updated plugin, but defensive)
             if len(raw_results_dicts) == 1 and isinstance(raw_results_dicts[0], str) and raw_results_dicts[0].startswith("[System Error"):
                 # If it's the old error format, return it as the processed content and an empty dict list
                 return raw_results_dicts, []
             return [], [] # Return empty lists if no results

        for i, result_item in enumerate(raw_results_dicts):
            # Ensure the item is a dictionary as expected from the new perform_web_search
            if not isinstance(result_item, dict):
                logger.warning(f"Unexpected item type in search results: {type(result_item)}. Skipping.")
                processed_content_list.append(f"[System Note: Skipped unexpected search result format for item {i+1}]")
                continue

            title = result_item.get('title', 'No Title')
            link = result_item.get('link', 'No Link')
            snippet = result_item.get('snippet', 'No Snippet Available') # Include snippet
            fetch_result = result_item.get('fetch_result', {})
            result_type = fetch_result.get('type', 'error')
            result_content = fetch_result.get('content') # Can be text (html), bytes (pdf), or string (error)
            fetched_filename = fetch_result.get('filename') # For PDFs

            # Add a header for each result for clarity in the combined text
            # Include title, link, and snippet
            header = f"\n--- Search Result {i+1}: {title} ---\nLink: {link}\nSnippet: {snippet}\n"

            if result_type == 'html' and isinstance(result_content, str) and result_content.strip():
                # Append header + HTML text content
                processed_content_list.append(header + "Content:\n" + result_content.strip())
                logger.debug(f"Added HTML content for result {i+1}")
            elif result_type == 'pdf' and isinstance(result_content, bytes):
                pdf_bytes = result_content
                pdf_filename = fetched_filename if fetched_filename else f"search_result_{i+1}.pdf"
                logger.info(f"Attempting to transcribe PDF: {pdf_filename}")
                # Call the new transcription function from ai_services
                transcription_result = transcribe_pdf_bytes(pdf_bytes, pdf_filename)

                # Check if transcription was successful or returned an error string
                if transcription_result.startswith(("[Error", "[System Note", "[AI Error")):
                    logger.warning(f"PDF transcription failed for {pdf_filename}: {transcription_result}")
                    # Append header + error/note about transcription failure
                    processed_content_list.append(header + f"Content: [Transcription Failed for PDF '{pdf_filename}': {transcription_result}]\n---")
                else:
                    logger.info(f"Successfully transcribed PDF: {pdf_filename}")
                    # Append header + transcribed text
                    processed_content_list.append(header + f"Content (Transcribed from PDF '{pdf_filename}'):\n{transcription_result.strip()}\n---")

            elif result_type == 'error':
                 error_msg = result_content if isinstance(result_content, str) else 'Unknown error'
                 note = f"[Error fetching content for this source: {error_msg}]\n---" # Added separator
                 processed_content_list.append(header + note) # Note already includes separator
                 logger.warning(f"Error fetching content for result {i+1}: {error_msg}")
            else:
                # Handle cases like empty content for HTML, or unexpected types/content
                note = f"[Could not process content for this source (Type: {result_type}).]\n---" # Added separator
                processed_content_list.append(header + note)
                logger.warning(f"Could not process content for result {i+1} (Type: {result_type}, Content type: {type(result_content)}).")


        # Return both the processed list of strings and the original list of dictionaries
        return processed_content_list, raw_results_dicts

    except Exception as e:
        logger.error(f"An unexpected error occurred during web search in deep_research: {e}", exc_info=True)
        # Return a list containing a single error string and an empty dict list
        return [f"[System Error: An unexpected error occurred during web search: {type(e).__name__}]"], []


# --- Research Plan Update ---

# This function would call an LLM to update the research plan
# based on the initial search results.
def query_and_research_to_updated_plan(
    query: str, collected_research: Dict[str, List[Dict]] # Expects Dict[step_name, List[Dict]]
) -> List[Tuple[str, str]]:
    """
    Updates the research plan based on the initial query and collected research.
    Returns a list of tuples [(step_name, step_description), ...].
    """
    logger.info(f"Updating research plan based on query and collected research.")
    # Placeholder: In a real app, this would call an LLM service
    # For now, return a slightly modified dummy plan
    dummy_plan = [
        ("Review Initial Findings", "Review the collected research results."),
        ("Identify Gaps or New Questions", "Based on the review, identify any gaps in information or new questions that arose."),
        ("Perform Targeted Searches (if needed)", "If gaps exist, determine specific queries for targeted web searches."),
        ("Synthesize Comprehensive Report", "Synthesize all collected information into a comprehensive report."),
        ("Identify Next Steps", "Based on the synthesized information, suggest potential next steps or related areas for further research."),
        ("Compile Works Cited", "List the sources used in the research.")
    ]
    logger.info(f"Generated dummy updated research plan: {dummy_plan}")
    return dummy_plan

# --- Report Synthesis ---

# These functions would call an LLM to synthesize research into report sections.

def synthesize_research_into_report_section(
    section_name: str, section_description: str, collected_research_for_step: List[str] # Expects List[str]
) -> str:
    """
    Synthesizes collected research for a specific step into a report section using an LLM.
    Returns the text content of the report section.
    """
    logger.info(f"Synthesizing report section: {section_name}")
    # Placeholder: In a real app, this would call an LLM service
    # For now, return a dummy synthesis
    research_text = "\n\n".join(collected_research_for_step)
    dummy_synthesis = f"## {section_name}\n\nThis section addresses the research step: '{section_description}'.\n\nBased on the collected information:\n\n{research_text}\n\n[Synthesis Placeholder: A real LLM would synthesize this.]"
    logger.info(f"Generated dummy synthesis for section: {section_name}")
    return dummy_synthesis

def create_exec_summary(report_content: str) -> str:
    """
    Creates an executive summary for the full report using an LLM.
    Returns the executive summary text.
    """
    logger.info("Creating executive summary.")
    # Placeholder: In a real app, this would call an LLM service
    dummy_summary = f"## Executive Summary\n\n[Summary Placeholder: A real LLM would summarize the following report content:]\n\n{report_content[:500]}..."
    logger.info("Generated dummy executive summary.")
    return dummy_summary

def create_next_steps(report_content: str) -> str:
    """
    Creates next steps based on the report content using an LLM.
    Returns the next steps text.
    """
    logger.info("Creating next steps.")
    # Placeholder: In a real app, this would call an LLM service
    dummy_next_steps = f"## Next Steps\n\n[Next Steps Placeholder: A real LLM would suggest steps based on the report.]\n\nPossible next steps could include further research, analysis, or action based on the findings."
    logger.info("Generated dummy next steps.")
    return dummy_next_steps

def create_works_cited(
    # report_references: Dict[str, List[str]], # This parameter seems unused in the current logic
    collected_research: Dict[str, List[Dict]] # Expects Dict[step_name, List[Dict]]
) -> str:
    """
    Creates a works cited section based on the collected research sources.
    This function processes the structured research data (list of dictionaries).
    Returns the works cited text.
    """
    logger.info("Creating works cited section.")
    works_cited_list = []
    source_counter = 1
    # collected_research is Dict[step_name, List[Dict]] where inner list items are the result_data dicts from perform_web_search
    for step_name, results_list in collected_research.items():
        if results_list:
            works_cited_list.append(f"### Sources for '{step_name}'")
            for result_item in results_list:
                 if isinstance(result_item, dict):
                    title = result_item.get('title', 'No Title')
                    link = result_item.get('link', 'No Link')
                    fetch_result = result_item.get('fetch_result', {})
                    result_type = fetch_result.get('type', 'unknown')
                    fetched_filename = fetch_result.get('filename') # For PDFs

                    source_entry = f"[{source_counter}] [{title}]({link})"
                    if result_type == 'pdf':
                        filename_note = f" ({fetched_filename})" if fetched_filename else ""
                        source_entry += f" - [Attached PDF Document{filename_note}]"
                    elif result_type == 'html':
                         # Optionally include a snippet or note for HTML
                         snippet = result_item.get('snippet', 'No Snippet Available')
                         source_entry += f" - \"{snippet[:100]}...\"" # Add snippet preview
                    else:
                         error_msg = fetch_result.get('content', 'Unknown error')
                         source_entry += f" - [Error fetching content: {error_msg}]"

                    works_cited_list.append(source_entry)
                    source_counter += 1
                 else:
                     # Handle unexpected items in the list (e.g., old error strings)
                     works_cited_list.append(f"[{source_counter}] [Unexpected Source Format] - {result_item}")
                     source_counter += 1


    if not works_cited_list:
        return "## Works Cited\n\nNo sources cited."

    return "## Works Cited\n\n" + "\n".join(works_cited_list)


def final_report(
    executive_summary: str, report_body: str, next_steps: str, works_cited: str
) -> str:
    """
    Combines all report sections into a final document.
    Returns the full report text.
    """
    logger.info("Compiling final report.")
    # Simple concatenation for now
    full_report = f"{executive_summary}\n\n{report_body}\n\n{next_steps}\n\n{works_cited}"
    logger.info("Final report compiled.")
    return full_report

# --- Main Deep Research Orchestration (Example) ---

# This function would orchestrate the entire deep research process.
# It's not called directly by the current Flask app structure, but
# serves as an example of how the above functions would be used together.
def perform_deep_research(query: str) -> str:
    """
    Orchestrates the deep research process based on a user query.
    Generates a plan, performs searches, synthesizes a report.
    Returns the final report as a string.
    """
    logger.info(f"Starting deep research for query: '{query}'")

    # 1. Generate Initial Research Plan
    research_plan = query_to_research_plan(query)
    if not research_plan:
        return "[Error: Could not generate a research plan.]"

    # Store raw search result dicts per *initial* step name for works cited
    collected_research_raw_dicts: Dict[str, List[Dict]] = {}

    # 2. Execute Research Steps (Simplified loop)
    report_sections = {}
    for step_name, step_description in research_plan:
        logger.info(f"Executing research step: {step_name} - {step_description}")

        # Determine search queries for the step
        search_queries = determine_research_queries(step_description)
        if not search_queries:
            logger.warning(f"No search queries generated for step: {step_name}")
            report_sections[step_name] = f"## {step_name}\n\n[No search queries generated for this step.]"
            collected_research_raw_dicts[step_name] = [] # Store empty list
            continue

        # Perform web searches for each query
        step_content_for_synthesis = [] # Content formatted for synthesis LLM
        step_raw_results_dicts = [] # Raw dicts for this step

        for search_query in search_queries:
            # Call the modified web_search which returns both processed content and raw dicts
            query_processed_content_list, query_raw_results_dicts = web_search(search_query)

            step_content_for_synthesis.extend(query_processed_content_list)
            step_raw_results_dicts.extend(query_raw_results_dicts)

        # Store the raw dicts for this step
        collected_research_raw_dicts[step_name] = step_raw_results_dicts

        if step_content_for_synthesis and not (len(step_content_for_synthesis) == 1 and step_content_for_synthesis[0].startswith("[System Error")):
            # Synthesize findings for this step
            section_content = synthesize_research_into_report_section(
                step_name, step_description, step_content_for_synthesis
            )
            report_sections[step_name] = section_content
        else:
            logger.warning(f"No usable content collected or system error for step: {step_name}")
            # Check if it was a system error from web_search
            if step_content_for_synthesis and step_content_for_synthesis[0].startswith("[System Error"):
                 report_sections[step_name] = f"## {step_name}\n\n{step_content_for_synthesis[0]}"
            else:
                 report_sections[step_name] = f"## {step_name}\n\n[No usable research content found for this step.]"


    # 3. Compile Report Body
    report_body = "\n\n".join(report_sections.values())

    # 4. Create Executive Summary
    executive_summary = create_exec_summary(report_body)

    # 5. Create Next Steps
    next_steps = create_next_steps(report_body)

    # 6. Compile Works Cited
    # Pass the collected_research_raw_dicts to create_works_cited
    works_cited = create_works_cited(collected_research_raw_dicts)

    # 7. Final Report Assembly
    final_report_text = final_report(
        executive_summary, report_body, next_steps, works_cited
    )

    logger.info("Deep research process completed.")
    return final_report_text

# Example usage (not part of the Flask app flow):
# if __name__ == '__main__':
#     research_query = "latest advancements in AI safety"
#     report = perform_deep_research(research_query)
#     print(report)
