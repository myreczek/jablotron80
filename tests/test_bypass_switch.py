"""The bypass switch shows the requested state at once and coalesces toggles.

A bypass change walks the keypad menu for 10-30 s. Without this the switch kept
its old state (and flickered with the menu) until the panel was done, and every
extra tap queued another full menu walk.
"""

import asyncio
import importlib
import sys
import types

import pytest

from custom_components.jablotron80.jablotron import (
    JablotronBypass,
    JablotronBypassError,
    JablotronDevice,
)


@pytest.fixture
def switch_module(monkeypatch):
    for name, attributes in {
        "homeassistant.components.switch": {"SwitchEntity": type("SwitchEntity", (), {})},
        "homeassistant.helpers.restore_state": {"RestoreEntity": type("RestoreEntity", (), {})},
        "homeassistant.exceptions": {"HomeAssistantError": type("HomeAssistantError", (Exception,), {})},
    }.items():
        module = sys.modules.get(name)
        if module is None:
            module = types.ModuleType(name)
            monkeypatch.setitem(sys.modules, name, module)
        for attribute, value in attributes.items():
            if not hasattr(module, attribute):
                monkeypatch.setattr(module, attribute, value, raising=False)
    monkeypatch.delitem(sys.modules, "custom_components.jablotron80.switch", raising=False)
    return importlib.import_module("custom_components.jablotron80.switch")


class FakeUnit:
    def __init__(self, device, fail=False):
        self.device = device
        self.calls = []
        self.fail = fail
        self.release = asyncio.Event()

    async def set_bypass(self, device_id, wanted):
        self.calls.append(wanted)
        await self.release.wait()
        if self.fail:
            raise JablotronBypassError("menu did not open")
        self.device._bypass = wanted


def _switch(module, unit, device):
    entity = module.JablotronBypassSwitch.__new__(module.JablotronBypassSwitch)
    entity._cu = unit
    entity._object = device
    entity._requested = None
    entity._busy = False
    entity.states = []
    entity.async_write_ha_state = lambda: entity.states.append(entity.is_on)
    return entity


def test_shows_requested_state_at_once(switch_module, event_loop_for_setters):
    loop = event_loop_for_setters
    device = JablotronDevice(13)
    device._bypass = JablotronBypass.NONE
    unit = FakeUnit(device)
    switch = _switch(switch_module, unit, device)

    task = loop.create_task(switch.async_turn_on())
    loop.run_until_complete(asyncio.sleep(0))
    assert switch.is_on is True  # before the panel is done

    # the menu walk passes the detector while it is still unbypassed
    device._bypass = JablotronBypass.NONE
    assert switch.is_on is True

    unit.release.set()
    loop.run_until_complete(task)
    assert switch.is_on is True
    assert unit.calls == [JablotronBypass.PERMANENT]


def test_rapid_toggles_end_in_the_last_request(switch_module, event_loop_for_setters):
    loop = event_loop_for_setters
    device = JablotronDevice(13)
    device._bypass = JablotronBypass.NONE
    unit = FakeUnit(device)
    switch = _switch(switch_module, unit, device)

    first = loop.create_task(switch.async_turn_on())
    loop.run_until_complete(asyncio.sleep(0))
    loop.run_until_complete(switch.async_turn_off())  # returns, picked up later
    loop.run_until_complete(switch.async_turn_on())
    loop.run_until_complete(switch.async_turn_off())
    assert switch.is_on is False

    unit.release.set()
    loop.run_until_complete(first)
    assert unit.calls == [JablotronBypass.PERMANENT, JablotronBypass.NONE]
    assert switch.is_on is False


def test_failure_reverts_to_real_state(switch_module, event_loop_for_setters):
    loop = event_loop_for_setters
    device = JablotronDevice(13)
    device._bypass = JablotronBypass.NONE
    unit = FakeUnit(device, fail=True)
    switch = _switch(switch_module, unit, device)
    unit.release.set()

    with pytest.raises(Exception, match="menu did not open"):
        loop.run_until_complete(switch.async_turn_on())

    assert switch.is_on is False
    assert switch.states[0] is True and switch.states[-1] is False
