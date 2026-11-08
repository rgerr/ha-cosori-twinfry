"""Unit tests: parsing, conversions, transitions (no Home Assistant needed)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from custom_components.cosori_twinfry.const import (
    DeviceStatus,
    Program,
    SyncMode,
    ZoneEvent,
    ZoneStatus,
)
from custom_components.cosori_twinfry.models import (
    UnreadableStatusError,
    ZoneSettings,
    ZoneSnapshot,
    classify_transition,
    minutes_to_seconds,
    normalise_status,
    offline_snapshot,
    parse_multi_status,
    program_from_api_mode,
    seconds_to_minutes,
    sync_mode_from_raw,
)

NOW = datetime(2026, 11, 7, 12, 0, tzinfo=UTC)


def _item(chamber: int, status: str, **extra) -> dict:
    return {
        "cookStatus": status,
        "chamber": chamber,
        "cookSetTime": 1200,
        "cookTemp": 200,
        "mode": "AirFry",
        "recipeName": "Frittura ad aria",
        "currentRemainingTime": 1140,
        "totalTimeRemaining": 1140,
        **extra,
    }


def test_time_conversions() -> None:
    assert minutes_to_seconds(20) == 1200
    assert minutes_to_seconds(0.5) == 30
    assert seconds_to_minutes(90) == 1.5
    assert seconds_to_minutes(None) is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("standby", ZoneStatus.STANDBY),
        ("ready", ZoneStatus.READY),
        ("cooking", ZoneStatus.COOKING),
        ("cookStop", ZoneStatus.PAUSED),
        ("pullOut", ZoneStatus.BASKET_OUT),
        ("hold", ZoneStatus.HOLD),
        ("somethingNew", ZoneStatus.UNKNOWN),
        (None, ZoneStatus.STANDBY),
    ],
)
def test_normalise_status(raw, expected) -> None:
    assert normalise_status(raw) == expected


def test_program_and_sync_mapping() -> None:
    assert program_from_api_mode("AirFry") == Program.AIRFRY
    assert program_from_api_mode("grill") == Program.GRILL
    assert program_from_api_mode("Proof") is None
    assert program_from_api_mode(None) is None
    assert sync_mode_from_raw(0) == SyncMode.OFF
    assert sync_mode_from_raw("1") == SyncMode.MATCH
    assert sync_mode_from_raw(2) == SyncMode.SYNC
    assert sync_mode_from_raw(None) is None


def test_parse_two_zones() -> None:
    snap = parse_multi_status(
        {
            "statusList": [_item(1, "cooking"), _item(2, "standby")],
            "tempUnit": "c",
            "syncType": 0,
            "workChamber": 1,
        },
        NOW,
    )
    assert snap.online
    assert snap.zone_1.status == ZoneStatus.COOKING
    assert snap.zone_1.program == Program.AIRFRY
    assert snap.zone_1.set_temperature == 200
    assert snap.zone_1.remaining_s == 1140
    assert snap.zone_1.ends_at(NOW) == NOW + timedelta(seconds=1140)
    # Standby carries no leftover values.
    assert snap.zone_2 == ZoneSnapshot(status=ZoneStatus.STANDBY)
    assert snap.device_status == DeviceStatus.COOKING
    assert snap.sync_mode == SyncMode.OFF


def test_parse_missing_chamber_is_idle() -> None:
    snap = parse_multi_status({"statusList": [_item(2, "cookStop")]}, NOW)
    assert snap.zone_1.status == ZoneStatus.STANDBY
    assert snap.zone_2.status == ZoneStatus.PAUSED
    assert snap.device_status == DeviceStatus.PAUSED
    # A paused cook has no end time.
    assert snap.zone_2.ends_at(NOW) is None


def test_parse_drawer_out_on_idle_zone() -> None:
    # Seen on a CAF-TF101S-AEUR: with the shared drawer out, an idle zone
    # reports pullOut with set time 0 and a default mode.
    snap = parse_multi_status(
        {
            "statusList": [
                _item(1, "pullOut", mode="AirFry", cookSetTime=0, currentRemainingTime=0),
                _item(2, "pullOut", mode="AirFry", cookSetTime=0, currentRemainingTime=0),
            ]
        },
        NOW,
    )
    assert snap.zone_1.status == ZoneStatus.BASKET_OUT
    assert snap.zone_1.program is None
    assert not snap.zone_1.has_cook
    assert snap.device_status == DeviceStatus.IDLE


def test_parse_drawer_out_during_cook() -> None:
    snap = parse_multi_status(
        {"statusList": [_item(1, "pullOut", cookSetTime=180, currentRemainingTime=159)]}, NOW
    )
    assert snap.zone_1.has_cook
    assert snap.zone_1.program == Program.AIRFRY
    assert snap.device_status == DeviceStatus.PAUSED


def test_parse_whole_basket() -> None:
    snap = parse_multi_status({"statusList": [_item(3, "cooking")], "workChamber": 3}, NOW)
    assert snap.whole_basket
    assert snap.zone_1.status == ZoneStatus.COOKING
    assert snap.zone_2.available is False


def test_parse_unknown_status_is_not_kept_as_old_value() -> None:
    snap = parse_multi_status({"statusList": [_item(1, "brandNew")]}, NOW)
    assert snap.zone_1.status == ZoneStatus.UNKNOWN


@pytest.mark.parametrize("inner", [{}, {"statusList": None}, {"statusList": ["x"]}])
def test_parse_unreadable(inner) -> None:
    with pytest.raises(UnreadableStatusError):
        parse_multi_status(inner, NOW)


def test_offline_snapshot() -> None:
    snap = offline_snapshot(NOW)
    assert not snap.online
    assert snap.device_status == DeviceStatus.OFFLINE
    assert not snap.zone_1.available


def _zone(status: ZoneStatus, remaining: int | None = None) -> ZoneSnapshot:
    return ZoneSnapshot(status=status, remaining_s=remaining)


@pytest.mark.parametrize(
    ("before", "after", "elapsed", "expected"),
    [
        (_zone(ZoneStatus.STANDBY), _zone(ZoneStatus.COOKING, 600), 15, ZoneEvent.STARTED),
        (_zone(ZoneStatus.READY), _zone(ZoneStatus.COOKING, 600), 15, ZoneEvent.STARTED),
        (_zone(ZoneStatus.STANDBY), _zone(ZoneStatus.READY, 600), 15, ZoneEvent.READY),
        (_zone(ZoneStatus.COOKING, 300), _zone(ZoneStatus.BASKET_OUT, 290), 15, ZoneEvent.PAUSED),
        (_zone(ZoneStatus.BASKET_OUT, 290), _zone(ZoneStatus.COOKING, 290), 15, ZoneEvent.RESUMED),
        (_zone(ZoneStatus.COOKING, 20), _zone(ZoneStatus.STANDBY), 15, ZoneEvent.FINISHED),
        (_zone(ZoneStatus.COOKING, 100), _zone(ZoneStatus.STANDBY), 60, ZoneEvent.FINISHED),
        (_zone(ZoneStatus.COOKING, 900), _zone(ZoneStatus.STANDBY), 15, ZoneEvent.STOPPED),
        (_zone(ZoneStatus.PAUSED, 900), _zone(ZoneStatus.STANDBY), 15, ZoneEvent.STOPPED),
        (_zone(ZoneStatus.COOKING, 600), _zone(ZoneStatus.COOKING, 585), 15, None),
        (_zone(ZoneStatus.READY), _zone(ZoneStatus.STANDBY), 15, None),
    ],
)
def test_classify_transition(before, after, elapsed, expected) -> None:
    assert classify_transition(before, after, elapsed) == expected


@pytest.mark.parametrize("status", [ZoneStatus.BASKET_OUT, ZoneStatus.PAUSED])
def test_no_event_when_idle_zone_drawer_returns(status: ZoneStatus) -> None:
    # One drawer for both zones: an idle zone reports pullOut too.
    before = _zone(status, 0)
    after = _zone(ZoneStatus.STANDBY)
    assert classify_transition(before, after, 30, had_cook=False) is None
    assert classify_transition(before, after, 30, had_cook=True) == ZoneEvent.FINISHED


def test_no_event_without_previous() -> None:
    assert classify_transition(None, _zone(ZoneStatus.COOKING, 10), 0) is None


def test_zone_settings_roundtrip_and_fallback() -> None:
    settings = ZoneSettings(program=Program.GRILL, temperature=240, minutes=10)
    assert ZoneSettings.from_dict(settings.as_dict()) == settings
    assert ZoneSettings.from_dict(None) == ZoneSettings()
    assert ZoneSettings.from_dict({"program": "bogus"}) == ZoneSettings()
