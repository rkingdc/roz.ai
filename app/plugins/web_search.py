from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from flask import current_app

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
    print(f"Performing Google Custom Search for: '{query}' (requesting {num_results} results)")

    api_key = current_app.config.get('GOOGLE_API_KEY')
    cse_id = current_app.config.get('GOOGLE_CSE_ID')

    if not api_key:
        print("ERROR: GOOGLE_API_KEY not found in Flask config.")
        return ["[System Error: Web search API key not configured]"]
    if not cse_id:
        print("ERROR: GOOGLE_CSE_ID not found in Flask config.")
        return ["[System Error: Web search Engine ID not configured]"]

    # Ensure num_results is within the API limits (1-10)
    num_results = max(1, min(num_results, 10))

    search_snippets = []
    try:
        # Build the service object
        service = build("customsearch", "v1", developerKey=api_key)

        # Execute the search request
        result = service.cse().list(
            q=query,
            cx=cse_id,
            num=num_results
        ).execute()

        # Extract snippets from results
        search_items = result.get('items', [])
        if not search_items:
            print("Web search returned no results.")
            return [] # Return empty list, not an error message for the AI

        for i, item in enumerate(search_items):
            title = item.get('title', 'No Title')
            snippet = item.get('snippet', 'No Snippet Available')
            # link = item.get('link') # You could include the link if desired
            formatted_result = f"{i+1}. {title}: {snippet.replace(chr(10), ' ').replace(chr(13), ' ')}" # Remove newlines from snippet
            search_snippets.append(formatted_result)
            print(f"  - Result {i+1}: {title}")

        return search_snippets

    except HttpError as e:
        print(f"ERROR during Google Custom Search API call: {e}")
        # Provide a generic error for the AI context, don't expose detailed API errors
        return [f"[System Error: Web search failed. Reason: {e.resp.status} {e.resp.reason}]"]
    except Exception as e:
        print(f"An unexpected error occurred during web search: {e}")
        return ["[System Error: An unexpected error occurred during web search.]"]
