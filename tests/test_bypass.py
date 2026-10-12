"""Detector bypass through the keypad's maintenance menu.

The records below were captured on a JA-80K while bypassing detector 12 for
one period and back (docs/olink-protocol-notes.md). The menu itself is driven
against a small simulated panel that answers keys the way the real one does.
"""

import asyncio

import pytest

from custom_components.jablotron80 import jablotron
from custom_components.jablotron80.const import (
    CABLE_MODEL,
    CABLE_MODEL_JA82T,
    CONFIGURATION_PASSWORD,
    CONFIGURATION_SERIAL_PORT,
)
from custom_components.jablotron80.jablotron import (
    JablotronBypass,
    JablotronBypassError,
    JablotronKeyPress,
    JablotronState,
)

NONE = JablotronBypass.NONE
ONE = JablotronBypass.ONE_PERIOD
PERM = JablotronBypass.PERMANENT


def _build_unit():
    config = {
        CABLE_MODEL: CABLE_MODEL_JA82T,
        CONFIGURATION_SERIAL_PORT: "/dev/null",
        CONFIGURATION_PASSWORD: "1234",
    }
    return jablotron.JA80CentralUnit(hass=None, config=config, options=None)


@pytest.mark.parametrize(
    "record, expected",
    [
        ("ed 21 0b 0c 01 00 00 32 5a ff", (12, NONE)),
        ("ed 21 0b 0c 11 00 00 32 1f ff", (12, ONE)),
        ("ed 21 0b 03 21 00 00 32 00 ff", (3, PERM)),
        ("ed 21 0b 03 31 00 00 32 00 ff", (3, PERM)),
    ],
)
def test_parse_captured_records(record, expected):
    assert JablotronBypass.parse(bytes.fromhex(record)) == expected


@pytest.mark.parametrize(
    "current, wanted, key",
    [
        (NONE, NONE, None),
        (NONE, PERM, "3"),
        (NONE, ONE, "2"),
        (ONE, NONE, "2"),
        (ONE, PERM, "3"),
        (PERM, NONE, "3"),
        (PERM, PERM, None),
    ],
)
def test_key_to_reach(current, wanted, key):
    assert JablotronBypass.key_to_reach(current, wanted) == key


def test_bypass_record_updates_device_not_alarm(event_loop_for_setters):
    """In the menu the warning flag is the bypass, not an alarm/fault."""
    unit = _build_unit()
    device = unit.get_device(12)
    packet = bytes.fromhex("ed 21 0b 0c 11 00 00 32 1f ff")

    event_loop_for_setters.run_until_complete(unit._process_state(packet, packet.hex()))

    assert device.bypass == ONE
    assert unit._bypass_cursor == (12, ONE)
    assert unit.led_alarm is not True
    assert unit.alert != "Alarm"


class FakePanel:
    """Answers keypad commands like a JA-80K, feeding state records back."""

    KEY = {JablotronKeyPress.get_key_command(k)[0]: k for k in "0123456789#*"}

    def __init__(self, unit, positions, bypass=None, drop_every=0):
        self.unit = unit
        self.positions = positions
        self.bypass = dict(bypass or {})
        self.mode = "unset"
        self.index = 0
        self.keys = []
        self.drop_every = drop_every
        self._count = 0
        self.update_devices = False

    def record(self) -> bytes:
        if self.mode == "bypass":
            position = self.positions[self.index]
            flags = 0x01 | (self.bypass.get(position, NONE) << 4)
            return bytes([0xED, 0x21, 0x0B, position, flags, 0, 0, 0x32, 0, 0xFF])
        if self.mode == "maintenance":
            return bytes.fromhex("ed 20 02 00 01 00 00 1e 11 ff")
        return bytes.fromhex("ed 40 00 00 01 00 00 00 16 ff")

    def press(self, key: str) -> None:
        if self.mode == "maintenance" and key == "1":
            self.mode, self.index = "bypass", 0
        elif self.mode == "maintenance" and key == "#":
            self.mode = "unset"
        elif self.mode == "bypass":
            position = self.positions[self.index]
            current = self.bypass.get(position, NONE)
            if key == "1":
                self.index = (self.index - 1) % len(self.positions)
            elif key == "7":
                self.index = (self.index + 1) % len(self.positions)
            elif key == "2":
                self.bypass[position] = NONE if current == ONE else ONE
            elif key == "3":
                self.bypass[position] = NONE if current == PERM else PERM
            elif key == "#":
                self.mode = "maintenance"

    async def add_command(self, command) -> None:
        asyncio.get_running_loop().create_task(self._handle(command))

    async def _handle(self, command) -> None:
        await asyncio.sleep(0)
        code = bytes(command.code)
        if len(code) > 1:
            # "*0" + master code
            self.keys.append("*0+code")
            if self.mode == "unset":
                self.mode = "maintenance"
        else:
            key = self.KEY[code[0]]
            self._count += 1
            if self.drop_every and self._count % self.drop_every == 0:
                self.keys.append(f"({key} lost)")
            else:
                self.keys.append(key)
                self.press(key)
        command.confirm(True)
        record = self.record()
        await self.unit._process_state(record, record.hex())


def _run(loop, unit, panel, coro):
    jablotron._loop = loop
    unit._connection = panel
    unit.BYPASS_STEP_TIMEOUT = 0.2
    unit.BYPASS_ENTER_TIMEOUT = 0.5
    initial = panel.record()
    loop.run_until_complete(unit._process_state(initial, initial.hex()))
    return loop.run_until_complete(coro)


