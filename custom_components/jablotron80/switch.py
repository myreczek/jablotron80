from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import EntityCategory
from homeassistant.components.switch import SwitchEntity
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.restore_state import RestoreEntity
from .jablotron import JA80CentralUnit, JablotronDevice, JablotronBypass, JablotronBypassError
from .jablotronHA import JablotronEntity
from typing import Any, Dict, Optional
from .const import DATA_JABLOTRON, DOMAIN


import logging

LOGGER = logging.getLogger(__package__)

# positions 1-50 are peripherals; 0 / 51+ are the control panel itself
MAX_PERIPHERAL_ID = 50


def bypassable(device: JablotronDevice) -> bool:
    if not 0 < device.device_id <= MAX_PERIPHERAL_ID:
        return False
    if device.is_indoor_siren or device.is_outdoor_siren:
        return False
    # once the bypass menu has been read, only offer what it lists
    return device._bypass_supported is not False


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities) -> None:
    cu = hass.data[DOMAIN][config_entry.entry_id][DATA_JABLOTRON]  # type: JA80CentralUnit
    async_add_entities([JablotronBypassSwitch(device, cu) for device in cu.devices if bypassable(device)], True)


class JablotronBypassSwitch(JablotronEntity, SwitchEntity, RestoreEntity):
    """Permanent bypass of one detector, set through the keypad's maintenance menu.

    ``on`` = the detector is bypassed (permanently or for one setting period).
    The integration reads the bypass menu once after start-up and then tracks
    changes itself; until then the last known state is restored. Changing it
    needs the system to be fully unset and uses the configured master code.
    """

    def __init__(self, device: JablotronDevice, cu: JA80CentralUnit):
        super().__init__(cu, device)

    @property
    def available(self) -> bool:
        # not offered by the panel's bypass menu (e.g. a keypad or output)
        return super().available and self._object._bypass_supported is not False

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        # the restored state is newer than the stored snapshot, but not than a live read
        if not self._cu._bypass_known and last is not None and last.state in ("on", "off"):
            if last.state == "off":
                self._object.bypass = JablotronBypass.NONE
            elif last.attributes.get("bypass type") == "one period":
                self._object.bypass = JablotronBypass.ONE_PERIOD
            else:
                self._object.bypass = JablotronBypass.PERMANENT

    @property
    def is_on(self) -> Optional[bool]:
        if self._object.bypass is None:
            return None
        return self._object.bypass != JablotronBypass.NONE

    @property
    def entity_category(self) -> Optional[EntityCategory]:
        return EntityCategory.CONFIG

    @property
    def icon(self) -> Optional[str]:
        return "mdi:shield-off-outline" if self.is_on else "mdi:shield-check-outline"

    @property
    def unique_id(self) -> str:
        return f"{super().unique_id}.bypass"

    @property
    def name(self) -> str:
        return f"{super().name} Bypass"

    @property
    def extra_state_attributes(self) -> Optional[Dict[str, Any]]:
        attr = super().extra_state_attributes or {}
        if self._object.bypass == JablotronBypass.ONE_PERIOD:
            attr["bypass type"] = "one period"
        elif self._object.bypass == JablotronBypass.PERMANENT:
            attr["bypass type"] = "permanent"
        return attr

    async def _set(self, wanted: int) -> None:
        try:
            await self._cu.set_bypass(self._object.device_id, wanted)
        except JablotronBypassError as ex:
            raise HomeAssistantError(f"Bypass of {self.name} failed: {ex}") from ex

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set(JablotronBypass.PERMANENT)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set(JablotronBypass.NONE)
