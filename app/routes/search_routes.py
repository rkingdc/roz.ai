from flask import Blueprint, request, jsonify, current_app
from app.database import search_notes # Assuming search_notes is the correct function name

# Define a Blueprint for search-related routes
# We'll prefix routes from this blueprint with /api (similar to other API routes)
# The actual route will be defined on the blueprint itself.
# The registration of this blueprint in app/__init__.py will handle the /api prefix.
# For now, we define the specific path for note search.
bp = Blueprint('search', __name__, url_prefix='/api/search')

@bp.route('/notes', methods=['GET'])
def handle_search_notes():
    """
    Searches notes based on a query term.
    Expects a 'q' query parameter.
    Example: /api/search/notes?q=mysearchterm
    """
    search_term = request.args.get('q', None)

    if not search_term or len(search_term.strip()) == 0:
        return jsonify([]), 200 # Return empty list if no search term or only whitespace

    try:
        # Assuming search_notes function takes the search term and optionally a limit.
        # We'll use a default limit or let the function handle its default.
        # If search_notes requires other parameters like user_id,
        # those would need to be handled here (e.g., from session or JWT).
        # For now, assuming it primarily needs the search_term.
        results = search_notes(search_term=search_term)
        
        # The search_notes function is expected to return a list of dictionaries.
        # Each dictionary should contain at least 'id', 'name', 'snippet', 'last_saved_at'.
        # Example: [{'id': 1, 'name': 'My Note', 'snippet': '...found term...', 'last_saved_at': '2023-01-01T10:00:00Z'}]
        
        return jsonify(results), 200
    except Exception as e:
        current_app.logger.error(f"Error during note search for term '{search_term}': {e}", exc_info=True)
        return jsonify({"error": "An error occurred while searching notes."}), 500

# To make this blueprint active, it needs to be registered in your main app factory (create_app function in app/__init__.py)
# Example in app/__init__.py:
#
# from app.routes import search_routes
# ...
# def create_app(test_config=None):
#     ...
#     app.register_blueprint(search_routes.bp)
#     ...
#     return app
