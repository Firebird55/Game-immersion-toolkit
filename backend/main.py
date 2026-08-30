from __future__ import annotations

import uvicorn


def main() -> None:
    uvicorn.run(
        "backend.api:app",
        host="127.0.0.1",
        port=8766,
        log_level="info",
        reload=False,
    )


if __name__ == "__main__":
    main()
