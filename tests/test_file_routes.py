import pytest
import json
import io
import os
import base64
from app.models import File, default_utcnow # Correct model name, import default_utcnow
from app import db as flask_db # Alias to avoid conflict

# Helper to create a file record in DB for tests that need an existing file
def create_db_file(filename="test.txt", content_type="text/plain", size=100, content_blob=b"test content", summary=None):
    new_file = File(
        filename=filename,
        content=content_blob,
        mimetype=content_type,
        filesize=size,
        summary=summary
    )
    flask_db.session.add(new_file)
    flask_db.session.commit()
    return new_file

def test_get_files_empty(client, db):
    """Test getting files when none exist."""
    response = client.get("/api/files")
    assert response.status_code == 200
    assert response.get_json() == []

def test_get_files_with_data(client, db):
    """Test getting files after creating some."""
    file1 = create_db_file(filename="file1.txt", content_blob=b"content1")
    file2 = create_db_file(filename="file2.pdf", content_type="application/pdf", content_blob=b"pdf content")

    response = client.get("/api/files")
    assert response.status_code == 200
    data = response.get_json()
    assert len(data) == 2
    filenames_in_response = {f["filename"] for f in data}
    assert "file1.txt" in filenames_in_response
    assert "file2.pdf" in filenames_in_response
    for f_data in data:
        assert "id" in f_data
        assert "filename" in f_data
        assert "mimetype" in f_data
        assert "filesize" in f_data
        assert "uploaded_at" in f_data
        assert "has_summary" in f_data


# --- POST /api/files (File Upload) Tests ---

def test_upload_single_file_success(client, db, mocker, app):
    """Test successful single file upload."""
    # Mock the actual database save function to control its behavior and return value
    # The route calls database_module.save_file_record_to_db
    mock_save_file = mocker.patch("app.database.save_file_record_to_db")
    
    # Simulate the File object that would be created and returned by save_file_record_to_db
    # before commit (so ID might be None initially, but gets populated after commit)
    # For this test, we'll assume it's populated after commit for simplicity in checking response.
    # The route itself handles the commit and then re-fetches.
    
    # The route calls db.session.commit() itself.
    # After commit, the file_obj in the route will have an ID.
    # We need to ensure our mock reflects that an ID is available for the response.
    
    # Let's refine the mocking strategy:
    # 1. Mock save_file_record_to_db to return a File instance (without ID yet, as commit is deferred)
    # 2. Mock db.session.commit()
    # 3. Mock File.query.get() or similar if the route re-fetches (it does not, it uses the list of objects)

    # The route collects File objects from save_file_record_to_db (with commit=False)
    # then commits, then builds the response from those objects.
    # So, the File objects must have IDs by the time the response is built.
    # This means the `save_file_record_to_db` mock should return an object that will get an ID.
    # Or, more simply, mock `save_file_record_to_db` to return an object that *already* has an ID,
    # as if the commit within the loop (if it were there) or the final commit worked.

    # Let's mock save_file_record_to_db to return a File instance that will have its ID set
    # by SQLAlchemy's identity map after a (mocked) commit.
    # For simplicity in testing the route's response construction, let's make the mock return
    # a File object that looks like it has been committed.
    
    mock_file_obj = File(id=1, filename="upload.txt", mimetype="text/plain", filesize=12, content=b"test content", uploaded_at=default_utcnow())
    mock_save_file.return_value = mock_file_obj
    mocker.patch.object(flask_db.session, 'commit') # Mock the commit

    file_content = b"test content"
    data = {"file": (io.BytesIO(file_content), "upload.txt")}
    
    response = client.post("/api/files", data=data, content_type="multipart/form-data")

    assert response.status_code == 201
    json_data = response.get_json()
    assert "uploaded_files" in json_data
    assert len(json_data["uploaded_files"]) == 1
    uploaded_file_info = json_data["uploaded_files"][0]
    assert uploaded_file_info["filename"] == "upload.txt"
    assert uploaded_file_info["id"] == 1 # Assuming mock_file_obj had ID 1
    
    mock_save_file.assert_called_once_with("upload.txt", file_content, "text/plain", 12, commit=False)
    flask_db.session.commit.assert_called_once()


