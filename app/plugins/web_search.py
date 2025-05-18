from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from flask import current_app
import requests
import re
from bs4 import BeautifulSoup
import os # Import os for path operations
from urllib.parse import urlparse # To parse URL for filename fallback
from werkzeug.utils import secure_filename # To sanitize filenames
import cgi # To parse Content-Disposition header

# Imports for save_file_record_to_db and transcribe_pdf_bytes are removed as they are no longer used.

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
              - 'url': The original URL.
              - 'type': 'html', 'transcribed_pdf_text', or 'error'.
              - 'content': Extracted HTML text, transcribed PDF text, or an error message.
              - 'filename': Original filename if applicable (especially for PDFs).
              - 'saved_file_id': The ID of the saved file record in the database, if successful.
    """
    # Imports for save_file_record_to_db and transcribe_pdf_bytes are removed
    # as they are no longer used directly in this function with manual tool calling.

    saved_file_id = None # Initialize - though this won't be set here anymore
    try:
        # Use stream=True to check headers before downloading the whole body
        response = requests.get(url, timeout=15, stream=True, headers={'User-Agent': 'MyWebApp/1.0'})
        response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)

        content_type = response.headers.get('Content-Type', '').lower()
        logger.info(f"Fetching URL: {url}, Content-Type: {content_type}")

        # --- PDF Handling ---
        if 'application/pdf' in content_type:
            logger.info(f"Detected PDF content at {url}. Downloading...")
            # Download the full PDF content
            pdf_bytes = response.content # Read the full content now
            logger.info(f"Downloaded {len(pdf_bytes)} bytes for PDF from {url}")

            # --- Extract Filename ---
            filename = None
            # Try Content-Disposition header first
            content_disposition = response.headers.get('Content-Disposition')
            if content_disposition:
                value, params = cgi.parse_header(content_disposition)
                if 'filename' in params:
                    filename = params['filename']
                    logger.info(f"Extracted filename from Content-Disposition: {filename}")

            # Fallback to URL parsing if header doesn't provide filename
            if not filename:
                parsed_url = urlparse(url)
                filename = os.path.basename(parsed_url.path)
                if not filename: # Handle cases like domain.com/ (no path)
                    filename = parsed_url.netloc + ".pdf" # Use domain name
                logger.info(f"Using filename from URL: {filename}")

            # Sanitize filename
            filename = secure_filename(filename)
            # Ensure it has a .pdf extension if missing (common issue)
            if not filename.lower().endswith('.pdf'):
                filename += ".pdf"
            logger.info(f"Sanitized PDF filename: {filename}") # Removed "for AFC"

            # Return raw PDF bytes; transcription and saving will be handled by the caller (ai_services)
            return {'type': 'pdf', 'content': pdf_bytes, 'url': url, 'filename': filename}

        # --- HTML Handling ---
        # Proceed only if it's likely HTML (or unspecified, default to HTML attempt)
        if 'text/html' in content_type or not content_type:
            # Download the full content now
            html_content = response.content # Read the full content now
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
                # DB saving will be handled by the caller (ai_services)
                return {'type': 'html', 'content': text, 'url': url} # Removed saved_file_id
            else:
                 # If no text could be extracted even if HTML structure was found
                 return {'type': 'error', 'content': "Could not extract text content from HTML.", 'url': url} # Removed saved_file_id

        # --- Handle other content types ---
        else:
            logger.warning(f"Unsupported Content-Type '{content_type}' at {url}. Skipping content extraction.") # Removed "for AFC"
            return {'type': 'error', 'content': f"Unsupported content type: {content_type}", 'url': url} # Removed saved_file_id

    except requests.exceptions.Timeout:
        logger.error(f"Timeout error fetching content from {url}") # Removed "for AFC"
        return {'type': 'error', 'content': "Request timed out.", 'url': url} # Removed saved_file_id
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching content from {url}: {e}") # Removed "for AFC"
        return {'type': 'error', 'content': f"Network or HTTP error: {e}", 'url': url} # Removed saved_file_id
    except Exception as e:
        # Catch potential BeautifulSoup errors or others
        logger.error(f"An unexpected error occurred while processing content from {url}: {e}", exc_info=True) # Removed "for AFC"
        return {'type': 'error', 'content': f"An unexpected error occurred: {e}", 'url': url} # Removed saved_file_id


def perform_web_search(query: str, num_results: int = 3):
    """
    Performs a web search using the Google Custom Search JSON API.
    This version is intended for Automatic Function Calling (AFC).

    Args:
        query (str): The search query string.
        num_results (int): The desired number of search results (max 10 per request).

    Returns:
        list: A list of dictionaries, where each dictionary contains:
              - 'title': The title of the search result.
              - 'link': The URL of the search result.
              - 'snippet': A snippet of text from the search result.
              Returns an empty list or a list with error messages on failure.
    """
    logger.info(
        f"Performing Google Custom Search for AFC: '{query}' (requesting {num_results} results)"
    )

    api_key = current_app.config.get("GOOGLE_API_KEY")
    cse_id = current_app.config.get("GOOGLE_CSE_ID")

    if not api_key:
        logger.error("ERROR: GOOGLE_API_KEY not found in Flask config for AFC search.")
        # For AFC, return a structure that can be processed, or raise an error the SDK might catch.
        # Returning an error message within the expected list structure might be best for the LLM.
        return [{"title": "Search Error", "link": "", "snippet": "[System Error: Web search API key not configured]"}]
    if not cse_id:
        logger.error("ERROR: GOOGLE_CSE_ID not found in Flask config for AFC search.")
        return [{"title": "Search Error", "link": "", "snippet": "[System Error: Web search Engine ID not configured]"}]

    # Ensure num_results is within the API limits (1-10)
    num_results = max(1, min(num_results, 10))

    search_results_processed = []
    try:
        service = build("customsearch", "v1", developerKey=api_key)
        result = service.cse().list(q=query, cx=cse_id, num=num_results).execute()
        search_items = result.get("items", [])

        if not search_items:
            logger.info("Web search returned no results.")
            return []

        for i, item in enumerate(search_items):
            title = item.get("title", "No Title")
            link = item.get("link", "no link")
            snippet = item.get("snippet", "No Snippet Available").replace(chr(10), ' ').replace(chr(13), ' ')

            # Content fetching and saving are no longer done here.
            # These will be handled by the "scrape_url" tool if the LLM decides to use it.

            result_data = {
                'title': title,
                'link': link,
                'snippet': snippet,
            }
            search_results_processed.append(result_data)
            logger.info(f"  - Found Result {i+1}: {title}")

        return search_results_processed

    except HttpError as e:
        logger.error(f"ERROR during Google Custom Search API call for AFC: {e}")
        return [{"title": "Search API Error", "link": "", "snippet": f"[System Error: Web search failed. Reason: {e.resp.status} {e.resp.reason}]"}]
    except Exception as e:
        logger.error(f"An unexpected error occurred during web search for AFC: {e}", exc_info=True)
        return [{"title": "Search Unexpected Error", "link": "", "snippet": "[System Error: An unexpected error occurred during web search.]"}]
