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
    event_loop_for_setters.run_until_complete(unit._process_state(armed, armed.hex()))

    with pytest.raises(JablotronMenuError, match="fully unset"):
        event_loop_for_setters.run_until_complete(unit.set_panel_time())

    assert panel.keys == []
