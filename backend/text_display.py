"""Shared stdlib-only display cleanup for official and observed text."""
import html
import re


TAG_RE = re.compile(r"<[^>]+>")


def display_text(value: str) -> str:
    text = html.unescape(str(value or ""))
    text = text.replace("\\n", " ").replace("\r", " ").replace("\n", " ")
    text = TAG_RE.sub("", text)
    return " ".join(text.split()).strip()
