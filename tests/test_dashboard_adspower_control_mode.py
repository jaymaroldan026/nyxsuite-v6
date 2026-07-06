from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_dashboard_exposes_adspower_control_mode_buttons():
    html = (ROOT / "webui" / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "webui" / "dashboard.js").read_text(encoding="utf-8")

    assert "adspower-mode-auto" in html
    assert "adspower-mode-api" in html
    assert "adspower-mode-gui" in html
    assert "adspower_control_mode" in js
    assert "cfg-adspower_control_mode" in js