def test_upload_no_file_part(client, db):
    response = client.post("/api/files", data={}, content_type="multipart/form-data")
    assert response.status_code == 400
    assert response.get_json()["error"] == "No file part in the request"

def test_upload_empty_filename(client, db):
    data = {"file": (io.BytesIO(b"content"), "")}
    response = client.post("/api/files", data=data, content_type="multipart/form-data")
    # The route continues if filename is empty, but save_file_record_to_db might handle it
    # Based on current route logic, it logs "Skipping file ... Empty filename" and continues.
    # If no other files, it might return an error or empty success.
    # Current route returns 400 "No valid files processed..." if all files are skipped.
    assert response.status_code == 400 
    assert "No valid files processed" in response.get_json()["error"]


def test_upload_disallowed_extension(client, db, app):
    data = {"file": (io.BytesIO(b"content"), "test.exe")}
    response = client.post("/api/files", data=data, content_type="multipart/form-data")
    assert response.status_code == 400 # Because all files failed
    json_data = response.get_json()
    assert "error" in json_data
    assert "File type not allowed for 'test.exe'" in json_data["error"]

def test_upload_file_too_large(client, db, app):
    # Configure a small max size for this test via app config if possible,
    # or ensure test config is used. TestConfig already sets MAX_FILE_SIZE_BYTES.
    large_content = b"a" * (app.config["MAX_FILE_SIZE_BYTES"] + 1)
    data = {"file": (io.BytesIO(large_content), "large.txt")}
    response = client.post("/api/files", data=data, content_type="multipart/form-data")
    assert response.status_code == 400
    json_data = response.get_json()
    assert "error" in json_data
    assert f"File 'large.txt' ({len(large_content)} bytes) exceeds size limit" in json_data["error"]

# --- POST /api/files/from_url Tests ---

def test_add_file_from_url_success(client, db, mocker):
    mock_fetch_content = mocker.patch("app.routes.file_routes.web_search.fetch_web_content")
    mock_fetch_content.return_value = {
        "type": "html", 
        "content": "<html><body>Test</body></html>", 
        "url": "http://example.com", 
        "filename": "example_com.html"
    }
    
    # Mock save_file_record_to_db to return a file ID
    mock_save_db = mocker.patch("app.database.save_file_record_to_db", return_value=1)
    # Mock File.query.get to return a File object
    mock_file_instance = File(id=1, filename="example_com.html", mimetype="text/html", filesize=29, content=b"", uploaded_at=default_utcnow())
    mocker.patch.object(File.query, "get", return_value=mock_file_instance)

    response = client.post("/api/files/from_url", json={"url": "http://example.com"})
    
    assert response.status_code == 201
    data = response.get_json()
    assert data["filename"] == "example_com.html"
    assert data["id"] == 1
    mock_fetch_content.assert_called_once_with("http://example.com")
    mock_save_db.assert_called_once()

def test_add_file_from_url_no_url(client, db):
    response = client.post("/api/files/from_url", json={})
    assert response.status_code == 400
    assert response.get_json()["error"] == "No URL provided"

def test_add_file_from_url_invalid_url(client, db):
    response = client.post("/api/files/from_url", json={"url": "not_a_url"})
    assert response.status_code == 400
    assert response.get_json()["error"] == "Invalid URL format"

def test_add_file_from_url_fetch_error(client, db, mocker):
    mock_fetch_content = mocker.patch("app.routes.file_routes.web_search.fetch_web_content")
    mock_fetch_content.return_value = {"type": "error", "content": "Fetch failed"}
    
    response = client.post("/api/files/from_url", json={"url": "http://example.com/fail"})
    assert response.status_code == 500
    assert "Failed to fetch content from URL: Fetch failed" in response.get_json()["error"]

# --- GET /api/file_content/<file_id> Tests ---

