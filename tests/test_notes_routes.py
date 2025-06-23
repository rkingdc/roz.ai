import pytest
import json
from app.models import Note, NoteHistory
from app import db as flask_db # Use an alias to avoid conflict with pytest 'db' fixture

# Helper function to create a note directly for setup in some tests
def create_note_directly(client):
    response = client.post("/api/notes")
    assert response.status_code == 201
    data = response.get_json()
    assert "id" in data
    return data # Return the full note dict

def test_get_all_notes_empty(client, db):
    """Test getting all notes when none exist."""
    response = client.get("/api/notes")
    assert response.status_code == 200
    assert response.get_json() == []

def test_create_new_note(client, db):
    """Test creating a new note."""
    response = client.post("/api/notes")
    assert response.status_code == 201
    data = response.get_json()
    assert "id" in data
    assert "name" in data and data["name"] is not None
    assert "content" in data and data["content"] == ""
    assert "last_saved_at" in data # Check for the key returned by get_note_from_db
    # created_at is not part of the JSON response from get_note_from_db

    # Verify in DB
    note_in_db = Note.query.get(data["id"])
    assert note_in_db is not None
    assert note_in_db.id == data["id"]
    assert note_in_db.name == data["name"]
    assert note_in_db.content == ""
    assert note_in_db.created_at is not None # Verify created_at exists on the DB model
    assert note_in_db.last_saved_at is not None # Verify last_saved_at exists on the DB model

    # Verify NO initial history entry upon creation via POST /api/notes
    history_entry_count = NoteHistory.query.filter_by(note_id=data["id"]).count()
    assert history_entry_count == 0

def test_get_all_notes_with_data(client, db):
    """Test getting all notes after creating some."""
    note1_data = create_note_directly(client)
    note2_data = create_note_directly(client)

    response = client.get("/api/notes")
    assert response.status_code == 200
    data = response.get_json()
    assert len(data) == 2
    note_ids_in_response = {note["id"] for note in data}
    assert note1_data["id"] in note_ids_in_response
    assert note2_data["id"] in note_ids_in_response

def test_get_note(client, db):
    """Test getting a specific note."""
    created_note_data = create_note_directly(client)
    note_id = created_note_data["id"]

    response = client.get(f"/api/note/{note_id}")
    assert response.status_code == 200
    data = response.get_json()
    assert data["id"] == note_id
    assert data["name"] == created_note_data["name"]
    assert data["content"] == created_note_data["content"]

def test_get_note_not_found(client, db):
    """Test getting a non-existent note."""
    response = client.get("/api/note/99999")
    assert response.status_code == 404
    assert response.get_json()["error"] == "Note not found"

def test_save_note_first_time_creates_initial_history(client, db, mocker):
    """Test that the first save (PUT) on a new note creates an initial history entry."""
    created_note_data = create_note_directly(client) # Note created, no history yet
    note_id = created_note_data["id"]

    new_name = "First Save Name"
    new_content = "This is the first saved content."

    # Mock AI service as save_note_to_db might call it, though for initial it shouldn't
    mock_ai = mocker.patch("app.ai_services.generate_note_diff_summary")

    response = client.put( # This is the first save operation that will trigger history
        f"/api/note/{note_id}",
        data=json.dumps({"name": new_name, "content": new_content}),
        content_type="application/json",
    )
    assert response.status_code == 200
    assert response.get_json()["message"] == "Note saved successfully"

    mock_ai.assert_not_called() # AI should not be called for the very first history entry

    # Verify in DB
    note_in_db = Note.query.get(note_id)
    assert note_in_db.name == new_name
    assert note_in_db.content == new_content

    # Verify new history entry (this is the *first* history entry)
    history_entries = NoteHistory.query.filter_by(note_id=note_id).order_by(NoteHistory.saved_at.asc()).all()
    assert len(history_entries) == 1
    first_history_entry = history_entries[0]
    assert first_history_entry.name == new_name
    assert first_history_entry.content == new_content
    assert first_history_entry.note_diff == "[Initial version]"

