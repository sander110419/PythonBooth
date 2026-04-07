from datetime import datetime

from pythonbooth.services.naming import NamingContext, compile_filename, sanitize_filename, sanitize_filename_part


def test_brace_template_formats_tokens_and_sequence():
    ctx = NamingContext(
        event_name="Autumn / Expo",
        booth_name="Booth:01",
        session_name="Evening Session",
        capture_datetime=datetime(2024, 4, 3, 15, 7, 9),
        camera_sequence=42,
        extension="jpg",
    )

    result = compile_filename("{EVENT}_{BOOTH}_{DAY}_{CAMERA:05d}.{EXT}", ctx)

    assert result.filename == "Autumn_Expo_Booth_01_Wed_00042.jpg"
    assert result.stem == "Autumn_Expo_Booth_01_Wed_00042"
    assert result.extension == ".jpg"


def test_wildcard_template_uses_camera_sequence_by_default():
    ctx = NamingContext(
        event_name="Summer Event",
        booth_name="Main Booth",
        capture_datetime=datetime(2024, 4, 3, 10, 11, 12),
        camera_sequence=7,
        extension="CRX",
    )

    result = ctx.render("EVENT_BOOTH_DAY_0XXXX.CRX")

    assert result.filename == "Summer_Event_Main_Booth_Wed_00007.CRX"
    assert result.sequence_source == "camera"


def test_wildcard_template_can_prefer_session_sequence():
    ctx = NamingContext(
        event_name="Night Shoot",
        booth_name="Booth 2",
        capture_datetime=datetime(2024, 4, 3, 10, 11, 12),
        camera_sequence=7,
        session_sequence=301,
        preferred_sequence_source="session",
        extension="jpg",
    )

    result = ctx.render("EVENT_SESSIONSEQ_XXX.{EXT}")

    assert result.filename == "Night_Shoot_301_301.jpg"
    assert result.sequence_source == "session"


def test_sanitization_strips_path_separators_and_reserved_names():
    assert sanitize_filename_part("../Hello:World/Booth") == "Hello_World_Booth"
    assert sanitize_filename("CON.txt") == "_CON.txt"


def test_context_value_map_exposes_expected_fields():
    ctx = NamingContext(
        event_name="My Event",
        booth_name="Booth A",
        session_id="sess-1",
        capture_datetime=datetime(2024, 1, 2, 3, 4, 5),
        camera_sequence=9,
        session_sequence=11,
        extension=".png",
    )

    values = ctx.value_map()

    assert values["EVENT"] == "My Event"
    assert values["BOOTH"] == "Booth A"
    assert values["DAY"] == "Tue"
    assert values["DATE"] == "20240102"
    assert values["TIME"] == "030405"
    assert values["EXT"] == "png"
    assert values["CAMERA"] == 9
    assert values["SESSIONSEQ"] == 11
