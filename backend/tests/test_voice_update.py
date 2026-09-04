import json

from scripts.update_voice_assets import discover_game_data, inventory


def test_voice_inventory_changes_with_installed_package(tmp_path):
    game = tmp_path / "ZenlessZoneZero_Data"
    audio = game / "Persistent/Audio/Windows/Full/Cn"
    audio.mkdir(parents=True)
    package = audio / "10100.pck"
    package.write_bytes(b"first")
    before = inventory(game, [])
    package.write_bytes(b"changed package")
    assert inventory(game, []) != before


def test_game_data_can_be_recovered_without_running_game(tmp_path):
    game = tmp_path / "ZenlessZoneZero_Data"
    game.mkdir()
    data = tmp_path / "data/agent-voices"
    data.mkdir(parents=True)
    (data / "library.json").write_text(json.dumps({"game_data": str(game)}))
    assert discover_game_data(tmp_path) == game
