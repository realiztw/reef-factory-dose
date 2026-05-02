"""Sensor entities for Reef Factory X3 Dosing Pump."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CHANNEL_NAMES, CHANNELS, CONF_SERIAL, DOMAIN
from .coordinator import ReefFactoryDoseCoordinator

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class DoseSensorDescription(SensorEntityDescription):
    """Extends SensorEntityDescription with a data key."""
    data_key: str = ""


def _build_channel_sensors(ch: int) -> tuple[DoseSensorDescription, ...]:
    label = CHANNEL_NAMES[ch]
    return (
        DoseSensorDescription(
            key=f"ch{ch}_container_current",
            data_key=f"ch{ch}_container_current",
            name=f"Channel {label} Container Level",
            native_unit_of_measurement="mL",
            state_class=SensorStateClass.MEASUREMENT,
            suggested_display_precision=1,
            icon="mdi:flask-outline",
        ),
        DoseSensorDescription(
            key=f"ch{ch}_today_dosed",
            data_key=f"ch{ch}_today_dosed",
            name=f"Channel {label} Today Dosed",
            native_unit_of_measurement="mL",
            state_class=SensorStateClass.TOTAL_INCREASING,
            suggested_display_precision=2,
            icon="mdi:water-plus-outline",
        ),
        DoseSensorDescription(
            key=f"ch{ch}_actions_today",
            data_key=f"ch{ch}_actions_today",
            name=f"Channel {label} Automated Actions Today",
            native_unit_of_measurement="actions",
            state_class=SensorStateClass.TOTAL_INCREASING,
            icon="mdi:robot-outline",
        ),
        DoseSensorDescription(
            key=f"ch{ch}_daily_dose_max",
            data_key=f"ch{ch}_daily_dose_max",
            name=f"Channel {label} Daily Target",
            native_unit_of_measurement="mL",
            state_class=SensorStateClass.MEASUREMENT,
            suggested_display_precision=1,
            icon="mdi:target",
            entity_registry_enabled_default=False,
        ),
        DoseSensorDescription(
            key=f"ch{ch}_container_capacity",
            data_key=f"ch{ch}_container_capacity",
            name=f"Channel {label} Container Capacity",
            native_unit_of_measurement="mL",
            state_class=SensorStateClass.MEASUREMENT,
            suggested_display_precision=0,
            icon="mdi:flask",
            entity_registry_enabled_default=False,
        ),
    )


SENSORS: tuple[DoseSensorDescription, ...] = tuple(
    sensor for ch in CHANNELS for sensor in _build_channel_sensors(ch)
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: ReefFactoryDoseCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        DoseSensorEntity(coordinator, description, entry)
        for description in SENSORS
    )


class DoseSensorEntity(CoordinatorEntity[ReefFactoryDoseCoordinator], SensorEntity):
    """A sensor entity backed by the X3 dose coordinator."""

    entity_description: DoseSensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ReefFactoryDoseCoordinator,
        description: DoseSensorDescription,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        serial = entry.data[CONF_SERIAL]
        self._attr_unique_id = f"{serial}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, serial)},
            name=f"X3 Dosing Pump {serial}",
            manufacturer="Reef Factory",
            model="X3 Dosing Pump",
        )

    @property
    def native_value(self) -> Any:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(self.entity_description.data_key)
