import json
import logging
import re
from typing import List, Tuple, Any, Dict
from concurrent.futures import (
    ThreadPoolExecutor,
    as_completed,
) 
import tempfile  # For potential future use if needed directly here
import os  # For potential future use if needed directly here
from flask import current_app  # To access config for model names if needed

# Assuming ai_services.py and web_search.py are in the same directory
# or accessible via the Python path.
# Use appropriate import style for your project structure (e.g., relative imports if part of a package)
from .ai_services import generate_text, transcribe_pdf_bytes  # Import the new function
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


def web_search(search_query: str, num_results: int = 3) -> Tuple[List[str], List[Dict]]:
    """
    Performs a web search using the plugin and processes the results.
    Returns a tuple:
    - A list of strings suitable for further processing (e.g., by an LLM),
      including notes for non-text content like PDFs.
    - A list of the raw result dictionaries from perform_web_search,
      useful for generating the works cited section.
    """
    logger.info(
        f"Performing web search for query: {search_query} (requesting {num_results} results)"
    )
    raw_results_dicts = []
    processed_content_list = []

    try:
        # perform_web_search now returns List[Dict]
        raw_results_dicts = perform_web_search(search_query, num_results)

        if not raw_results_dicts:
            logger.info("Web search returned no results.")
            # Check if it's the old system error string format (shouldn't happen with updated plugin, but defensive)
            if (
                len(raw_results_dicts) == 1
                and isinstance(raw_results_dicts[0], str)
                and raw_results_dicts[0].startswith("[System Error")
            ):
                # If it's the old error format, return it as the processed content and an empty dict list
                return raw_results_dicts, []
            return [], []  # Return empty lists if no results

        for i, result_item in enumerate(raw_results_dicts):
            # Ensure the item is a dictionary as expected from the new perform_web_search
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
            snippet = result_item.get(
                "snippet", "No Snippet Available"
            )  # Include snippet
            fetch_result = result_item.get("fetch_result", {})
            result_type = fetch_result.get("type", "error")
            result_content = fetch_result.get(
                "content"
            )  # Can be text (html), bytes (pdf), or string (error)
            fetched_filename = fetch_result.get("filename")  # For PDFs

            # Add a header for each result for clarity in the combined text
            # Include title, link, and snippet
            header = f"\n--- Search Result {i+1}: {title} ---\nLink: {link}\nSnippet: {snippet}\n"

            if (
                result_type == "html"
                and isinstance(result_content, str)
                and result_content.strip()
            ):
                # Append header + HTML text content
                processed_content_list.append(
                    header + "Content:\n" + result_content.strip()
                )
                logger.debug(f"Added HTML content for result {i+1}")
            elif result_type == "pdf" and isinstance(result_content, bytes):
                pdf_bytes = result_content
                pdf_filename = (
                    fetched_filename if fetched_filename else f"search_result_{i+1}.pdf"
                )
                logger.info(f"Attempting to transcribe PDF: {pdf_filename}")
                # Call the new transcription function from ai_services
                transcription_result = transcribe_pdf_bytes(pdf_bytes, pdf_filename)

                # Check if transcription was successful or returned an error string
                if transcription_result.startswith(
                    ("[Error", "[System Note", "[AI Error")
                ):
                    logger.warning(
                        f"PDF transcription failed for {pdf_filename}: {transcription_result}"
                    )
                    # Append header + error/note about transcription failure
                    processed_content_list.append(
                        header
                        + f"Content: [Transcription Failed for PDF '{pdf_filename}': {transcription_result}]\n---"
                    )
                else:
                    logger.info(f"Successfully transcribed PDF: {pdf_filename}")
                    # Append header + transcribed text
                    processed_content_list.append(
                        header
                        + f"Content (Transcribed from PDF '{pdf_filename}'):\n{transcription_result.strip()}\n---"
                    )

            elif result_type == "error":
                error_msg = (
                    result_content
                    if isinstance(result_content, str)
                    else "Unknown error"
                )
                note = f"[Error fetching content for this source: {error_msg}]\n---"  # Added separator
                processed_content_list.append(
                    header + note
                )  # Note already includes separator
                logger.warning(f"Error fetching content for result {i+1}: {error_msg}")
            else:
                # Handle cases like empty content for HTML, or unexpected types/content
                note = f"[Could not process content for this source (Type: {result_type}).]\n---"  # Added separator
                processed_content_list.append(header + note)
                logger.warning(
                    f"Could not process content for result {i+1} (Type: {result_type}, Content type: {type(result_content)})."
                )

        # Return both the processed list of strings and the original list of dictionaries
        return processed_content_list, raw_results_dicts

    except Exception as e:
        logger.error(
            f"An unexpected error occurred during web search in deep_research: {e}",
            exc_info=True,
        )
        # Return a list containing a single error string and an empty dict list
        return [
            f"[System Error: An unexpected error occurred during web search: {type(e).__name__}]"
        ], []


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
    section_name: str, section_description: str, all_raw_research_items: List[Dict]
) -> Tuple[str, List[str]]:
    """
    Uses an LLM to synthesize collected research (provided as raw dicts) into a coherent report section.
    Also extracts or generates references used in the section.
    Expects LLM to return JSON: {"report_section": "...", "references": ["ref1", "ref2"]}
    """
    logger.info(f"Synthesizing research for section: '{section_name}'")

    if not collected_research_for_step:
        logger.warning(
            f"No research provided for section '{section_name}'. Returning empty section."
        )
        return (
            f"## {section_name}\n\nNo research data was found for this section.\n",
            [],
        )

    # Format research for the prompt using the raw dictionaries
    # Ensure content extraction handles different types (text, transcription, error notes)
    formatted_research_parts = []
    for i, research_dict in enumerate(all_raw_research_items):
        source_id = f"Source {i+1}"
        link = research_dict.get("link", "No Link Provided")
        title = research_dict.get("title", "No Title")
        snippet = research_dict.get("snippet", "")  # Include snippet if available
        fetch_result = research_dict.get("fetch_result", {})
        content_type = fetch_result.get("type", "unknown")
        content = fetch_result.get("content", "[Content not available]")

        content_str = ""
        if content_type == "html" and isinstance(content, str):
            content_str = content.strip()
        elif content_type == "pdf" and isinstance(content, bytes):
            # This shouldn't happen if web_search transcribed it, but handle defensively
            content_str = f"[Note: PDF content bytes received, transcription expected upstream. Filename: {fetch_result.get('filename', 'N/A')}]"
        elif content_type == "pdf_transcribed" and isinstance(content, str):
            # Assuming web_search adds this type after successful transcription
            content_str = f"Transcribed text from PDF '{fetch_result.get('filename', 'N/A')}':\n{content.strip()}"
        elif content_type == "error" and isinstance(content, str):
            content_str = f"[Error fetching content: {content}]"
        elif isinstance(content, str):  # Fallback for other string content
            content_str = content.strip()
        else:
            content_str = f"[Content not available or unexpected type: {content_type}]"

        formatted_research_parts.append(
            f"{source_id}:\nTitle: {title}\nLink: {link}\nSnippet: {snippet}\nContent:\n{content_str}"
        )

    formatted_research = "\n\n---\n\n".join(formatted_research_parts)

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


