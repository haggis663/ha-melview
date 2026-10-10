"""Sensors for readings MelView reports alongside a unit's climate state.

A Lossnay (unit type ERV) reports the outdoor air temperature at its intake,
plus supply and exhaust air temperatures and its core efficiency. Units with
an outdoor temperature capability report `outdoortemp` too. None of these
were exposed before.

The values come from the status response the climate entity already fetches,
so these sensors add no requests to the MelView API.
"""
import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, UnitOfTemperature

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# (status key, name, unit, device class, scale)
SENSOR_TYPES = (
    ('outdoortemp', 'Outdoor temperature',
     UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE, 1),
    ('supplytemp', 'Supply air temperature',
     UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE, 1),
    ('exhausttemp', 'Exhaust air temperature',
     UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE, 1),
    # Reported as a fraction, e.g. 0.9.
    ('coreefficiency', 'Core efficiency', PERCENTAGE, None, 100),
)


async def async_setup_entry(hass, entry, async_add_entities):
    """ Add a sensor for each reading a unit actually reports.
    """
    entities = []
    for device in hass.data[DOMAIN][entry.entry_id]:
        for key, name, unit, device_class, scale in SENSOR_TYPES:
            if device.get_status_value(key) is None:
                continue
            entities.append(MelViewSensor(device, key, name, unit,
                                          device_class, scale))
    async_add_entities(entities, False)


class MelViewSensor(SensorEntity):
    """ One numeric field from a unit's status response.
    """

    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, device, key, name, unit, device_class, scale):
        self._device = device
        self._key = key
        self._scale = scale
        self._attr_name = 'MelView {} {}'.format(
            device.get_friendly_name(), name)
        self._attr_unique_id = '{}-{}'.format(device.get_id(), key)
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class

    @property
    def native_value(self):
        """ Latest value from the last status response.
        """
        value = self._device.get_status_value(self._key)
        if value is None:
            return None
        try:
            return round(float(value) * self._scale, 1)
        except (TypeError, ValueError):
            _LOGGER.debug('unexpected %s value: %r', self._key, value)
            return None
