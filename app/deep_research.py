# deep_research.py

import json
import re
from typing import List, Tuple, Dict, Any

# Assuming ai_services.py and web_search.py are in the same directory
# or accessible via the Python path.
# Use appropriate import style for your project structure (e.g., relative imports if part of a package)
from .ai_services import generate_text  # For LLM interactions
from .plugins.web_search import (
        perform_web_search,
        fetch_web_content,
    )  # For web searching and scraping


import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# --- Helper Function for Parsing LLM JSON Output ---
def parse_llm_json_output(llm_output: str, expected_keys: List[str]) -> Any:
    """
    Attempts to parse JSON output from the LLM.
    Handles potential JSON decoding errors and missing keys.
    """
    try:
        # Clean potential markdown code block fences
        cleaned_output = re.sub(r"```json\n?|\n?```", "", llm_output).strip()
        data = json.loads(cleaned_output)

        # Basic validation for expected structure (can be made more robust)
        if isinstance(data, dict):
            if not all(key in data for key in expected_keys):
                logger.warning(
                    f"LLM JSON output missing expected keys ({expected_keys}). Output: {cleaned_output}"
                )
                return None
        elif isinstance(data, list):
            # Add checks if list structure is expected (e.g., list of dicts)
            pass
        else:
            logger.warning(
                f"LLM JSON output was not a dict or list as expected. Output: {cleaned_output}"
            )
            return None

        return data
    except json.JSONDecodeError:
        logger.error(f"Failed to decode LLM JSON output: {llm_output}")
        return None
    except Exception as e:
        logger.error(f"Error parsing LLM JSON output: {e}")
        return None


# --- Core Research Functions ---


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


def web_search(search_query: str, num_results: int = 3) -> List[str]:
    """
    Performs a web search using the provided query and returns formatted results.
    Leverages the perform_web_search function from web_search.py.
    """
    logger.info(f"Performing web search for: '{search_query}'")
    try:
        # perform_web_search already returns a list of formatted strings
        # including Title, Snippet, Link, and potentially fetched Web Content
        search_results = perform_web_search(search_query, num_results=num_results)

        # Filter out potential error messages returned by perform_web_search
        valid_results = [
            res for res in search_results if not res.startswith("[System Error")
        ]
        logger.info(f"Web search returned {len(valid_results)} valid results.")
        return valid_results
    except Exception as e:
        logger.error(
            f"Error during web search for '{search_query}': {e}", exc_info=True
        )
        return []


def scrape_web(search_result_string: str) -> str:
    """
    Extracts the fetched web content from the formatted string returned by web_search.
    If content wasn't fetched or is missing, it attempts to fetch it using the link.
    """
    logger.debug(f"Attempting to extract/scrape content from result string.")
    content_marker = "\n[Web Content]\n"
    link_marker = "\n[Link]\n"
    failed_marker = "[Failed to retrieve full website content.]"

    content = ""
    link = None

    # Extract link first
    link_match = re.search(
        rf"{re.escape(link_marker)}(.*?)(\n\[|$)", search_result_string, re.DOTALL
    )
    if link_match:
        link = link_match.group(1).strip()
        logger.debug(f"Extracted link: {link}")

    # Check for existing content
    content_match = re.search(
        rf"{re.escape(content_marker)}(.*)", search_result_string, re.DOTALL
    )
    if content_match:
        content = content_match.group(1).strip()
        # Check if the existing content indicates failure
        if failed_marker in content:
            logger.warning(f"Previous fetch failed for {link}. Attempting refetch.")
            content = ""  # Reset content to trigger refetch
        elif content:
            logger.debug(f"Extracted existing web content (length: {len(content)}).")
            return link, content  # Return existing content if valid

    # If no valid content exists and we have a link, try fetching now
    if not content and link:
        logger.info(
            f"No existing content found or refetch needed. Scraping URL: {link}"
        )
        try:
            fetched_content = fetch_web_content(
                link
            )  # Use the function from web_search.py
            if fetched_content:
                logger.info(
                    f"Successfully scraped content (length: {len(fetched_content)}) from {link}."
                )
                return link, fetched_content
            else:
                logger.warning(f"Scraping returned no content from {link}.")
                return link, f"[Scraping failed for URL: {link}]"
        except Exception as e:
            logger.error(f"Error scraping URL {link}: {e}", exc_info=True)
            return link, f"[Scraping error for URL: {link} - {e}]"
    elif not link:
        logger.warning("Could not extract link from search result string to scrape.")
        return link, "[Scraping failed: No link found in result string]"
    else:
        # This case should ideally not be reached if content_match logic is correct
        logger.debug("Content was present but empty, returning empty string.")
        return link, ""


