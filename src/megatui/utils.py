"""Utility functions."""


def truncate_str_lhs(
    text: str, max_length: int, wrapping_txt: str | None = None
) -> str:
    """Truncate a string from the left hand side."""
    text_len = len(text)

    # Check if we need to truncate this at all
    if text_len < max_length:
        return text

    # If we don't get a wrapping string, use our default ellipsis
    if not wrapping_txt:
        wrapping_txt = "…"

    # Final length of our truncated string
    truncate_text_to = max_length - len(wrapping_txt)

    return f"{wrapping_txt}{text[-truncate_text_to:]}"
