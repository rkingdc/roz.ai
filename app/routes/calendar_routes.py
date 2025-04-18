# app/routes/calendar_routes.py
from flask import Blueprint, jsonify, current_app, session, redirect, url_for, request
from ..plugins import google_calendar # Use relative import for plugin module

# Create Blueprint for calendar API, using '/api/calendar' prefix
bp = Blueprint('calendar_api', __name__, url_prefix='/api/calendar')

# NOTE: The '/connect' and '/oauth2callback' routes needed for a full
#       web-based OAuth flow are NOT implemented in this simplified version.
#       We assume 'token.json' already exists and is valid/refreshable.

@bp.route('/events', methods=['GET'])
def get_calendar_events():
    """API endpoint to fetch upcoming calendar events."""
    print("Received request for /api/calendar/events")
    service = google_calendar.get_calendar_service()

    if not service:
        # If service failed (e.g., token invalid, needs re-auth)
        # In a full app, might redirect to connect route or return specific error
        print("Failed to get calendar service (likely auth issue).")
        return jsonify({"error": "Could not connect to Google Calendar. Please ensure credentials/token are valid."}), 503 # Service Unavailable

    # Fetch events for the next 3 months (default)
    events_text = google_calendar.fetch_upcoming_events(service, months=3)

    # Check if the returned text indicates an error occurred during fetch
    if events_text.startswith("[Error"):
        # Return error status if fetching failed
        return jsonify({"error": events_text}), 500 # Internal Server Error

    return jsonify({"events": events_text})

