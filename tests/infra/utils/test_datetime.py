from datetime import datetime, timedelta, timezone

from src.infra.utils.datetime import ensure_utc, parse_iso, to_iso


def test_ensure_utc_keeps_naive_datetimes_as_utc() -> None:
    value = ensure_utc(datetime(2026, 5, 10, 12, 0, 0))

    assert value.isoformat() == "2026-05-10T12:00:00+00:00"


def test_ensure_utc_normalizes_offset_datetimes_to_utc() -> None:
    value = ensure_utc(datetime(2026, 5, 10, 20, 0, 0, tzinfo=timezone(timedelta(hours=8))))

    assert value.isoformat() == "2026-05-10T12:00:00+00:00"


def test_parse_and_format_iso_normalize_to_utc() -> None:
    assert parse_iso("2026-05-10T20:00:00+08:00").isoformat() == ("2026-05-10T12:00:00+00:00")
    assert to_iso(datetime(2026, 5, 10, 20, 0, 0, tzinfo=timezone(timedelta(hours=8)))) == (
        "2026-05-10T12:00:00+00:00"
    )
