from pathlib import Path

from backend.textmaps import TextMapIndex


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    index = TextMapIndex(project_root / "data" / "textmaps")
    index.prepare(progress=lambda message: print(f"[TextMaps] {message}", flush=True))
    print(f"[TextMaps] Ready: {index.entry_count:,} bilingual entries", flush=True)


if __name__ == "__main__":
    main()
