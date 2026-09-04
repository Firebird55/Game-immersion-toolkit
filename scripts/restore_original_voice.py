"""Upgrade retained, finalized recordings to exact original assets, if available."""
from pathlib import Path

from backend.storage import TranscriptStore
from backend.voice_assets import VoiceAssetService


def main():
    root = Path(__file__).resolve().parents[1]
    audio = (root / "data/audio").resolve()
    store = TranscriptStore(root / "data/transcript.db")
    assets = VoiceAssetService(root / "data/voice-assets/manifest.json",
                               root / "data/voice-assets/vgmstream/vgmstream-cli.exe", audio)
    rows = {line.id: line for line in store.list(limit=50) + store.list_favorites()}
    updated = 0
    try:
        for line in rows.values():
            if not line.has_audio or not line.voiced or line.audio_source == "original" or not assets.has(line.text_id):
                continue
            filename = assets.extract(line.text_id, line.id)
            current = store.get(line.id)
            if current is None or current.text_id != line.text_id:
                (audio / filename).unlink(missing_ok=True)
                continue
            old = store.audio_path(line.id)
            store.update_audio(line.id, filename, True)
            if old and old != filename:
                old_path = (audio / old).resolve()
                if old_path.parent == audio:
                    old_path.unlink(missing_ok=True)
            updated += 1
        print(f"Restored {updated} retained lines to exact original Mandarin clips.")
    finally:
        assets.close()


if __name__ == "__main__":
    main()
