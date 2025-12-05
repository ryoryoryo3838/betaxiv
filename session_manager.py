import json
import os
import shutil
from datetime import datetime

SESSIONS_DIR = "sessions"

def ensure_sessions_dir():
    if not os.path.exists(SESSIONS_DIR):
        os.makedirs(SESSIONS_DIR)

def save_session(session_id, data):
    ensure_sessions_dir()
    filepath = os.path.join(SESSIONS_DIR, f"{session_id}.json")
    # Convert non-serializable objects (like timestamps) if necessary
    # Assuming data contains basic types. 
    # NOTE: The gemini_file object is not serializable. We should store its name/uri.
    # However, for simplicity we rely on re-uploading the file if the session is reloaded,
    # because Gemini file handles expire.
    # We will store the LOCAL path of the PDF.
    
    with open(filepath, "w") as f:
        json.dump(data, f, indent=4)

def load_session(session_id):
    filepath = os.path.join(SESSIONS_DIR, f"{session_id}.json")
    if os.path.exists(filepath):
        with open(filepath, "r") as f:
            return json.load(f)
    return None

def list_sessions():
    ensure_sessions_dir()
    sessions = []
    for filename in os.listdir(SESSIONS_DIR):
        if filename.endswith(".json"):
            filepath = os.path.join(SESSIONS_DIR, filename)
            try:
                with open(filepath, "r") as f:
                    data = json.load(f)
                    # Use the first chat message as title if available, else timestamp
                    title = data.get("title", filename)
                    sessions.append({
                        "id": filename.replace(".json", ""),
                        "title": title,
                        "timestamp": data.get("timestamp", ""),
                        "preview": title
                    })
            except Exception:
                continue
    # Sort by timestamp desc
    sessions.sort(key=lambda x: x["timestamp"], reverse=True)
    return sessions

def delete_session(session_id):
    filepath = os.path.join(SESSIONS_DIR, f"{session_id}.json")
    if os.path.exists(filepath):
        os.remove(filepath)
