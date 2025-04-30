import json
import logging
import re
from typing import List, Tuple, Any, Dict

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
    section_name: str, section_description: str, collected_research_for_step: List[str]
) -> Tuple[str, List[str]]:
    """
    Uses an LLM to synthesize collected research into a coherent report section.
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

    # Format research for the prompt, accessing the 'content' key
    formatted_research = "\n\n---\n\n".join(
        [
            f"Source {i+1}:\n{research.get('content', '[Content not available]')}\nURL:{research.get('link')}"
            for i, research in enumerate(collected_research_for_step)
        ]
    )

    prompt = f"""
You are a research assistant writing a section for a report.
Your task is to synthesize the provided research findings into a well-structured report section and include inline citations using a specific Markdown link format.

Section Name: "{section_name}"
Section Description (Key points to cover): "{section_description}"

Provided Research (Multiple sources, including URLs):
--- START RESEARCH ---
{formatted_research}
--- END RESEARCH ---

*Note: The 'Provided Research' is expected to be formatted clearly, e.g., each source begins with "Source N: [Snippet Text] (URL: http://example.com/sourceN)". Ensure your '{formatted_research}' variable is structured this way.*

Instructions:
1.  Write the report section based *only* on the information contained within the `Provided Research`. Do not include outside knowledge.
2.  Structure the section logically using Markdown (headings, paragraphs, lists, bolding). Start with a Level 2 Heading (## {section_name}).
3.  Accurately and factually reflect the information found in the sources.
4.  **Crucially: Include inline citations for all factual claims, statistics, and significant information derived from the research.**
    *   Cite the original source(s) immediately after the sentence, clause, or fact it supports.
    *   Use the Markdown link format `[[SourceNumber]](URL)`.
    *   The `SourceNumber` is the number from the 'Source N' identifier (e.g., use `1` for 'Source 1', `2` for 'Source 2').
    *   The `URL` is the URL provided with that specific source in the `Provided Research` section.
    *   This format `[[N]](url)` means the rendered text will be `[N]` (including the brackets), and this entire `[N]` will be a clickable link to the URL.
    *   If a piece of information is supported by multiple sources, include multiple citations sequentially (e.g., `...key finding.[[1]](url1)[[3]](url3)`).
5.  After writing the section, list the identifiers of the sources (using the "Source N" format, e.g., "Source 1", "Source 3") that were *actually cited* within the section content.

Return your response as a JSON object with two keys:
-   `report_section`: A string containing the full Markdown text of the report section, including the inline citations formatted as `[[Number]](URL)`.
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
    report_references: Dict[str, List[str]], collected_research: Dict[str, List[str]]
) -> str:
    """
    Creates a works cited section based on the references collected during synthesis.
    It attempts to extract actual URLs or source identifiers from the original research data.
    """
    logger.info("Generating works cited section.")

    cited_items = []
    source_details = {}  # Store details like link for each original source item

    # First, iterate through collected_research to build source details from the dict structure
    source_counter = 1
    for step_name, research_items in collected_research.items():
        for item_dict in research_items:
            source_id = f"Source {source_counter}"
            link = item_dict.get("link")
            # We don't have a reliable title field, use link or a placeholder
            title = f"Source {source_counter}"  # Placeholder title
            if link:
                # Try to create a slightly better title from the link if possible
                try:
                    hostname = re.match(r"https?://(?:www\.)?([^/]+)", link).group(1)
                    if hostname:
                        title = f"Content from {hostname}"
                except Exception:
                    pass  # Keep placeholder if regex fails

            source_details[source_id] = {
                "link": link,
                "title": title,  # Use generated or placeholder title
                "original_index": source_counter,
            }
            source_counter += 1

    # Collect all unique references mentioned across report sections
    unique_cited_source_ids = set()
    for section_name, refs in report_references.items():
        if section_name.endswith(
            "_references"
        ):  # Ensure we only look at reference lists
            unique_cited_source_ids.update(refs)

    # Build the works cited list using the extracted details
    for source_id in sorted(
        list(unique_cited_source_ids),
        key=lambda x: source_details.get(x, {}).get("original_index", 999),
    ):
        details = source_details.get(source_id)
        if details:
            entry = f"{details['original_index']}. "  # Start with original index number
            # Use the title we stored (placeholder or derived from hostname)
            entry += f"*{details.get('title', 'Source')}*"

            link = details.get("link")
            if link:
                entry += f" - Available at: <{link}>"  # Use angle brackets for URL
            else:
                entry += " (Link not available)"
            cited_items.append(entry)
        else:
            # Fallback if source_id wasn't found (shouldn't happen ideally)
            cited_items.append(f"- {source_id} (Details not found)")

    works_cited_content = "# Works Cited\n\n"
    if cited_items:
        works_cited_content += "\n".join(cited_items)
    else:
        works_cited_content += (
            "No specific sources were cited in the generated report sections.\n"
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

    # 2. Execute Research Steps
    collected_research: Dict[str, List[str]] = (
        {}
    )  # Stores raw scraped content per *initial* step name
    original_step_details: Dict[str, str] = (
        {}
    )  # Store description for mapping later if needed

    # 3. initial research
    for step_name, step_description in research_plan:
        original_step_details[step_name] = step_description
        collected_research[step_name] = []
        logger.info(f"\n--- Processing Research Step: {step_name} ---")
        logger.info(f"Description: {step_description}")

        # a. Determine Search Queries
        search_queries: List[str] = determine_research_queries(step_description)

        # b. Perform Web Search & Scrape Results
        for search_query in search_queries:
            search_results, _ = web_search(search_query)  # Gets formatted strings
            collected_research[step_name].extend(search_results)

    # 3. Generate Updated Report Plan (Outline)
    updated_report_plan: List[Tuple[str, str]] = query_and_research_to_updated_plan(
        query, collected_research
    )
    
    logger.info(
        f"Updated Report Plan (Outline):\n{json.dumps(updated_report_plan, indent=2)}"
    )

    # 4. Synthesize Report Section
    for section_name, section_description in updated_report_plan:
        logger.info(f"\n--- Synthesizing Report Section: {section_name} ---")
        if not collected_research.get(section_name):
            collected_research[section_name] = []
        if (section_name, section_description) not in research_plan:
            # only run more searches if the plan hasn't changed for this step
            search_queries: List[str] = determine_research_queries(section_description)
        
            # b. Perform Web Search & Scrape Results
            for search_query in search_queries:
                search_results, _ = web_search(
                    search_query
                )  # Gets formatted strings
                collected_research[section_name].extend(search_results)
                logger.info(
                    f"Collected {len(collected_research[section_name])} research items for step '{section_name}'."
                )

        all_research_items = [
            item for sublist in collected_research.values() for item in sublist
        ]

        # Pass all collected research items to the synthesis function
        report_section_text, section_refs = synthesize_research_into_report_section(
            section_name,
            section_description,
            all_research_items,  # Pass all collected research
        )
        report_sections[section_name] = report_section_text
        # Store references under a specific key format
        report_references[section_name + "_references"] = section_refs

    # 5. Assemble Final Report Components
    full_report_body = "\n\n".join(report_sections.values())

    executive_summary = create_exec_summary(full_report_body)
    next_steps = create_next_steps(full_report_body)
    # Pass the references collected during synthesis AND the original research data
    works_cited = create_works_cited(report_references, collected_research)

    # 6. Generate Final Report
    final_report_output = final_report(
        executive_summary, full_report_body, next_steps, works_cited
    )

    logger.info(f"--- Deep Research Complete for Query: '{query}' ---")
    return final_report_output
