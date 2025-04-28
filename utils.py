import re

def parse_time(time_str):
    """Parse time string (e.g., 1m, 30s, 1h) to seconds."""
    time_str = time_str.lower().strip()
    match = re.match(r"(\d+)([smh])", time_str)
    if not match:
        return None
    
    value, unit = match.groups()
    value = int(value)
    if unit == "s":
        return value
    elif unit == "m":
        return value * 60
    elif unit == "h":
        return value * 3600
    return None

def format_time(seconds):
    """Format seconds to human-readable string."""
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        return f"{seconds // 60}m"
    else:
        return f"{seconds // 3600}h"
