"""Start the local UI and open it in the browser (M00_UI.md, D29).

    uv run python scripts/run_ui.py            # http://127.0.0.1:8765
    uv run python scripts/run_ui.py --no-browser

Reachable from this PC only (ENGINE_UI_HOST defaults to 127.0.0.1). Stop with Ctrl+C.
Reads data/engine.db and data/corpus.db; nothing here calls SEC, Tiingo or Gemini.
"""

from __future__ import annotations

import sys
import threading
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import uvicorn  # noqa: E402

from engine.ui.app import create_app  # noqa: E402
from engine.ui.settings import from_env  # noqa: E402


def main() -> int:
    settings = from_env()
    app = create_app(settings)
    url = f"http://{settings.host}:{settings.port}/"
    if "--no-browser" not in sys.argv[1:]:
        threading.Timer(1.0, webbrowser.open, args=(url,)).start()
    print(f"Investment engine UI at {url} (Ctrl+C to stop)")
    uvicorn.run(app, host=settings.host, port=settings.port, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