def test_set_permanent_bypass(event_loop_for_setters):
    unit = _build_unit()
    device = unit.get_device(12)
    panel = FakePanel(unit, positions=[2, 3, 5, 12, 14])

    _run(event_loop_for_setters, unit, panel, unit.set_bypass(12, PERM))

    assert panel.bypass[12] == PERM
    assert device.bypass == PERM
    assert panel.keys == ["*0+code", "1", "7", "7", "7", "3", "#", "#"]
    assert panel.mode == "unset"
    assert JablotronState.is_disarmed_state(unit._last_state)


def test_clear_one_period_bypass(event_loop_for_setters):
    unit = _build_unit()
    panel = FakePanel(unit, positions=[2, 12], bypass={12: ONE})

    _run(event_loop_for_setters, unit, panel, unit.set_bypass(12, NONE))

    assert panel.bypass[12] == NONE
    assert panel.keys[-3:] == ["2", "#", "#"]


def test_lost_keypresses_are_retried_without_overshooting(event_loop_for_setters):
    unit = _build_unit()
    panel = FakePanel(unit, positions=[2, 3, 5, 12, 14], drop_every=3)

    _run(event_loop_for_setters, unit, panel, unit.set_bypass(12, PERM))

    assert panel.bypass == {12: PERM}
    assert panel.mode == "unset"


def test_unknown_detector_fails_and_leaves_menu(event_loop_for_setters):
    unit = _build_unit()
    panel = FakePanel(unit, positions=[2, 3, 5])

    with pytest.raises(JablotronBypassError, match="not in the bypass menu"):
        _run(event_loop_for_setters, unit, panel, unit.set_bypass(12, PERM))

    assert panel.bypass == {}
    assert panel.mode == "unset"


def test_refuses_when_armed(event_loop_for_setters):
    unit = _build_unit()
    panel = FakePanel(unit, positions=[2, 12])
    armed = bytes.fromhex("ed 43 00 00 09 00 00 00 00 ff")
    jablotron._loop = event_loop_for_setters
    unit._connection = panel
    unit.BYPASS_STEP_TIMEOUT = 0.2
    event_loop_for_setters.run_until_complete(unit._process_state(armed, armed.hex()))

    with pytest.raises(JablotronBypassError, match="fully unset"):
        event_loop_for_setters.run_until_complete(unit.set_bypass(12, PERM))

    assert "*0+code" not in panel.keys


def test_read_bypasses_walks_whole_menu(event_loop_for_setters):
    unit = _build_unit()
    devices = {p: unit.get_device(p) for p in (2, 3, 12)}
    panel = FakePanel(unit, positions=[2, 3, 12], bypass={3: ONE, 12: PERM})

    result = _run(event_loop_for_setters, unit, panel, unit.read_bypasses())

    assert result == {2: NONE, 3: ONE, 12: PERM}
    assert [devices[p].bypass for p in (2, 3, 12)] == [NONE, ONE, PERM]
    assert panel.mode == "unset"


def _feed(loop, unit, *records):
    for record in records:
        packet = bytes.fromhex(record)
        loop.run_until_complete(unit._process_state(packet, packet.hex()))


def test_unsetting_ends_one_period_bypasses(event_loop_for_setters):
    """Oasis manual ch. 16: a one-period bypass is cancelled by unsetting."""
    unit = _build_unit()
    one, perm = unit.get_device(3), unit.get_device(12)
    one.bypass, perm.bypass = ONE, PERM

    _feed(
        event_loop_for_setters,
        unit,
        "ed 40 00 00 01 00 00 00 16 ff",  # unset
        "ed 43 00 00 09 00 00 00 00 ff",  # set ABC
    )
    assert one.bypass == ONE

    _feed(event_loop_for_setters, unit, "ed 40 00 00 01 00 00 00 16 ff")  # unset again

    assert one.bypass == NONE
    assert perm.bypass == PERM


def test_leaving_maintenance_keeps_one_period_bypass(event_loop_for_setters):
    unit = _build_unit()
    device = unit.get_device(3)
    device.bypass = ONE

    _feed(
        event_loop_for_setters,
        unit,
        "ed 20 02 00 01 00 00 1e 11 ff",  # maintenance
        "ed 40 00 00 01 00 00 00 16 ff",  # back to unset
    )

    assert device.bypass == ONE


def test_service_mode_clears_all_bypasses(event_loop_for_setters):
    unit = _build_unit()
    devices = [unit.get_device(3), unit.get_device(12)]
    devices[0].bypass, devices[1].bypass = ONE, PERM

    _feed(
        event_loop_for_setters,
        unit,
        "ed 40 00 00 01 00 00 00 16 ff",
        "ed 00 01 00 01 00 00 00 00 ff",  # service
    )

    assert [d.bypass for d in devices] == [NONE, NONE]


def test_snapshot_seeds_state_and_supported_detectors(event_loop_for_setters):
    unit = _build_unit()
    listed, unlisted = unit.get_device(12), unit.get_device(20)

    unit.load_bypass_snapshot({"12": PERM, "3": NONE})

    assert listed.bypass == PERM and listed._bypass_supported is True
    assert unlisted.bypass is None and unlisted._bypass_supported is False


def test_no_snapshot_assumes_no_bypass(event_loop_for_setters):
    unit = _build_unit()
    device = unit.get_device(12)

    unit.load_bypass_snapshot(None)

    assert device.bypass == NONE
    assert device._bypass_supported is None


def test_read_marks_unlisted_detectors_and_known(event_loop_for_setters):
    unit = _build_unit()
    listed, unlisted = unit.get_device(12), unit.get_device(20)
    panel = FakePanel(unit, positions=[2, 12])

    _run(event_loop_for_setters, unit, panel, unit.read_bypasses())

    assert unit._bypass_known
    assert listed._bypass_supported is True
    assert unlisted._bypass_supported is False
