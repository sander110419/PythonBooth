from pythonbooth.services.canon_guidance import build_canon_access_help


def test_canon_access_help_mentions_remote_control_mode():
    help_text = build_canon_access_help()

    assert "Photo Import/Remote Control" in help_text
    assert "Wi-Fi/Bluetooth" in help_text