def test_save_note_subsequent_update(client, db, mocker):
    """Test a subsequent update to an existing note."""
    created_note_data = create_note_directly(client)
    note_id = created_note_data["id"]

    # First save
    client.put(
        f"/api/note/{note_id}",
        data=json.dumps({"name": "Name V1", "content": "Content V1"}),
        content_type="application/json",
    )

    # Second save (the one we're testing)
    new_name_v2 = "Updated Note Name V2"
    new_content_v2 = "This is the updated content V2."
    
    mock_ai = mocker.patch("app.ai_services.generate_note_diff_summary", return_value="AI summary for V2")

    response = client.put(
        f"/api/note/{note_id}",
        data=json.dumps({"name": new_name_v2, "content": new_content_v2}),
        content_type="application/json",
    )
    assert response.status_code == 200

    mock_ai.assert_called_once_with("Content V1", new_content_v2)

    note_in_db = Note.query.get(note_id)
    assert note_in_db.name == new_name_v2
    assert note_in_db.content == new_content_v2

    history_entries = NoteHistory.query.filter_by(note_id=note_id).order_by(NoteHistory.saved_at.asc()).all()
    assert len(history_entries) == 2
    assert history_entries[1].name == new_name_v2
    assert history_entries[1].content == new_content_v2
    assert history_entries[1].note_diff == "AI summary for V2"


def test_save_note_missing_data(client, db):
    """Test updating a note with missing 'name' or 'content'."""
    created_note_data = create_note_directly(client)
    note_id = created_note_data["id"]

    response_missing_content = client.put(
        f"/api/note/{note_id}",
        data=json.dumps({"name": "Just Name"}),
        content_type="application/json",
    )
    assert response_missing_content.status_code == 400
    assert response_missing_content.get_json()["error"] == "Missing 'name' or 'content' in request body"

def test_save_note_not_found(client, db):
    """Test updating a non-existent note."""
    response = client.put(
        "/api/note/99999",
        data=json.dumps({"name": "Test", "content": "Test content"}),
        content_type="application/json",
    )
    assert response.status_code == 404
    assert response.get_json()["error"] == "Note not found"

def test_delete_note(client, db):
    """Test deleting an existing note."""
    created_note_data = create_note_directly(client)
    note_id = created_note_data["id"]

    # Add some history by saving the note once
    client.put(
        f"/api/note/{note_id}",
        data=json.dumps({"name": "Note to delete", "content": "Content to delete"}),
        content_type="application/json",
    )
    assert Note.query.get(note_id) is not None
    assert NoteHistory.query.filter_by(note_id=note_id).count() > 0

    response = client.delete(f"/api/note/{note_id}")
    assert response.status_code == 200
    assert response.get_json()["message"] == "Note deleted successfully"

    assert Note.query.get(note_id) is None
    assert NoteHistory.query.filter_by(note_id=note_id).count() == 0

def test_delete_note_not_found(client, db):
    """Test deleting a non-existent note."""
    non_existent_note_id = 99999
    assert Note.query.get(non_existent_note_id) is None
    response = client.delete(f"/api/note/{non_existent_note_id}")
    assert response.status_code == 404
    assert response.get_json()["error"] == "Note not found"

def test_get_note_history(client, db):
    """Test getting history for a specific note."""
    created_note_data = create_note_directly(client)
    note_id = created_note_data["id"]

    # First update (creates the first history entry)
    client.put(
        f"/api/note/{note_id}",
        data=json.dumps({"name": "Updated Name 1", "content": "Updated Content 1"}),
        content_type="application/json",
    )
    # Second update (creates the second history entry)
    client.put(
        f"/api/note/{note_id}",
        data=json.dumps({"name": "Updated Name 2", "content": "Updated Content 2"}),
        content_type="application/json",
    )

    response = client.get(f"/api/notes/{note_id}/history")
    assert response.status_code == 200
    history_data = response.get_json() # Ordered desc by saved_at by the API
    assert isinstance(history_data, list)
    assert len(history_data) == 2
    
    latest_history = history_data[0]
    older_history = history_data[1]

    assert latest_history["name"] == "Updated Name 2"
    assert latest_history["content"] == "Updated Content 2"
    assert latest_history["note_diff"] is not None # Should be AI summary or marker

    assert older_history["name"] == "Updated Name 1"
    assert older_history["content"] == "Updated Content 1"
    assert older_history["note_diff"] == "[Initial version]"

