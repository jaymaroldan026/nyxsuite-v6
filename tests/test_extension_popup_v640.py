from pathlib import Path
import json


ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return (ROOT / path).read_text(encoding="utf-8")


def test_nyx_popup_queue_is_removed_from_extension_only():
    popup_html = read("nyx_extension/popup.html")
    popup_js = read("nyx_extension/popup.js")

    for removed in [
        "queueSectionToggle",
        "queueSearchInput",
        "queueTable",
        "markDoneQueueProfileButton",
        "relaunchQueueProfileButton",
        "closeQueueProfileButton",
        "removeQueueProfileButton",
        "Nyx Queue",
    ]:
        assert removed not in popup_html

    for removed in [
        "renderQueueTable",
        "getFilteredQueueRows",
        "getSelectedQueueProfileIds",
        "markDoneSelectedQueueProfiles",
        "closeQueueProfile",
        "queueSearchInput",
        "queueTable",
        "NYX_MARK_DONE_PROFILE",
        "NYX_RELAUNCH_QUEUE_PROFILE",
        "NYX_REMOVE_QUEUE_PROFILE",
    ]:
        assert removed not in popup_js

    assert "Daily Update" in popup_html
    assert "Nyx Scrape" in popup_html
    assert "setupInstallButton" in popup_html


def test_nyxify_popup_queue_is_removed_and_setup_install_is_available():
    popup_html = read("nyxify_extension/popup.html")
    popup_js = read("nyxify_extension/popup.js")

    for removed in [
        "sheetQueue",
        "banProxyButton",
        "removeQueueRowButton",
        "Nyxify Queue",
    ]:
        assert removed not in popup_html

    for removed in [
        "renderSheetQueue",
        "getQueueSignature",
        "syncSelectedRowClass",
        "getSelectedRow",
        "sheetQueue",
        "banProxyButton",
        "removeQueueRowButton",
        "NYXIFY_BAN_PROXY",
        "NYXIFY_REMOVE_QUEUE_ROW",
    ]:
        assert removed not in popup_js

    assert "setupInstallButton" in popup_html
    assert (ROOT / "nyxify_extension" / "setup.html").exists()
    assert (ROOT / "nyxify_extension" / "setup.js").exists()


def test_v640_version_metadata_is_synced():
    version_py = read("core/version.py")
    nyx_manifest = json.loads(read("nyx_extension/manifest.json"))
    nyxify_manifest = json.loads(read("nyxify_extension/manifest.json"))

    assert 'NYX_VERSION = "6.4.0"' in version_py
    assert 'NYXIFY_VERSION = "6.4.0"' in version_py
    assert read("VERSION").strip() == "6.4.0"
    assert nyx_manifest["version"] == "6.4.0"
    assert nyx_manifest["version_name"] == "6.4.0"
    assert nyxify_manifest["version"] == "6.4.0"
    assert nyxify_manifest["version_name"] == "6.4.0"