def test_get_file_content_text(client, db):
    file_content_str = "Hello, this is test text."
    file_obj = create_db_file(filename="text_file.txt", content_blob=file_content_str.encode('utf-8'), size=len(file_content_str.encode('utf-8')))
    
    response = client.get(f"/api/file_content/{file_obj.id}")
    assert response.status_code == 200
    data = response.get_json()
    assert data["id"] == file_obj.id
    assert data["filename"] == "text_file.txt"
    assert data["content"] == file_content_str
    assert data["mimetype"] == "text/plain"
    assert data["is_base64"] is False

def test_get_file_content_binary_base64(client, db):
    # Simulate binary content (e.g., a small PNG)
    # A minimal valid PNG (1x1 transparent pixel)
    png_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
    binary_content = base64.b64decode(png_b64)
    file_obj = create_db_file(filename="image.png", content_type="image/png", content_blob=binary_content, size=len(binary_content))

    response = client.get(f"/api/file_content/{file_obj.id}")
    assert response.status_code == 200
    data = response.get_json()
    assert data["id"] == file_obj.id
    assert data["filename"] == "image.png"
    assert data["content"] == png_b64 # Expect base64 encoded string
    assert data["mimetype"] == "image/png"
    assert data["is_base64"] is True

def test_get_file_content_not_found(client, db):
    response = client.get("/api/file_content/99999")
    assert response.status_code == 404
    assert response.get_json()["error"] == "File not found"

# --- File Summary Tests ---
def test_get_file_summary_exists(client, db):
    file_obj = create_db_file(summary="Existing summary here.")
    response = client.get(f"/api/files/{file_obj.id}/summary")
    assert response.status_code == 200
    assert response.get_json()["summary"] == "Existing summary here."

def test_get_file_summary_generate_new(client, db, mocker):
    file_obj = create_db_file(summary=None) # No summary initially
    mock_ai_summary = mocker.patch("app.ai_services.get_or_generate_summary", return_value="AI Generated Summary")
    
    response = client.get(f"/api/files/{file_obj.id}/summary")
    assert response.status_code == 200
    assert response.get_json()["summary"] == "AI Generated Summary"
    mock_ai_summary.assert_called_once_with(file_obj.id)

def test_update_file_summary(client, db, mocker):
    file_obj = create_db_file()
    mock_save_summary = mocker.patch("app.database.save_summary_in_db", return_value=True)
    
    new_summary_text = "This is an updated summary."
    response = client.put(f"/api/files/{file_obj.id}/summary", json={"summary": new_summary_text})
    
    assert response.status_code == 200
    assert response.get_json()["message"] == "Summary updated successfully."
    mock_save_summary.assert_called_once_with(file_obj.id, new_summary_text)

# --- DELETE /api/files/<file_id> Test (already partially covered by test_delete_file) ---
# The existing test_delete_file covers the success and basic not_found cases.
# The route logic for delete is:
# 1. Call database_module.delete_file_record_from_db(file_id)
# 2. If True, return success.
# 3. If False, call database_module.get_file_details_from_db(file_id)
# 4. If details not found, return 404.
# 5. Else (exists but delete failed), return 500.

def test_delete_file_actually_deletes_from_db(client, db):
    """Ensure the file is actually removed from the database."""
    file_obj = create_db_file(filename="delete_me_fully.txt", content_blob=b"delete content")
    file_id = file_obj.id

    # Ensure it exists
    assert File.query.get(file_id) is not None

    response = client.delete(f"/api/files/{file_id}")
    assert response.status_code == 200
    assert response.get_json()["message"] == f"File ID {file_id} deleted successfully."
    
    # Verify it's gone
    assert File.query.get(file_id) is None

def test_delete_file_fails_in_db_but_file_exists(client, db, mocker):
    """Test scenario where DB delete fails but file was initially found."""
    file_obj = create_db_file(filename="fail_delete.txt")
    file_id = file_obj.id

    mocker.patch("app.database.delete_file_record_from_db", return_value=False)
    # Ensure get_file_details_from_db still finds it for the route's secondary check
    mocker.patch("app.database.get_file_details_from_db", return_value={"id": file_id, "filename": "fail_delete.txt"})

    response = client.delete(f"/api/files/{file_id}")
    assert response.status_code == 500
    assert response.get_json()["error"] == f"Failed to delete file ID {file_id}."