def query_and_research_to_updated_plan(
    query: str, collected_research: Dict[str, List[str]]
) -> List[Tuple[str, str]]:
    """
    Takes the original query and collected research, asks an LLM to refine the research plan
    into a report outline. Expects JSON list of [section_name, section_description] pairs.
    """
    logger.info("Generating updated report plan based on collected research.")

    # Format the collected research for the prompt (provide snippets or summaries)
    research_summary = ""
    for step_name, research_items in collected_research.items():
        research_summary += f"\n**Research Step: {step_name}**\n"
        if research_items:
            # Provide first N characters of the 'content' key as a snippet
            snippets = [
                f"- {item.get('content', '')[:500]}..." for item in research_items[:2] # Show snippets from first 2 results
            ]
            research_summary += "\n".join(snippets)
            if len(research_items) > 2:
                research_summary += f"\n- ... ({len(research_items) - 2} more items)"
        else:
            research_summary += "- No research found for this step."
        research_summary += "\n"

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
            f"Source {i+1}:\n{research.get('content', '[Content not available]')}"
            for i, research in enumerate(collected_research_for_step)
        ]
    )

    prompt = f"""
    You are a research assistant writing a section for a report.
    Your task is to synthesize the provided research findings into a well-structured report section.

    Section Name: "{section_name}"
    Section Description (Key points to cover): "{section_description}"

    Provided Research (Multiple sources):
    --- START RESEARCH ---
    {formatted_research}
    --- END RESEARCH ---

    Instructions:
    1. Write the report section based *only* on the provided research.
    2. Structure the section logically using Markdown (headings, paragraphs, lists). Start with a Level 2 Heading (## {section_name}).
    3. Accurately reflect the information found in the sources.
    4. **Crucially:** Keep track of which source(s) support each key piece of information. While writing, you don't need explicit inline citations, but be mindful of the origin.
    5. After writing the section, list the sources (using the "Source N" identifiers from the input) that were *actually used* to construct the section content.

    Return your response as a JSON object with two keys:
    - "report_section": A string containing the full Markdown text of the report section.
    - "references": A JSON list of strings, where each string is the identifier of a source used (e.g., ["Source 1", "Source 3"]).

    Example JSON Output:
    ```json
    {{
      "report_section": "## Section Title\\n\\nBased on Source 1, the key finding is... Source 2 further elaborates that...",
      "references": ["Source 1", "Source 2"]
    }}
    ```

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
            title = f"Source {source_counter}" # Placeholder title
            if link:
                # Try to create a slightly better title from the link if possible
                try:
                    hostname = re.match(r"https?://(?:www\.)?([^/]+)", link).group(1)
                    if hostname:
                        title = f"Content from {hostname}"
                except Exception:
                    pass # Keep placeholder if regex fails

            source_details[source_id] = {
                "link": link,
                "title": title, # Use generated or placeholder title
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
            formatted_report = re.sub(r"^```markdown\n?", "", formatted_report, flags=re.IGNORECASE)
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


# --- Main Execution Function ---


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

    for step_name, step_description in research_plan:
        original_step_details[step_name] = step_description
        collected_research[step_name] = []
        logger.info(f"\n--- Processing Research Step: {step_name} ---")
        logger.info(f"Description: {step_description}")

        # a. Determine Search Queries
        search_queries: List[str] = determine_research_queries(step_description)
        if not search_queries:
            logger.warning(
                f"No search queries generated for step '{step_name}'. Skipping web search."
            )
            continue

        # b. Perform Web Search & Scrape Results
        for search_query in search_queries:
            search_results: List[str] = web_search(
                search_query
            )  # Gets formatted strings
            for result_string in search_results:
                # Extract/scrape content and link from the result string
                link, scraped_content = scrape_web(result_string)
                if scraped_content and not scraped_content.startswith("[Scraping failed"):
                    # Store as dict including the link
                    research_item = {"content": scraped_content, "link": link}
                    collected_research[step_name].append(research_item)
                else:
                    logger.debug(
                        f"No useful content scraped from a result for query '{search_query}'."
                    )
        logger.info(
            f"Collected {len(collected_research[step_name])} research items for step '{step_name}'."
        )

    # 3. Generate Updated Report Plan (Outline)
    updated_report_plan: List[Tuple[str, str]] = query_and_research_to_updated_plan(
        query, collected_research
    )
    if not updated_report_plan:
        logger.warning(
            "Could not generate updated report plan. Attempting synthesis with original plan."
        )
        # Fallback: Use original plan structure for synthesis? Or return error?
        # For now, let's try using the original plan for the report structure
        updated_report_plan = research_plan
        # return "[Error: Could not generate updated report plan after research.]"
    logger.info(
        f"Updated Report Plan (Outline):\n{json.dumps(updated_report_plan, indent=2)}"
    )

    # 4. Synthesize Report Sections
    report_sections: Dict[str, str] = {}
    report_references: Dict[str, List[str]] = {}  # Stores references used *per section*

    # Map updated plan sections back to original research (needs careful handling if structure changed drastically)
    # Simple approach: Assume the updated plan roughly corresponds to original steps or synthesizes across them.
    # We pass ALL research relevant to the *original* step that seems closest, or maybe ALL research if mapping is hard.
    # For simplicity here, we'll iterate through the *updated* plan and try to find corresponding *original* research.
    # This might require a more sophisticated mapping step in a real application.

    research_for_synthesis = collected_research  # Use the originally collected research keyed by original step name

    for section_name, section_description in updated_report_plan:
        logger.info(f"\n--- Synthesizing Report Section: {section_name} ---")
        # Simplistic: Find the original step this section most relates to (e.g., by name similarity - crude)
        # Or, more robustly, the LLM in step 3 should indicate which original research informed each new section.
        # For this example, we'll just pass ALL collected research to each synthesis step.
        # This is inefficient but avoids complex mapping logic for now.
        all_research_items = [
            item for sublist in research_for_synthesis.values() for item in sublist
        ]

        if not all_research_items:
            logger.warning(
                f"No research available to synthesize section '{section_name}'."
            )
            report_sections[section_name] = (
                f"## {section_name}\n\n[Skipped: No research data available for synthesis.]\n"
            )
            report_references[section_name + "_references"] = []
            continue

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


# --- Example Usage ---
if __name__ == "__main__":
    # Ensure you have Flask context or another way to provide API keys
    # if ai_services relies on current_app.config
    # This basic example might fail if ai_services needs Flask context.
    # You might need to wrap this in a Flask route or manually configure the client.

    # Example requires API keys to be configured where ai_services expects them.
    # If running standalone without Flask, you might need to modify ai_services
    # or manually initialize the Gemini client here.

    # --- Mocking Flask context for standalone run (IF NEEDED) ---
    class MockApp:
        config = {
            # ADD YOUR API KEYS HERE FOR STANDALONE TESTING
            # 'API_KEY': 'YOUR_GEMINI_API_KEY',
            # 'GOOGLE_API_KEY': 'YOUR_GOOGLE_SEARCH_API_KEY',
            # 'GOOGLE_CSE_ID': 'YOUR_CUSTOM_SEARCH_ENGINE_ID',
            # 'DEFAULT_MODEL': 'gemini-pro', # Or another suitable model
            # 'SUMMARY_MODEL': 'gemini-pro',
            # 'PRIMARY_MODEL': 'gemini-pro',
        }

    class MockG:
        def __init__(self):
            self._context = {}

        def __contains__(self, key):
            return key in self._context

        def __setitem__(self, key, value):
            self._context[key] = value

        def __getitem__(self, key):
            return self._context[key]

    # Manually push context if necessary (use with caution)
    # from contextlib import contextmanager
    # @contextmanager
    # def push_context(app, g_obj):
    #     global current_app, g
    #     _original_current_app = current_app
    #     _original_g = g
    #     current_app = app
    #     g = g_obj
    #     try:
    #         yield
    #     finally:
    #         current_app = _original_current_app
    #         g = _original_g

    # mock_app = MockApp()
    # mock_g = MockG()

    # if not mock_app.config.get('API_KEY') or not mock_app.config.get('GOOGLE_API_KEY'):
    #     print("\nWARNING: API keys not set in MockApp.config. LLM and Search calls will likely fail.")
    #     # Set dummy keys to avoid immediate crashes but expect dummy output
    #     mock_app.config['API_KEY'] = 'DUMMY_KEY'
    #     mock_app.config['GOOGLE_API_KEY'] = 'DUMMY_KEY'
    #     mock_app.config['GOOGLE_CSE_ID'] = 'DUMMY_ID'
    #     mock_app.config['DEFAULT_MODEL'] = 'dummy-model'
    #     mock_app.config['SUMMARY_MODEL'] = 'dummy-model'
    #     mock_app.config['PRIMARY_MODEL'] = 'dummy-model'

    # --- Run the research ---
    # with push_context(mock_app, mock_g): # Uncomment if Flask context is needed by imported modules
    #     test_query = "What are the latest advancements in quantum computing and their potential impact on cryptography?"
    #     final_report_result = perform_deep_research(test_query)

    #     print("\n\n--- FINAL REPORT ---")
    #     print(final_report_result)
    #     print("--- END OF REPORT ---")

    # --- Simpler execution if context isn't strictly needed or handled internally ---
    test_query = "Explain the main challenges and opportunities in deploying large-scale renewable energy projects."
    print(f"Running deep research for: {test_query}")
    # Ensure API keys are available via environment variables or however ai_services/web_search expects them
    # when run outside Flask. If they rely *only* on Flask context, the above mocking is necessary.
    final_report_result = perform_deep_research(test_query)

    print("\n\n--- FINAL REPORT ---")
    print(final_report_result)
    print("--- END OF REPORT ---")
