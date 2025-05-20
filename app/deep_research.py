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
            else: # If it's a list but not of dicts, or empty, and no specific keys for list items
                logger.debug(
                    "Parsed JSON is a list (not of dicts or empty), returning as is."
                )
                return parsed_output
        elif isinstance(parsed_output, list) and not expected_keys: # List of strings, numbers etc.
             return parsed_output
        else:
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
    app_context # Pass Flask app context for background thread safety
) -> List[str]:
    """
    Executes a single research step using an LLM to orchestrate web searches and scraping.
    Returns a list of strings, where each string is a formatted summary of a processed source.
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

            # Comprehensive prompt for the LLM to manage the research sub-tasks
            # This prompt needs to be carefully engineered.
            prompt = f"""
You are an AI research assistant executing a specific step of a larger research plan.
Your goal is to gather relevant information for the following research step:
"{step_description}"

To do this, you must:
1.  Formulate 2-3 targeted search queries based on the step description.
2.  Execute these queries using the `web_search` tool. This tool will return a list of search results (title, link, snippet).
3.  Review the search results. For each promising link that seems highly relevant and likely to contain detailed information, use the `scrape_url` tool to fetch its full content.
    *   The `scrape_url` tool will return text content for HTML pages.
    *   If `scrape_url` tool returns raw PDF data (which you cannot read directly), make a note of the PDF's title and link, and state that it is a PDF document. Do not attempt to include the raw PDF data in your output.
    *   If scraping fails or a page has no useful content, note that and rely on the snippet if it's informative.
4.  Synthesize the information you've gathered from the scraped content and relevant snippets.
5.  For each distinct source of information you used (whether fully scraped or just a snippet), format it as a string with the following structure:
    "Title: [Title of the source or page]\nLink: [URL of the source]\nSnippet: [Original snippet from web_search if available]\nContent: [Your summary of the scraped content, or the full text if concise and relevant, or a note like 'PDF document, content not directly viewable', or 'Scraping failed/No content extracted']\n---"
6.  Return all these formatted source strings as a JSON list. Each string in the list represents one processed source.

Example of a single formatted source string in the output list:
"Title: Example Research Paper\nLink: https://example.com/paper.pdf\nSnippet: This paper discusses advanced research techniques...\nContent: PDF document, content not directly viewable.\n---"

Another example:
"Title: Blog Post on Topic X\nLink: https://example.com/blog/topic-x\nSnippet: An insightful blog post covering Topic X...\nContent: The blog post details several key aspects of Topic X. Firstly, it highlights A. Secondly, it discusses B. [More summarized content from scrape]...\n---"

If a search result is not promising enough to scrape, but the snippet is useful, you can include it like:
"Title: Less Relevant Page\nLink: https://example.com/less-relevant\nSnippet: This page touches upon a related concept...\nContent: Based on snippet: This page touches upon a related concept. [No scraping performed or scrape failed]\n---"

Proceed with the research for the step description provided above. Ensure your final output is ONLY the JSON list of formatted source strings.
JSON Output:
            """

            if is_cancelled_callback():
                logger.info("Research step cancelled before LLM call.")
                return ["[AI Info: Research step cancelled by user.]"]

            generation_config = types.GenerateContentConfig(
                tools=[WEB_SEARCH_TOOL, WEB_SCRAPE_TOOL],
                # Potentially increase max_output_tokens if the combined summaries are long
                # temperature might be set lower for more factual summarization
            )
            
            if socketio and sid:
                socketio.emit("status_update", {"message": f"Researching: {step_description[:40]}..."}, room=sid)

            response = gemini_client.models.generate_content(
                model=model_to_use,
                contents=prompt,
                config=generation_config
            )
            
            # The SDK's automatic function calling handles the tool execution loop.
            # The final response.text should contain the JSON list of formatted strings.

            if response.text:
                logger.debug(f"LLM response for research step: {response.text[:500]}")
                parsed_items = parse_llm_json_output(response.text, expected_keys=[]) # Expecting a list of strings
                if isinstance(parsed_items, list) and all(isinstance(item, str) for item in parsed_items):
                    processed_research_items.extend(parsed_items)
                    logger.info(f"Successfully processed {len(parsed_items)} items for research step.")
                else:
                    logger.error(f"LLM response for research step was not a JSON list of strings: {response.text[:500]}")
                    processed_research_items.append(f"[System Error: LLM did not return a valid list of research items for '{step_description}'. Raw response: {response.text[:200]}]")
            else:
                logger.warning(f"LLM returned no text for research step: {step_description}")
                # Check for blocked prompt or other issues
                if response.prompt_feedback and response.prompt_feedback.block_reason:
                    reason = response.prompt_feedback.block_reason
                    msg = response.prompt_feedback.block_reason_message
                    logger.error(f"Prompt blocked for research step. Reason: {reason}, Message: {msg}")
                    processed_research_items.append(f"[System Error: Prompt blocked by API - {reason}. Please revise the query/step.]")
                else:
                    processed_research_items.append(f"[System Error: LLM returned no usable output for '{step_description}'.]")

        except Exception as e:
            logger.error(f"Error during execute_research_step for '{step_description}': {e}", exc_info=True)
            processed_research_items.append(f"[System Error: Exception during research step execution - {type(e).__name__}]")

        return processed_research_items


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
            research_items_for_step = execute_research_step(
                step_description,
                is_cancelled_callback,
                socketio,
                sid,
                app.app_context() # Pass the app context
            )
            collected_research[step_name] = research_items_for_step
            logger.info(
                f"--- Finished Research Step: {step_name} - Collected {len(research_items_for_step)} items ---"
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
                research_items_for_new_section = execute_research_step(
                    section_description,
                    is_cancelled_callback,
                    socketio,
                    sid,
                    app.app_context() # Pass the app context
                )
                # Ensure collected_research[section_name] is a list and extend it
                if section_name not in collected_research or not isinstance(collected_research[section_name], list):
                    collected_research[section_name] = []
                collected_research[section_name].extend(research_items_for_new_section)
                logger.info(
                    f"--- Finished Additional Research Step: {section_name} - Collected {len(research_items_for_new_section)} items ---"
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
