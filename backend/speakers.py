from __future__ import annotations

import re

from rapidfuzz import fuzz

from .models import TranscriptLine
from .storage import TranscriptStore
from .textmaps import TextMapIndex, normalize_english
from .voice_assets import VoiceAssetService


VOICE_TOKEN_RE = re.compile(r"/VO_([^/]+)", re.IGNORECASE)
CAMEL_BOUNDARY_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
NON_SPEAKERS = {"galgame", "comic", "voice", "main", "companion"}

ALIASES = {
    "anbi": "Anby",
    "astra": "Astra Yao",
    "aokaku": "Soukaku",
    "silveranby": "Soldier 0 - Anby",
    "spanbi": "Soldier 0 - Anby",
}

VARIANT_PREFIXES = ("student", "taoist", "swimsuit", "starlight", "unleash")


def _voice_token(source: str) -> str | None:
    tokens = [match.group(1) for match in VOICE_TOKEN_RE.finditer(source)]
    return next((token for token in reversed(tokens) if token.casefold() not in NON_SPEAKERS), None)


def _humanize_token(token: str) -> list[str]:
    lowered = token.casefold()
    candidates = []
    alias = ALIASES.get(lowered)
    if alias:
        candidates.append(alias)
    candidates.extend((token, CAMEL_BOUNDARY_RE.sub(" ", token)))
    for prefix in VARIANT_PREFIXES:
        if lowered.startswith(prefix) and len(token) > len(prefix) + 2:
            base = token[len(prefix):]
            candidates.extend((base, CAMEL_BOUNDARY_RE.sub(" ", base)))
    return list(dict.fromkeys(candidate.strip() for candidate in candidates if candidate.strip()))


def _ocr_speaker(source_ocr: str, english: str) -> str | None:
    explicit = re.match(r"^\s*([A-Z][A-Za-z' -]{1,38})\s*[:：]\s*", source_ocr)
    if explicit:
        return explicit.group(1).strip()
    words = source_ocr.split()
    target = normalize_english(english)
    if len(words) < 2 or not target:
        return None
    for prefix_length in range(1, min(4, len(words))):
        remainder = normalize_english(" ".join(words[prefix_length:]))
        if len(remainder) >= max(6, int(len(target) * 0.65)) and fuzz.ratio(remainder, target) >= 88:
            candidate = " ".join(words[:prefix_length]).strip(" \"'.,!?…:;()[]{}")
            if candidate and normalize_english(candidate) != target[: len(normalize_english(candidate))]:
                return candidate
    return None


class SpeakerResolver:
    def __init__(
        self,
        textmaps: TextMapIndex,
        voice_assets: VoiceAssetService,
        transcript: TranscriptStore,
    ) -> None:
        self.textmaps = textmaps
        self.voice_assets = voice_assets
        self.transcript = transcript

    def resolve(self, line: TranscriptLine) -> tuple[str, str] | None:
        if not self.textmaps.ready:
            return None
        candidates: list[str] = []
        token = _voice_token(self.voice_assets.source_for(line.text_id, line.english))
        if token:
            candidates.extend(_humanize_token(token))
        ocr_name = _ocr_speaker(line.source_ocr, line.english)
        if ocr_name:
            candidates.insert(0, ocr_name)
        return self.textmaps.resolve_display_name(candidates)

    def enrich(self, line: TranscriptLine) -> TranscriptLine:
        if line.speaker_english and line.speaker_chinese:
            return line
        names = self.resolve(line)
        if names is None:
            return line
        updated = self.transcript.update_speaker(line.id, *names)
        return updated or line

    def backfill(self) -> int:
        updated = 0
        for line in self.transcript.list(limit=1000):
            if line.speaker_english and line.speaker_chinese:
                continue
            enriched = self.enrich(line)
            updated += int(bool(enriched.speaker_english and enriched.speaker_chinese))
        return updated
