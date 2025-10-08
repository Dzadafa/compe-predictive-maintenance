import re

import re

def parse_duration(text: str, default_cd) -> int:
    """
    Parse durations like '10d', '2m', '1y' into seconds.
    Supports multiple parts, e.g. '1y2m10d'.
    """
    total = 0
    matches = re.findall(r"(\d+)([dmy])", text.lower())
    for amount, unit in matches:
        amount = int(amount)
        if unit == "d":
            total += amount * 24 * 3600
        elif unit == "m":
            total += amount * 30 * 24 * 3600   # approx month
        elif unit == "y":
            total += amount * 365 * 24 * 3600  # approx year
    return total if total > 0 else default_cd



def format_duration(seconds: int) -> str:
    years, seconds = divmod(seconds, 31536000)  # 365 days
    months, seconds = divmod(seconds, 2592000)  # 30 days
    weeks, seconds = divmod(seconds, 604800)
    days, _ = divmod(seconds, 86400)

    parts = []
    if years: parts.append(f"{years}y")
    if months: parts.append(f"{months}mo")
    if weeks: parts.append(f"{weeks}w")
    if days: parts.append(f"{days}d")

    return " ".join(parts) if parts else "0d"