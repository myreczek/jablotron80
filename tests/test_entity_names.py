"""A name given in the UI renames the detector only through its main entity.

Several entities share one JablotronDevice. Renaming e.g. the battery sensor
used to overwrite the device name, so every sibling entity (and the device)
was shown as "<name> Battery". Sub-entities (battery, bypass) now set
``_names_object = False``.
"""

import types

from custom_components.jablotron80.jablotronHA import JablotronEntity
from tests.test_reconciliation import _build_unit


class MainEntity(JablotronEntity):
    def async_write_ha_state(self):
        pass


class SubEntity(MainEntity):
    _names_object = False


def _added(entity, registry_name, loop):
    entity.registry_entry = types.SimpleNamespace(name=registry_name)
    loop.run_until_complete(entity.async_added_to_hass())


def test_renamed_sub_entity_keeps_device_name(event_loop_for_setters):
    unit = _build_unit()
    device = unit.get_device(7)
    device.name = "Dveře terasa"

    _added(SubEntity(unit, device), "Dveře terasa Battery", event_loop_for_setters)

    assert device.name == "Dveře terasa"


def test_renamed_main_entity_still_renames_device(event_loop_for_setters):
    unit = _build_unit()
    device = unit.get_device(7)
    device.name = "serial 01868075"

    _added(MainEntity(unit, device), "Dveře terasa", event_loop_for_setters)

    assert device.name == "Dveře terasa"


def test_battery_and_bypass_entities_are_sub_entities():
    # the platform modules need the full HA stack, so check their source
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1] / "custom_components" / "jablotron80"
    for module, cls in (("binary_sensor.py", "JablotronBatteryBinarySensor"), ("switch.py", "JablotronBypassSwitch")):
        source = (root / module).read_text(encoding="utf-8")
        body = source.split(f"class {cls}(", 1)[1].split("\nclass ", 1)[0]
        assert "_names_object = False" in body, cls

