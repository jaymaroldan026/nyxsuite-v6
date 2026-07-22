import json
import tempfile
from pathlib import Path
from unittest import mock

from core import bridge_runtime_config as brc


def test_bridge_config_defaults_transparent_tray_icon_off():
    with tempfile.TemporaryDirectory() as tmp:
        data_dir = Path(tmp)
        config_path = data_dir / "bridge_config.json"

        with mock.patch.object(brc, "DATA_DIR", data_dir), \
                mock.patch.object(brc, "CONFIG_PATH", config_path):
            config = brc.load_bridge_config()

    assert config == {"transparent_tray_icon": False}


def test_bridge_config_saves_and_reloads_transparent_tray_icon():
    with tempfile.TemporaryDirectory() as tmp:
        data_dir = Path(tmp)
        config_path = data_dir / "bridge_config.json"

        with mock.patch.object(brc, "DATA_DIR", data_dir), \
                mock.patch.object(brc, "CONFIG_PATH", config_path):
            saved = brc.save_bridge_config({"transparent_tray_icon": True})
            reloaded = brc.load_bridge_config()

    assert saved["transparent_tray_icon"] is True
    assert reloaded["transparent_tray_icon"] is True


def test_bridge_config_invalid_json_falls_back_to_default():
    with tempfile.TemporaryDirectory() as tmp:
        data_dir = Path(tmp)
        data_dir.mkdir(parents=True, exist_ok=True)
        config_path = data_dir / "bridge_config.json"
        config_path.write_text("{not json", encoding="utf-8")

        with mock.patch.object(brc, "DATA_DIR", data_dir), \
                mock.patch.object(brc, "CONFIG_PATH", config_path):
            config = brc.load_bridge_config()

    assert config["transparent_tray_icon"] is False


def test_bridge_config_write_uses_json_file():
    with tempfile.TemporaryDirectory() as tmp:
        data_dir = Path(tmp)
        config_path = data_dir / "bridge_config.json"

        with mock.patch.object(brc, "DATA_DIR", data_dir), \
                mock.patch.object(brc, "CONFIG_PATH", config_path):
            brc.save_bridge_config({"transparent_tray_icon": True})
            raw = json.loads(config_path.read_text(encoding="utf-8"))

    assert raw == {"transparent_tray_icon": True}