def create_works_cited(
    report_references: Dict[str, List[str]], all_raw_research_items: List[Dict]
) -> str:
    """
    Creates a works cited section based on the references collected during synthesis
    and the consolidated list of raw research item dictionaries.
    """
    logger.info("Generating works cited section.")

    cited_items_formatted = []
    source_details_map = {}  # Map "Source N" identifier to its details

    # Build a map from "Source N" to the details needed for citation
    for i, item_dict in enumerate(all_raw_research_items):
        source_id = f"Source {i+1}"
        link = item_dict.get("link")
        title = item_dict.get(
            "title", f"Source {i+1}"
        )  # Use title if available, else placeholder
        # Add filename for PDFs if available
        filename = item_dict.get("fetch_result", {}).get("filename")
        if filename:
            title += f" ({filename})"

        source_details_map[source_id] = {
            "link": link,
            "title": title,
            "original_index": i + 1,  # Store the 1-based index
        }

    # Collect all unique source identifiers ("Source 1", "Source 2", etc.) mentioned across report sections
    unique_cited_source_ids = set()
    for section_name, refs in report_references.items():
        if section_name.endswith(
            "_references"
        ):  # Ensure we only look at reference lists
            unique_cited_source_ids.update(
                refs
            )  # refs contains ["Source 1", "Source 3", ...]

    # Build the formatted works cited list, sorted by original index
    for source_id in sorted(
        list(unique_cited_source_ids),
        # Sort using the original_index stored in the map
        key=lambda sid: source_details_map.get(sid, {}).get(
            "original_index", float("inf")
        ),
    ):
        details = source_details_map.get(source_id)
        if details:
            entry = f"{details['original_index']}. "  # Start with original index number
            entry += (
                f"*{details.get('title', 'Untitled Source')}*"  # Use title from map
            )

            link = details.get("link")
            # Check for valid link before adding
            if link and link != "No Link Provided" and link.startswith("http"):
                entry += f" - Available at: <{link}>"  # Use angle brackets for URL
            else:
                entry += " (Link not available or invalid)"
            cited_items_formatted.append(entry)
        else:
            # Fallback if source_id wasn't found in the map (shouldn't happen ideally)
            cited_items_formatted.append(f"- {source_id} (Details not found)")

    works_cited_content = "# Works Cited\n\n"
    if cited_items_formatted:
        works_cited_content += "\n".join(cited_items_formatted)
    else:
        works_cited_content += (
            "[Note: No specific sources were cited or citation data was missing.]\n"
        )

    # Optional: Ask LLM to format the list nicely (might be overkill)
    # prompt = f"""
    # Please format the following list of cited sources into a clean "Works Cited" section using Markdown.
    # Ensure each item is on a new line, potentially using numbered or bulleted lists.

    # Cited Sources List:
    # {works_cited_content}

    # Formatted Works Cited Section (Markdown):
    # """
    # formatted_list = generate_text(prompt)
    # return formatted_list

    logger.info("Successfully generated works cited section.")
    return works_cited_content


