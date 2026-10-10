"""Filter warning for units that report one.

A Lossnay sets `changefilter` in its status response when its filters are due
for cleaning or replacement. Like the sensors, this reads the response the
climate entity already fetches and adds no API requests.
"""
from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)

from .const import DOMAIN


async def async_setup_entry(hass, entry, async_add_entities):
    """ Add a filter sensor for each unit that reports `changefilter`.
    """
    async_add_entities(
        [
            MelViewFilterSensor(device)
            for device in hass.data[DOMAIN][entry.entry_id]
            if device.get_status_value('changefilter') is not None
        ], False
    )


class MelViewFilterSensor(BinarySensorEntity):
    """ On when the unit says its filter needs attention.
    """

    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, device):
        self._device = device
        self._attr_name = 'MelView {} Filter'.format(
            device.get_friendly_name())
        self._attr_unique_id = '{}-changefilter'.format(device.get_id())

    @property
    def is_on(self):
        """ True when the unit reports the filter is due.
        """
        value = self._device.get_status_value('changefilter')
        if value is None:
            return None
        return str(value) == '1'
