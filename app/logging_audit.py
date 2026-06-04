import json
import logging
import re
from datetime import datetime
from typing import Any, Dict, List
from app.config import LOG_FILE

# Set up logger
logger = logging.getLogger("fallback_runner_audit")
logger.setLevel(logging.INFO)

# Initialize handlers if they don't exist
if not logger.handlers:
    # Console log handler
    c_handler = logging.StreamHandler()
    c_handler.setLevel(logging.INFO)
    c_format = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    c_handler.setFormatter(c_format)
    logger.addHandler(c_handler)
    
    # File log handler (for persistent audit trials)
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        f_handler = logging.FileHandler(LOG_FILE, encoding='utf-8')
        f_handler.setLevel(logging.INFO)
        f_format = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        f_handler.setFormatter(f_format)
        logger.addHandler(f_handler)
    except Exception as e:
        print(f"Warning: Could not set up file handler for audit log at {LOG_FILE}: {e}")

# Key words to redact
REDACT_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r"token", r"authorization", r"cookie", r"password", 
        r"secret", r"private_key", r"api_key", r"gateway_token", r"session"
    ]
]

def redact_sensitive_data(data: Any) -> Any:
    """Recursively redacts values for keys resembling secrets (e.g. passwords, tokens, keys)."""
    if isinstance(data, dict):
        redacted = {}
        for k, v in data.items():
            if any(pattern.search(k) for pattern in REDACT_PATTERNS) and not isinstance(v, (dict, list)):
                redacted[k] = "[REDACTED]"
            else:
                redacted[k] = redact_sensitive_data(v)
        return redacted
    elif isinstance(data, list):
        return [redact_sensitive_data(item) for item in data]
    elif isinstance(data, str):
        # Additional cleanup to prevent accidental print of private key formats or secrets
        if "BEGIN PRIVATE KEY" in data or "ssh-rsa" in data:
            return "[REDACTED KEY MATERIAL]"
        return data
    return data


def log_audit_event(event_type: str, details: Dict[str, Any] = None) -> None:
    """Logs an audit event structure to the log stream."""
    if details is None:
        details = {}
        
    clean_details = redact_sensitive_data(details)
    
    log_payload = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "event_type": event_type,
        "details": clean_details
    }
    
    # Use standard logging info, writing JSON for easy parsing
    logger.info(f"AUDIT_EVENT: {json.dumps(log_payload)}")

def get_audit_logs_for_run(run_id: str) -> str:
    """Retrieves all log events matching run_id from the audit log file."""
    if not LOG_FILE.exists():
        return ""
        
    matching_lines = []
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            for line in f:
                if run_id in line:
                    matching_lines.append(line.strip())
    except Exception as e:
        return f"Error reading audit log: {str(e)}"
        
    return "\n".join(matching_lines)