def test_get_note_history_note_not_found(client, db):
    """Test getting history for a non-existent note."""
    response = client.get("/api/notes/99999/history")
    assert response.status_code == 404
    assert response.get_json()["error"] == "Note not found"

# --- Helpers for on-demand summary tests ---
def get_history_id_for_latest_entry(note_id):
    latest_history = NoteHistory.query.filter_by(note_id=note_id).order_by(NoteHistory.saved_at.desc()).first()
    assert latest_history is not None, f"No history found for note_id {note_id}"
    return latest_history.id

def get_history_id_for_initial_entry(note_id): # This will be the first entry after the first PUT
    initial_history = NoteHistory.query.filter_by(note_id=note_id).order_by(NoteHistory.saved_at.asc()).first()
    assert initial_history is not None, f"No initial history found for note_id {note_id}"
    return initial_history.id

# --- Tests for on-demand summary generation ---

def test_generate_history_item_summary_initial_on_demand(client, db, mocker):
    created_note_data = create_note_directly(client)
    note_id = created_note_data["id"]
    client.put(
        f"/api/note/{note_id}",
        data=json.dumps({"name": "Initial Name", "content": "Initial Content"}),
        content_type="application/json",
    )
    history_id = get_history_id_for_initial_entry(note_id)
    
    initial_hist_entry_obj = NoteHistory.query.get(history_id)
    assert initial_hist_entry_obj.note_diff == "[Initial version]" # Set by save_note_to_db

    mock_ai_summary = mocker.patch("app.ai_services.generate_note_diff_summary")

    response = client.post(f"/api/notes/{note_id}/history/{history_id}/generate_summary")
    assert response.status_code == 200
    data = response.get_json()
    assert data["summary"] == "[Initial version]" # On-demand logic re-confirms

    mock_ai_summary.assert_not_called()
    history_entry = NoteHistory.query.get(history_id)
    assert history_entry.note_diff == "[Initial version]"

def test_generate_history_item_summary_content_change_on_demand(client, db, mocker):
    created_note_data = create_note_directly(client)
    note_id = created_note_data["id"]
    first_put_content = "Content for first history"
    client.put(
        f"/api/note/{note_id}",
        data=json.dumps({"name": "Name V1", "content": first_put_content}),
        content_type="application/json",
    )
    second_put_content = "New Content Here for V2"
    # Mock AI during the save that creates V2 history, so its note_diff is set
    with mocker.patch("app.ai_services.generate_note_diff_summary", return_value="Summary from save_note_to_db"):
        client.put(
            f"/api/note/{note_id}",
            data=json.dumps({"name": "Name V2", "content": second_put_content}),
            content_type="application/json",
        )
    history_id_v2 = get_history_id_for_latest_entry(note_id)

    # Now, clear V2's note_diff to simulate it being "pending" for on-demand generation
    hist_v2_obj = NoteHistory.query.get(history_id_v2)
    hist_v2_obj.note_diff = None 
    flask_db.session.commit()

    mock_ondemand_ai = mocker.patch("app.ai_services.generate_note_diff_summary", return_value="On-demand AI summary for V2")

    response = client.post(f"/api/notes/{note_id}/history/{history_id_v2}/generate_summary")
    assert response.status_code == 200
    data = response.get_json()
    assert data["summary"] == "On-demand AI summary for V2"
    mock_ondemand_ai.assert_called_once_with(first_put_content, second_put_content)

    history_entry = NoteHistory.query.get(history_id_v2)
    assert history_entry.note_diff == "On-demand AI summary for V2"

