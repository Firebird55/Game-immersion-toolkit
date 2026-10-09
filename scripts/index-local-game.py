"""Index a supported local game without launching it or changing its assets."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.game_assets import LOCAL_GAMES
from backend.game_paths import save_install
from backend.local_game import LocalGameTextIndex
from backend.local_game_updates import LocalGameUpdateManager
from backend.local_voice import LocalVoiceAssetService

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--game", required=True, choices=list(LOCAL_GAMES))
parser.add_argument("--install", type=Path)
args = parser.parse_args()
if args.install:
    save_install(args.game, args.install)
data = ROOT / "data"
index = LocalGameTextIndex(args.game, data / args.game)
voices = LocalVoiceAssetService(args.game, data / args.game,
    data / "voice-assets/vgmstream/vgmstream-cli.exe", data / "audio")
updater = LocalGameUpdateManager(args.game, index, voices)
try:
    updater._run()
    status = updater.status()
    print(status["message"])
    if status.get("last_error"):
        print(status["last_error"])
        sys.exit(1)
finally:
    voices.close()
