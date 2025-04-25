from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from flask import current_app
import requests
import re
from bs4 import BeautifulSoup


# Configure logging
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def fetch_web_content(url, selectors_to_try=None):
    """
    Fetches and extracts text content from a webpage using specified CSS selectors.

    Args:
        url (str): The URL of the webpage to scrape.
        selectors_to_try (list): A list of CSS selectors to try for finding the main content.
                                  If None, it will try a few common selectors.
                                  Each item in the list should be a dictionary with 'tag' (e.g., 'div', 'article') and
                                  optional 'attrs' (a dictionary of attributes like {'id': 'content', 'class': 'main'}).

    Returns:
        str: The extracted text content, or None if extraction fails.
    """
    try:
        response = requests.get(url, timeout=10)  # Added a timeout to prevent hanging
        response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)
        soup = BeautifulSoup(response.content, "html.parser")

        body = soup.find('body')  # Start from the body
        if not body:
            logger.warning(f"Could not find <body> tag in Wikipedia article: {url}")
            return None

        all_text = body.find_all(string=True) # Get all text nodes

        # Filter out script, style, and other unwanted tags
        visible_texts = [t for t in all_text if t.parent.name not in ['script', 'style', 'head', 'title', 'meta', '[document]']]

        # Join the visible texts and clean up whitespace
        text = "\n".join(visible_texts)
        text = re.sub(r"\[.*?\]", "", text)  # Remove citation-like markers
        text = text.replace(chr(10), " ").replace(chr(13), " ")  # Clean newlines
        text = '\n'.join(line.strip() for line in text.splitlines())  # Remove empty lines
        text = text.strip()

        return text

    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching content from {url}: {e}")
        return None
    except Exception as e:
        logger.error(
            f"An unexpected error occurred while processing content from {url}: {e}"
        )
        return None


def fetch_wikipedia_content(url):
    """Fetches the text content from a Wikipedia article."""
    try:
        response = requests.get(url)
        response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)

        soup = BeautifulSoup(response.content, "html.parser")
        content_div = soup.find("div", {"id": "mw-content-text"})
        if not content_div:
            logger.warning(
                f"Could not find 'mw-content-text' div in Wikipedia article: {url}"
            )
            return None

        paragraphs = content_div.find_all(
            "p"
        )  # or other relevant tags like 'li' for lists, 'h2' for headers

        # Extract text from all paragraph elements within the content div.
        text = "\n".join(
            [p.get_text() for p in paragraphs]
        )  # Concatenate all paragraphs.  Consider other tags too (h2, h3, etc)
        text = re.sub(r"\[.*?\]", "", text)  # Remove citation links
        text = text.replace(chr(10), " ").replace(chr(13), " ")  # Clean newlines
        return text.strip()  # Remove leading/trailing whitespace

    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching Wikipedia content from {url}: {e}")
        return None
    except Exception as e:
        logger.error(
            f"An unexpected error occurred while processing Wikipedia content from {url}: {e}"
        )
        return None


def perform_web_search(query, num_results=3):
    """
    Performs a web search using the Google Custom Search JSON API.

    Args:
        query (str): The search query string.
        num_results (int): The desired number of search results (max 10 per request).

    Returns:
        list: A list of strings, where each string contains the title and snippet
              of a search result, or an empty list if an error occurs or no results found.
    """
    logger.info(
        f"Performing Google Custom Search for: '{query}' (requesting {num_results} results)"
    )

    api_key = current_app.config.get("GOOGLE_API_KEY")
    cse_id = current_app.config.get("GOOGLE_CSE_ID")

    if not api_key:
        logger.error("ERROR: GOOGLE_API_KEY not found in Flask config.")
        return ["[System Error: Web search API key not configured]"]
    if not cse_id:
        logger.error("ERROR: GOOGLE_CSE_ID not found in Flask config.")
        return ["[System Error: Web search Engine ID not configured]"]

    # Ensure num_results is within the API limits (1-10)
    num_results = max(1, min(num_results, 10))

    search_snippets = []
    try:
        # Build the service object
        service = build("customsearch", "v1", developerKey=api_key)

        # Execute the search request
        result = service.cse().list(q=query, cx=cse_id, num=num_results).execute()

        # Extract snippets from results
        search_items = result.get("items", [])
        if not search_items:
            logger.info("Web search returned no results.")
            return []  # Return empty list, not an error message for the AI

        for i, item in enumerate(search_items):
            title = item.get("title", "No Title")
            link = item.get("link", "no link")
            snippet = item.get("snippet", "No Snippet Available")
            # link = item.get('link') # You could include the link if desired
            formatted_result = f"[Title]\n{title}\n[Snippet]\n{snippet.replace(chr(10), ' ').replace(chr(13), ' ')}\n[Link]\n{link}"  # Remove newlines from snippet

            
            # Check if the URL is a Wikipedia article
            logger.info(formatted_result)
            if "wikipedia.org" in link:
                content = fetch_wikipedia_content(link)
            else:
                content = fetch_web_content(link)
            if content:
                formatted_result += "\n[Web Content]\n" + content
            else:
                formatted_result += "\n[Failed to retrieve full website content.]"

            search_snippets.append(formatted_result)

            logger.info(f"  - Result {i+1}: {title}")

        return search_snippets

    except HttpError as e:
        logger.error(f"ERROR during Google Custom Search API call: {e}")
        # Provide a generic error for the AI context, don't expose detailed API errors
        return [
            f"[System Error: Web search failed. Reason: {e.resp.status} {e.resp.reason}]"
        ]
    except Exception as e:
        logger.error(f"An unexpected error occurred during web search: {e}")
        return ["[System Error: An unexpected error occurred during web search.]"]
