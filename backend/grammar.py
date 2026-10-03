"""Normalize Lexirise grammar matches without losing their raw token anchors."""
from __future__ import annotations

import re


def normalize_grammar(text: str, analysis: dict, overrides: dict[str, int]) -> list[dict]:
    raw_tokens = analysis.get("occurrences") or []
    states = analysis.get("grammarStates") or {}
    matches = analysis.get("grammar") or []
    if not isinstance(raw_tokens, list) or not isinstance(states, dict) or not isinstance(matches, list):
        return []
    encoded = text.encode("utf-16-le")
    length = len(encoded) // 2
    rules: dict[str, dict] = {}
    for match in matches:
        if not isinstance(match, dict):
            continue
        slug = match.get("slug")
        if not isinstance(slug, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,160}", slug):
            continue
        indices = match.get("indices") or []
        anchors = match.get("anchors") or []
        if not isinstance(indices, list) or not isinstance(anchors, list):
            continue
        indices = indices + [anchor.get("token") for anchor in anchors if isinstance(anchor, dict)]
        spans = []
        for index in indices:
            if type(index) is not int or not 0 <= index < len(raw_tokens):
                continue
            token = raw_tokens[index]
            if not isinstance(token, dict):
                continue
            start, end = token.get("charStart"), token.get("charEnd")
            if type(start) is not int or type(end) is not int or not 0 <= start < end <= length:
                continue
            try:
                encoded[start * 2:end * 2].decode("utf-16-le")
            except UnicodeDecodeError:
                continue
            span = {"start": start, "end": end}
            if span not in spans:
                spans.append(span)
        # No valid anchor means the rule cannot be tied to this sentence.
        if not spans:
            continue
        state = overrides.get(slug, states.get(slug, 0))
        if type(state) is not int or state not in range(5):
            state = 0
        if slug not in rules:
            rules[slug] = {"slug": slug, "title": match.get("title") if isinstance(match.get("title"), str) else slug,
                           "subtitle": match.get("subtitle") if isinstance(match.get("subtitle"), str) else "",
                           "level": match.get("level") if isinstance(match.get("level"), str) else "",
                           "proficiency": state, "localOverride": slug in overrides,
                           "spans": [], "examples": []}
        rule = rules[slug]
        for span in spans:
            if span not in rule["spans"]:
                rule["spans"].append(span)
        start, end = min(span["start"] for span in spans), max(span["end"] for span in spans)
        example = encoded[start * 2:end * 2].decode("utf-16-le")
        if example not in rule["examples"]:
            rule["examples"].append(example)
    return list(rules.values())
