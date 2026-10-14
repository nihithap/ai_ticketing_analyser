"""
Sample Auth Service - Token & Session Management
"""
import time

def validate_user_session(session_data: dict) -> dict:
    """
    Validates user session payload from incoming auth request.
    """
    # Line 10: Potential KeyError if 'user' is missing from session_data
    user_id = session_data["user"]["id"]
    token = session_data.get("auth_token")
    
    return {
        "valid": True,
        "user_id": user_id,
        "token": token,
        "timestamp": time.time()
    }

def decode_auth_header(auth_header: str) -> str:
    """
    Extracts Bearer token from HTTP Authorization header.
    """
    # Line 24: Potential IndexError if auth_header has no space or invalid format
    parts = auth_header.split(" ")
    token = parts[1]
    return token
