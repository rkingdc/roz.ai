def get_uploaded_files_from_db():
    """Retrieves metadata for all uploaded files (excluding BLOB)."""
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute(" SELECT id, filename, mimetype, filesize, uploaded_at, (summary IS NOT NULL) as has_summary FROM files ORDER BY uploaded_at DESC ") # Changed from uploaded_files
        files = cursor.fetchall()
        return [dict(row) for row in files]
    except sqlite3.Error as e:
        logger.info(f"Database error getting file list: {e}")
        return []