def final_report(
    executive_summary: str, report_body: str, next_steps: str, works_cited: str
) -> str:
    """Uses an LLM to assemble and format the final report from its components."""
    logger.info("Formatting final report using LLM.")

    prompt = f"""
You are tasked with assembling and formatting a final research report from its constituent parts using Markdown.
Ensure the report flows logically, uses appropriate headings (e.g., #, ##), and applies selective bolding for emphasis on key terms or findings.

**Crucially, you must convert simple source references within the report body into proper Markdown links.**
The 'Works Cited' section provided below contains the mapping between source numbers and their details (including URLs if available).
When you encounter a reference like '[Source N]' or similar patterns indicating a citation within the 'Report Body' text, replace it with a Markdown link like '[N](URL)' if a URL exists for that source number in the 'Works Cited' section, or just '[N]' if no URL is available. Use the number from the 'Works Cited' entry (e.g., '1.', '2.') as the link text 'N'.

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

**4. Works Cited (use this to create Markdown links in the body):**
--- START ---
{works_cited}
--- END ---

**Instructions:**
1. Combine these sections into a single, coherent Markdown document.
2. Use appropriate Markdown heading levels (e.g., `# Executive Summary`, `## Section Title`, `# Next Steps / Further Research`, `# Works Cited`).
3. Apply selective **bolding** to highlight important terms, concepts, or conclusions within the text.
4. **Convert references:** Find patterns like '[Source N]' in the 'Report Body' and replace them with Markdown links `[N](URL)` using the corresponding URL from the 'Works Cited' section. If a source number in 'Works Cited' does not have a URL, use `[N]`. Match the number 'N' to the number at the start of the entry in 'Works Cited'.
5. Ensure the final 'Works Cited' section is included at the end, formatted clearly (e.g., as a numbered list).
6. Do not add any commentary outside the report content itself.

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
            return f"{executive_summary}\n\n---\n\n{report_body}\n\n---\n\n{next_steps}\n\n---\n\n{works_cited}".strip()
    except Exception as e:
        logger.error(f"Error during final report formatting: {e}", exc_info=True)
        # Fallback to basic concatenation on exception
        return f"{executive_summary}\n\n---\n\n{report_body}\n\n---\n\n{next_steps}\n\n---\n\n{works_cited}".strip()


# --- Helper for Parallel Execution ---
def _execute_research_step(
    step_name: str, step_description: str
) -> Tuple[str, List[str], List[Dict]]:
    """
    Executes a single research step: determines queries and performs web search.
    Designed to be run in parallel using ThreadPoolExecutor (shares app context).
    Returns the step name, list of processed content strings, and list of raw result dictionaries.
    """
    logger.info(f"--- Starting Research Step (Thread): {step_name} ---")
    logger.debug(f"Description: {step_description}")
    all_processed_content_for_step = []
    all_raw_dicts_for_step = []
    try:
        # Explicitly create an app context for the thread
        with current_app.app_context():
            # a. Determine Search Queries
            # Now generate_text (called by determine_research_queries) will have app context
            search_queries: List[str] = determine_research_queries(step_description)
            if not search_queries:
                logger.warning(f"No search queries generated for step: {step_name}")
                # Still return outside the context block
                return step_name, [], []

            # b. Perform Web Search & Scrape Results for each query
            for search_query in search_queries:
                # web_search calls transcribe_pdf_bytes which calls generate_text,
                # so it also needs the app context.
                processed_content, raw_dicts = web_search(search_query)
                if processed_content:
                    all_processed_content_for_step.extend(processed_content)
                if raw_dicts:
                    all_raw_dicts_for_step.extend(raw_dicts)

                if not processed_content and not raw_dicts:
                    logger.debug(
                        f"No results from web_search for query '{search_query}' in step '{step_name}'"
                    )

            logger.info(
                f"--- Finished Research Step (Thread): {step_name} - Collected {len(all_processed_content_for_step)} processed items, {len(all_raw_dicts_for_step)} raw items ---"
            )
            # Return results outside the context block but before the except block
            return step_name, all_processed_content_for_step, all_raw_dicts_for_step

    except Exception as e:
        # Log the error outside the app context if it happens during context setup/teardown or general execution
        logger.error(f"Error executing research step '{step_name}': {e}", exc_info=True)
        # Return step name and error messages/empty lists outside the context
        error_msg = f"[System Error: Failed to execute research step '{step_name}' due to {type(e).__name__}]"
        return step_name, [error_msg], []


# --- Main Deep Research Orchestration ---
def perform_deep_research(query: str) -> str:
    """
    Orchestrates the deep research process from query to final report.
    """
    logger.info(f"--- Starting Deep Research for Query: '{query}' ---")

    # 1. Generate Initial Research Plan
    research_plan: List[Tuple[str, str]] = query_to_research_plan(query)
    if not research_plan:
        return "[Error: Could not generate initial research plan.]"
    logger.info(f"Initial Research Plan:\n{json.dumps(research_plan, indent=2)}")

    # 2. Prepare for Research Execution
    collected_research: Dict[str, List[str]] = (
        {}
    )  # Stores processed content strings per *initial* step name
    collected_raw_results: Dict[str, List[Dict]] = (
        {}
    )  # Stores raw result dicts per *initial* step name
    original_step_details: Dict[str, str] = {
        name: desc for name, desc in research_plan
    }  # Store descriptions for reference

    # 3. Execute Initial Research Steps in Parallel using Threads
    logger.info(
        f"--- Executing {len(research_plan)} Initial Research Steps in Parallel (Threads) ---"
    )
    # Use ThreadPoolExecutor for I/O-bound tasks (LLM calls, web requests)
    # Threads share the Flask application context, avoiding the RuntimeError.
    with ThreadPoolExecutor() as executor:
        # Submit all research steps to the executor
        future_to_step = {
            executor.submit(
                _execute_research_step, name, desc
            ): name  # _execute_research_step now returns 3 items
            for name, desc in research_plan
        }

        # Process completed futures as they finish
        for future in as_completed(future_to_step):
            step_name = future_to_step[future]
            try:
                # Get the result tuple (step_name, processed_strings, raw_dicts)
                completed_step_name, processed_results, raw_results = future.result()

                # Ensure the returned name matches (sanity check)
                if completed_step_name == step_name:
                    collected_research[step_name] = processed_results
                    collected_raw_results[step_name] = raw_results
                    logger.info(
                        f"Successfully collected results for step: {step_name} ({len(processed_results)} processed, {len(raw_results)} raw)"
                    )
                else:
                    logger.error(
                        f"Mismatch in step name from future: expected {step_name}, got {completed_step_name}"
                    )
                    # Store error messages in both dicts for consistency
                    error_msg = f"[System Error: Mismatch in step name processing for '{step_name}']"
                    collected_research[step_name] = [error_msg]
                    collected_raw_results[step_name] = [{"error": error_msg}]

            except Exception as exc:
                logger.error(
                    f"Step '{step_name}' generated an exception during execution: {exc}",
                    exc_info=True,
                )
                # Store error messages in both dicts
                error_msg = (
                    f"[System Error: Step '{step_name}' failed during execution: {exc}]"
                )
                collected_research[step_name] = [error_msg]
                collected_raw_results[step_name] = [{"error": error_msg}]

    logger.info(
        "--- Finished Parallel Execution of Initial Research Steps (Threads) ---"
    )
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
        return "[Error: Could not generate updated report plan based on research.]"
    logger.info(
        f"Updated Report Plan (Outline):\n{json.dumps(updated_report_plan, indent=2)}"
    )

    # 5. Synthesize Report Sections based on the *updated* plan
    # This part remains sequential as each section synthesis depends on the overall collected data.
    report_sections: Dict[str, str] = {}
    report_references: Dict[str, List[str]] = (
        {}
    )  # Stores references cited per section (e.g., "Source 1", "Source 3")

    # Consolidate *all* raw research items collected across *all* initial steps.
    # The synthesis function needs access to all potential sources for citation.
    all_raw_research_items = []
    for step_name in collected_raw_results:
        all_raw_research_items.extend(collected_raw_results[step_name])

    logger.info(
        f"Total raw research items available for synthesis: {len(all_raw_research_items)}"
    )

    for section_name, section_description in updated_report_plan:
        logger.info(f"\n--- Synthesizing Report Section: {section_name} ---")

        # Pass the consolidated list of raw result dictionaries to the synthesis function.
        # The function's prompt expects this format to extract URLs for citations.
        report_section_text, section_refs = synthesize_research_into_report_section(
            section_name,
            section_description,
            all_raw_research_items,  # Pass the list of raw dictionaries
        )
        report_sections[section_name] = report_section_text
        # Store the list of cited source identifiers (e.g., ["Source 1", "Source 3"])
        report_references[section_name + "_references"] = section_refs

    # 6. Assemble Final Report Components
    full_report_body = "\n\n".join(report_sections.values())

    executive_summary = create_exec_summary(full_report_body)
    next_steps = create_next_steps(full_report_body)

    # Create Works Cited using the collected references and the raw results dicts
    # Pass the consolidated raw results dict list here
    works_cited = create_works_cited(report_references, all_raw_research_items)

    # 7. Generate Final Report using LLM for formatting and citation linking
    final_report_output = final_report(
        executive_summary, full_report_body, next_steps, works_cited
    )

    logger.info(f"--- Deep Research Complete for Query: '{query}' ---")
    return final_report_output
