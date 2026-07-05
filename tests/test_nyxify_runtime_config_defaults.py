import tempfile
from pathlib import Path
from unittest import mock

from core import nyxify_runtime_config as nrc


def test_nyxify_defaults_keep_tags_blank_and_disabled():
    with tempfile.TemporaryDirectory() as tmp:
        data_dir = Path(tmp)
        config_path = data_dir / "nyxify_config.json"

        with mock.patch.object(nrc, "DATA_DIR", data_dir), \
                mock.patch.object(nrc, "CONFIG_PATH", config_path):
            config = nrc.load_nyxify_config()

    assert config["tag_one"] == ""
    assert config["tag_two"] == ""
    assert config["adspower_tags_enabled"] is False
