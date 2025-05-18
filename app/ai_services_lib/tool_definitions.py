from google.genai.types import (
    Tool,
    FunctionDeclaration,
    Schema,
    Type,
)

# --- Tool Definitions ---
# Web Search Tool
WEB_SEARCH_TOOL = Tool(
    function_declarations=[
        FunctionDeclaration(
            name="web_search",
            description=(
                "Performs a web search using a search engine based on a user query. "
                "Returns a list of search results, each including a title, link, and snippet. "
                "Use this tool to find relevant web pages before deciding to scrape specific URLs."
            ),
            parameters=Schema(
                type=Type.OBJECT,
                properties={
                    "query": Schema(type=Type.STRING, description="The search query")
                },
                required=["query"],
            ),
        )
    ]
)

# Web Scrape Tool
WEB_SCRAPE_TOOL = Tool(
    function_declarations=[
        FunctionDeclaration(
            name="scrape_url",
            description=(
                "Fetches and extracts content from a specific URL. "
                "Can handle HTML (extracts main textual content) and PDF documents "
                "(returns raw PDF data which will then be transcribed to text by the system). "
                "Use this tool after identifying a promising URL from web_search results."
            ),
            parameters=Schema(
                type=Type.OBJECT,
                properties={
                    "url": Schema(type=Type.STRING, description="The URL to scrape")
                },
                required=["url"],
            ),
        )
    ]
)
# --- End Tool Definitions ---
