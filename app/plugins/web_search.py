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


def fetch_web_content(url):
    """
    Fetches content from a URL, attempting to extract text from HTML or identifying PDFs.

    Args:
        url (str): The URL of the webpage or resource.

    Returns:
        dict: A dictionary containing:
              - 'type': 'html', 'pdf', or 'error'
              - 'content': Extracted text (for html), raw bytes (for pdf, currently unused downstream), or error message.
              - 'url': The original URL.
    """
    try:
        # Use stream=True to check headers before downloading the whole body
        response = requests.get(url, timeout=15, stream=True, headers={'User-Agent': 'MyWebApp/1.0'})
        response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)

        content_type = response.headers.get('Content-Type', '').lower()
        logger.info(f"Fetching URL: {url}, Content-Type: {content_type}")

        # --- PDF Handling ---
        if 'application/pdf' in content_type:
            logger.info(f"Detected PDF content at {url}")
            # In a real scenario, you might download response.content here
            # For now, we just signal that it's a PDF.
            # pdf_bytes = response.content # Uncomment if you need the bytes later
            return {'type': 'pdf', 'content': b"PDF content placeholder", 'url': url} # Return placeholder bytes

        # --- HTML Handling ---
        # Proceed only if it's likely HTML (or unspecified, default to HTML attempt)
        if 'text/html' in content_type or not content_type:
            # Download the full content now
            html_content = response.content
            soup = BeautifulSoup(html_content, "html.parser")
            text = None

            # --- Wikipedia Specific Logic ---
            if "wikipedia.org" in url:
                content_div = soup.find("div", {"id": "mw-content-text"})
                if content_div:
                    paragraphs = content_div.find_all("p")
                    text = "\n".join([p.get_text() for p in paragraphs])
                    logger.info(f"Extracted Wikipedia content from {url}")
                else:
                    logger.warning(f"Could not find 'mw-content-text' div in Wikipedia article: {url}")
                    # Fallback to generic extraction if specific div not found
                    body = soup.find('body')
                    if body:
                        all_text_nodes = body.find_all(string=True)
                        visible_texts = [t for t in all_text_nodes if t.parent.name not in ['script', 'style', 'head', 'title', 'meta', '[document]']]
                        text = "\n".join(visible_texts)
                        logger.info(f"Used fallback generic extraction for Wikipedia page: {url}")

            # --- Generic HTML Logic ---
            else:
                body = soup.find('body')
                if body:
                    all_text_nodes = body.find_all(string=True)
                    # Filter out script, style, and other unwanted tags
                    visible_texts = [t for t in all_text_nodes if t.parent.name not in ['script', 'style', 'head', 'title', 'meta', '[document]']]
                    text = "\n".join(visible_texts)
                    logger.info(f"Extracted generic HTML content from {url}")
                else:
                    logger.warning(f"Could not find <body> tag in HTML page: {url}")

            # --- Text Cleaning (Common for both Wikipedia and Generic) ---
            if text:
                text = re.sub(r"\[.*?\]", "", text)  # Remove citation-like markers [1], [edit], etc.
                text = text.replace(chr(10), " ").replace(chr(13), " ") # Replace newlines within paragraphs with spaces
                text = '\n'.join(line.strip() for line in text.splitlines() if line.strip()) # Remove leading/trailing whitespace from lines and remove empty lines
                text = text.strip()
                return {'type': 'html', 'content': text, 'url': url}
            else:
                 # If no text could be extracted even if HTML structure was found
                 return {'type': 'error', 'content': "Could not extract text content from HTML.", 'url': url}

        # --- Handle other content types ---
        else:
            logger.warning(f"Unsupported Content-Type '{content_type}' at {url}. Skipping content extraction.")
            return {'type': 'error', 'content': f"Unsupported content type: {content_type}", 'url': url}

    except requests.exceptions.Timeout:
        logger.error(f"Timeout error fetching content from {url}")
        return {'type': 'error', 'content': "Request timed out.", 'url': url}
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching content from {url}: {e}")
        return {'type': 'error', 'content': f"Network or HTTP error: {e}", 'url': url}
    except Exception as e:
        # Catch potential BeautifulSoup errors or others
        logger.error(f"An unexpected error occurred while processing content from {url}: {e}", exc_info=True)
        return {'type': 'error', 'content': f"An unexpected error occurred: {e}", 'url': url}


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
            formatted_result = f"[Title]\n{title}\n[Snippet]\n{snippet.replace(chr(10), ' ').replace(chr(13), ' ')}\n[Link]\n{link}"

            # Fetch content using the unified function
            logger.info(f"Fetching content for result {i+1}: {link}")
            fetch_result = fetch_web_content(link)

            # Append content based on type
            if fetch_result['type'] == 'html':
                if fetch_result['content']:
                    formatted_result += "\n[Web Content]\n" + fetch_result['content']
                else:
                    formatted_result += "\n[Could not extract text content.]"
            elif fetch_result['type'] == 'pdf':
                # Indicate PDF was found, but don't include binary content here
                formatted_result += "\n[PDF Document Found. Content not extracted here.]"
            elif fetch_result['type'] == 'error':
                formatted_result += f"\n[Error fetching content: {fetch_result['content']}]"
            else: # Should not happen, but good to have a fallback
                 formatted_result += f"\n[Unknown content type encountered: {fetch_result.get('type', 'N/A')}]"


            search_snippets.append(formatted_result)
            logger.info(f"  - Processed Result {i+1}: {title} ({fetch_result['type']})")

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