def test_generate_history_item_summary_metadata_change_on_demand(client, db, mocker):
    created_note_data = create_note_directly(client)
    note_id = created_note_data["id"]
    content_c1 = "Consistent Content"
    client.put(
        f"/api/note/{note_id}",
        data=json.dumps({"name": "Name V1", "content": content_c1}),
        content_type="application/json",
    )
    client.put(
        f"/api/note/{note_id}",
        data=json.dumps({"name": "Name V2 - Metadata Change", "content": content_c1}),
        content_type="application/json",
    )
    history_id_metadata_change = get_history_id_for_latest_entry(note_id)
    
    hist_meta_obj = NoteHistory.query.get(history_id_metadata_change)
    assert hist_meta_obj.note_diff == "[Metadata change only]" # Set by save_note_to_db

    mock_ai_summary = mocker.patch("app.ai_services.generate_note_diff_summary")
    response = client.post(f"/api/notes/{note_id}/history/{history_id_metadata_change}/generate_summary")
    assert response.status_code == 200
    data = response.get_json()
    assert data["summary"] == "[Metadata change only]"
    mock_ai_summary.assert_not_called()

def test_generate_history_item_summary_ai_failure_on_demand(client, db, mocker):
    created_note_data = create_note_directly(client)
    note_id = created_note_data["id"]
    content_c1 = "Content for V1"
    client.put(
        f"/api/note/{note_id}",
        data=json.dumps({"name": "Name V1", "content": content_c1}),
        content_type="application/json",
    )
    content_c2_fail = "Content that will cause AI fail"
    client.put(
        f"/api/note/{note_id}",
        data=json.dumps({"name": "Name V2", "content": content_c2_fail}),
        content_type="application/json",
    )
    history_id_fail = get_history_id_for_latest_entry(note_id)
    
    hist_fail_obj = NoteHistory.query.get(history_id_fail)
    hist_fail_obj.note_diff = None # Simulate pending
    flask_db.session.commit()

    mock_ai_summary = mocker.patch("app.ai_services.generate_note_diff_summary", return_value="[AI Error] Failed")
    response = client.post(f"/api/notes/{note_id}/history/{history_id_fail}/generate_summary")
    assert response.status_code == 200
    data = response.get_json()
    assert data["summary"] == "[AI summary generation failed]"
    mock_ai_summary.assert_called_once_with(content_c1, content_c2_fail)
    history_entry = NoteHistory.query.get(history_id_fail)
    assert history_entry.note_diff == "[AI summary generation failed]"

def test_generate_history_item_summary_already_exists_on_demand(client, db, mocker):
    created_note_data = create_note_directly(client)
    note_id = created_note_data["id"]
    client.put(
        f"/api/note/{note_id}",
        data=json.dumps({"name": "Name V1", "content": "Content V1"}),
        content_type="application/json",
    )
    existing_summary_text = "This summary was generated by save_note_to_db"
    with mocker.patch("app.ai_services.generate_note_diff_summary", return_value=existing_summary_text):
        client.put(
            f"/api/note/{note_id}",
            data=json.dumps({"name": "Name V2", "content": "Content V2 that gets summarized"}),
            content_type="application/json",
        )
    history_id_exists = get_history_id_for_latest_entry(note_id)
    
    history_entry_check = NoteHistory.query.get(history_id_exists)
    assert history_entry_check.note_diff == existing_summary_text

    mock_ondemand_ai = mocker.patch("app.ai_services.generate_note_diff_summary")
    response = client.post(f"/api/notes/{note_id}/history/{history_id_exists}/generate_summary")
    assert response.status_code == 200
    data = response.get_json()
    assert data["summary"] == existing_summary_text
    assert data.get("message") == "Summary already existed."
    mock_ondemand_ai.assert_not_called()

def test_generate_history_item_summary_history_not_found(client, db):
    created_note_data = create_note_directly(client)
    note_id = created_note_data["id"]
    response = client.post(f"/api/notes/{note_id}/history/99999/generate_summary")
    assert response.status_code == 404
    assert response.get_json()["error"] == "History entry not found"

def test_generate_history_item_summary_note_not_found_for_history(client, db):
    response = client.post("/api/notes/99999/history/12345/generate_summary")
    assert response.status_code == 404
    assert response.get_json()["error"] == "History entry not found"
