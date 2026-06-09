"""Sensor platform for Essensplaner."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType

from .coordinator import EssensplanerConfigEntry, EssensplanerStatisticsCoordinator
from .entity import EssensplanerEntity
from .models import Statistics

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class EssensplanerSensorDescription(SensorEntityDescription):
    """Sensor description."""

    value_fn: Callable[[Statistics], StateType]


SENSOR_TYPES: tuple[EssensplanerSensorDescription, ...] = (
    EssensplanerSensorDescription(
        key="recipes",
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda s: s.total_recipes,
    ),
    EssensplanerSensorDescription(
        key="categories",
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda s: s.total_categories,
    ),
    EssensplanerSensorDescription(
        key="tags",
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda s: s.total_tags,
    ),
    EssensplanerSensorDescription(
        key="tools",
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda s: s.total_tools,
    ),
    EssensplanerSensorDescription(
        key="cookbooks",
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda s: s.total_cookbooks,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EssensplanerConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up sensors."""
    coordinator = entry.runtime_data.statistics_coordinator
    async_add_entities(
        EssensplanerStatisticSensor(coordinator, description)
        for description in SENSOR_TYPES
    )


class EssensplanerStatisticSensor(EssensplanerEntity, SensorEntity):
    """Statistics sensor."""

    entity_description: EssensplanerSensorDescription
    coordinator: EssensplanerStatisticsCoordinator

    def __init__(
        self,
        coordinator: EssensplanerStatisticsCoordinator,
        description: EssensplanerSensorDescription,
    ) -> None:
        """Initialize sensor."""
        super().__init__(coordinator, description.key)
        self.entity_description = description
        self._attr_translation_key = description.key

    @property
    def native_value(self) -> StateType:
        """Return sensor value."""
        return self.entity_description.value_fn(self.coordinator.data)
