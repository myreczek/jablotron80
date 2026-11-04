"""Setting the panel clock through the maintenance menu (Oasis manual ch. 17)."""

import datetime

import pytest

from custom_components.jablotron80 import jablotron
from custom_components.jablotron80.jablotron import JA80CentralUnit, JablotronMenuError
from tests.test_bypass import FakePanel, _build_unit, _run


@pytest.mark.parametrize(
    "now, keys",
    [
        # manual example: 21:30, 29 April 2009
        (datetime.datetime(2009, 4, 29, 21, 29, 40), "42130290409"),
        # rounded to the nearest minute at the time the last digit arrives (~1 s)
        (datetime.datetime(2026, 10, 12, 17, 5, 28), "41705121026"),
        (datetime.datetime(2026, 10, 12, 17, 5, 29), "41706121026"),
        # measured case: pressed 18:02:24.7 -> must be 18:02, not 18:03
        (datetime.datetime(2026, 10, 12, 18, 2, 24), "41802121026"),
        # crosses midnight and the year
        (datetime.datetime(2026, 12, 31, 23, 59, 50), "40000010127"),
    ],
)
def test_panel_time_keys(now, keys):
    assert JA80CentralUnit.panel_time_keys(now) == keys


def test_set_panel_time_enters_maintenance_and_leaves(event_loop_for_setters):
    unit = _build_unit()
    panel = FakePanel(unit, positions=[2])
    clock = lambda: datetime.datetime(2026, 10, 12, 17, 5, 0)

    _run(event_loop_for_setters, unit, panel, unit.set_panel_time(clock))

    assert panel.keys == ["*0+code", "41705121026", "#"]
    assert panel.mode == "unset"


def test_set_panel_time_refuses_when_armed(event_loop_for_setters):
    unit = _build_unit()
    panel = FakePanel(unit, positions=[2])
    armed = bytes.fromhex("ed 43 00 00 09 00 00 00 00 ff")
    jablotron._loop = event_loop_for_setters
    unit._connection = panel
    unit.BYPASS_STEP_TIMEOUT = 0.2
    unit.UNSET_SETTLE_TIMEOUT = 0.2
    unit.CLOCK_VERIFY_TIMEOUT = 0.2
    event_loop_for_setters.run_until_complete(unit._process_state(armed, armed.hex()))

    with pytest.raises(JablotronMenuError, match="fully unset"):
        event_loop_for_setters.run_until_complete(unit.set_panel_time())

    assert panel.keys == []


def test_set_panel_time_waits_for_the_unset_record(event_loop_for_setters):
    """The disarm event flips the alarm entity before the panel's state record
    says unset; an automation reacting at once must not be refused."""
    import asyncio

    unit = _build_unit()
    panel = FakePanel(unit, positions=[2])
    jablotron._loop = event_loop_for_setters
    unit._connection = panel
    unit.BYPASS_STEP_TIMEOUT = 0.2
    unit.UNSET_SETTLE_TIMEOUT = 0.2
    unit.CLOCK_VERIFY_TIMEOUT = 0.2
    unit.BYPASS_ENTER_TIMEOUT = 0.5
    armed = bytes.fromhex("ed 42 00 00 05 00 00 00 00 ff")  # set AB
    event_loop_for_setters.run_until_complete(unit._process_state(armed, armed.hex()))
    clock = lambda: datetime.datetime(2026, 11, 4, 6, 2, 43)

    async def scenario():
        task = asyncio.ensure_future(unit.set_panel_time(clock))
        await asyncio.sleep(0.05)
        panel.mode = "unset"
        unset = panel.record()
        await unit._process_state(unset, unset.hex())
        await task

    event_loop_for_setters.run_until_complete(scenario())

    assert panel.keys == ["*0+code", "40603041126", "#"]
    assert panel.mode == "unset"


def _clock_events(unit, panel, drifts):
    """Leaving maintenance reports the panel clock, as the real panel's event does."""
    import time

    def report():
        unit._panel_time_drift._value = drifts.pop(0)
        unit._panel_clock_at = time.monotonic()

    panel.on_unset = report


def test_set_panel_time_retries_a_time_that_did_not_take(event_loop_for_setters):
    unit = _build_unit()
    panel = FakePanel(unit, positions=[2])
    _clock_events(unit, panel, [93, 3])
    clock = lambda: datetime.datetime(2026, 11, 4, 9, 57, 23)

    _run(event_loop_for_setters, unit, panel, unit.set_panel_time(clock))

    assert panel.keys == ["*0+code", "40957041126", "#", "*0+code", "40957041126", "#"]


def test_set_panel_time_gives_up_after_the_retry(event_loop_for_setters):
    unit = _build_unit()
    panel = FakePanel(unit, positions=[2])
    _clock_events(unit, panel, [93, 93])

    with pytest.raises(JablotronMenuError, match="still off by 93 s"):
        _run(event_loop_for_setters, unit, panel, unit.set_panel_time())

    assert panel.keys.count("*0+code") == 2
    assert panel.mode == "unset"


def test_set_panel_time_accepts_a_good_first_attempt(event_loop_for_setters):
    unit = _build_unit()
    panel = FakePanel(unit, positions=[2])
    _clock_events(unit, panel, [-20])

    _run(event_loop_for_setters, unit, panel, unit.set_panel_time())

    assert panel.keys.count("*0+code") == 1
