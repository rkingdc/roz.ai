import pytest
import json
from app.models import Chat # To verify database entries directly if needed

# Helper function to create a chat directly for setup in some tests
def create_chat_directly(client):
    response = client.post("/api/chat")
    assert response.status_code == 201
    return response.get_json()["id"]

def test_create_new_chat(client, db):
    """Test creating a new chat."""
    response = client.post("/api/chat")
    assert response.status_code == 201
    data = response.get_json()
    assert "id" in data
    assert "name" in data # Default name is usually assigned
    assert "model_name" in data # Default model is usually assigned

    # Verify in DB (optional, but good for confidence)
    chat_in_db = Chat.query.get(data["id"])
    assert chat_in_db is not None
    assert chat_in_db.id == data["id"]

def test_get_saved_chats_empty(client, db):
    """Test getting saved chats when none exist."""
    response = client.get("/api/chats")
    assert response.status_code == 200
    assert response.get_json() == []

def test_get_saved_chats_with_data(client, db):
    """Test getting saved chats after creating some."""
    chat_id1 = create_chat_directly(client)
    chat_id2 = create_chat_directly(client)

    response = client.get("/api/chats")
    assert response.status_code == 200
    data = response.get_json()
    assert len(data) == 2
    chat_ids_in_response = {chat["id"] for chat in data}
    assert chat_id1 in chat_ids_in_response
    assert chat_id2 in chat_ids_in_response

def test_get_chat_details_and_history(client, db):
    """Test getting details and history for a specific chat."""
    chat_id = create_chat_directly(client)
    # You might want to add some messages to this chat via a (yet to be tested) message endpoint
    # or directly to the DB for a more thorough history test.
    # For now, history will be empty.

    response = client.get(f"/api/chat/{chat_id}")
    assert response.status_code == 200
    data = response.get_json()
    assert "details" in data
    assert data["details"]["id"] == chat_id
    assert "history" in data
    assert data["history"] == [] # Assuming no messages added yet

def test_get_chat_not_found(client, db):
    """Test getting a non-existent chat."""
    response = client.get("/api/chat/99999") # Assuming 99999 doesn't exist
    assert response.status_code == 404
    assert "error" in response.get_json()
    assert response.get_json()["error"] == "Chat not found"

def test_delete_chat(client, db):
    """Test deleting an existing chat."""
    chat_id = create_chat_directly(client)

    # Verify it exists before delete
    assert Chat.query.get(chat_id) is not None

    response = client.delete(f"/api/chat/{chat_id}")
    assert response.status_code == 200
    assert response.get_json()["message"] == f"Chat {chat_id} deleted."

    # Verify it's gone from DB
    assert Chat.query.get(chat_id) is None

def test_delete_chat_not_found(client, db):
    """Test deleting a non-existent chat."""
    response = client.delete("/api/chat/99999")
    assert response.status_code == 404
    assert response.get_json()["error"] == "Chat 99999 not found"

def test_save_chat_name(client, db, app):
    """Test updating the name of a chat."""
    chat_id = create_chat_directly(client)
    new_name = "My Awesome Chat"

    response = client.put(
        f"/api/chat/{chat_id}/name",
        data=json.dumps({"name": new_name}),
        content_type="application/json",
    )
    assert response.status_code == 200
    assert response.get_json()["message"] == "Chat name updated successfully."

    # Verify in DB
    chat_in_db = Chat.query.get(chat_id)
    assert chat_in_db.name == new_name

def test_save_chat_name_empty(client, db):
    """Test updating chat name with empty string (should default)."""
    chat_id = create_chat_directly(client)
    response = client.put(
        f"/api/chat/{chat_id}/name",
        data=json.dumps({"name": ""}),
        content_type="application/json",
    )
    assert response.status_code == 200
    chat_in_db = Chat.query.get(chat_id)
    assert chat_in_db.name == "New Chat" # As per route logic

def test_save_chat_name_chat_not_found(client, db):
    """Test updating name for a non-existent chat."""
    # The current route implementation returns 500 if db.save_chat_name_in_db fails,
    # which would happen if the chat_id doesn't exist.
    # A 404 might be more appropriate, but we test current behavior.
    response = client.put(
        "/api/chat/99999/name",
        data=json.dumps({"name": "Test"}),
        content_type="application/json",
    )
    assert response.status_code == 500 # Based on current route logic
    assert "error" in response.get_json()
    assert response.get_json()["error"] == "Failed to update chat name"


def test_save_chat_model(client, db, app):
    """Test updating the model of a chat."""
    chat_id = create_chat_directly(client)
    new_model = app.config["AVAILABLE_MODELS"][0] # Use a valid model from config

    response = client.put(
        f"/api/chat/{chat_id}/model",
        data=json.dumps({"model_name": new_model}),
        content_type="application/json",
    )
    assert response.status_code == 200
    assert response.get_json()["message"] == f"Chat model updated to {new_model}."

    # Verify in DB
    chat_in_db = Chat.query.get(chat_id)
    assert chat_in_db.model_name == new_model

def test_save_chat_model_no_model_name(client, db):
    """Test updating chat model without providing model_name."""
    chat_id = create_chat_directly(client)
    response = client.put(
        f"/api/chat/{chat_id}/model",
        data=json.dumps({}), # Missing model_name
        content_type="application/json",
    )
    assert response.status_code == 400
    assert response.get_json()["error"] == "Model name not provided"

def test_save_chat_model_unknown_model(client, db, app):
    """Test updating chat model with an unknown model name."""
    # The route currently logs a warning but proceeds with the update.
    # If strict validation were added to return 400, this test would change.
    chat_id = create_chat_directly(client)
    unknown_model = "super_advanced_unknown_model_v9000"

    response = client.put(
        f"/api/chat/{chat_id}/model",
        data=json.dumps({"model_name": unknown_model}),
        content_type="application/json",
    )
    assert response.status_code == 200 # Current behavior
    # Verify in DB
    chat_in_db = Chat.query.get(chat_id)
    assert chat_in_db.model_name == unknown_model

def test_save_chat_model_chat_not_found(client, db):
    """Test updating model for a non-existent chat."""
    # Similar to save_chat_name, current route returns 500 if db.update_chat_model fails.
    response = client.put(
        "/api/chat/99999/model",
        data=json.dumps({"model_name": "test_model_1"}),
        content_type="application/json",
    )
    assert response.status_code == 500 # Based on current route logic
    assert "error" in response.get_json()
    assert response.get_json()["error"] == "Failed to update chat model"
