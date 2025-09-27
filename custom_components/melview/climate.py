#!/usr/local/bin/python3

'''
    Author: zacharyrs

    How to install:
        Refer to README.md

    License:
                DO WHAT THE FUCK YOU WANT TO PUBLIC LICENSE
                        Version 2, December 2004

        Everyone is permitted to copy and distribute verbatim or modified
        copies of this license document, and changing it is allowed as long
        as the name is changed.

                  DO WHAT THE FUCK YOU WANT TO PUBLIC LICENSE
          TERMS AND CONDITIONS FOR COPYING, DISTRIBUTION AND MODIFICATION

         0. You just DO WHAT THE FUCK YOU WANT TO.
'''

import logging

from homeassistant.components.climate.const import (
    HVACMode,
    ClimateEntityFeature
)


from homeassistant.components.climate import ClimateEntity
from homeassistant.const import (
    UnitOfTemperature,
    ATTR_TEMPERATURE,
    PRECISION_HALVES,
    PRECISION_WHOLE,
    STATE_OFF
)

from .melview import MODE_ERV, UNIT_TYPE_ERV, MelViewAuthentication, MelView, MODE_ATA

_LOGGER = logging.getLogger(__name__)

DOMAIN = 'melview'
REQUIREMENTS = ['requests']
DEPENDENCIES = []

HVAC_MODES = [HVACMode.AUTO, HVACMode.COOL, HVACMode.DRY, HVACMode.FAN_ONLY, HVACMode.HEAT, HVACMode.OFF]

# ---------------------------------------------------------------

class MelViewClimate(ClimateEntity):
    """ Melview handler for HomeAssistants
    """
    def __init__(self, device):
        self._enable_turn_on_off_backwards_compatibility = False
        self._device = device

        self._name = 'MelView {}'.format(device.get_friendly_name())
        self._unique_id = device.get_id()
    
        if self._device.get_unit_type() == UNIT_TYPE_ERV:
            self._operations_list = []
            self.preset_list = [x for x in MODE_ERV]
        else:
            self._operations_list = [x for x in MODE_ATA] + [HVACMode.OFF]
            self.preset_list = None
        
        self._speeds_list = [x for x in self._device.fan_keyed]

        self._precision = PRECISION_WHOLE
        self._target_step = 1.0
        if self._device.get_precision_halves():
            self._precision = PRECISION_HALVES
            self._target_step = 0.5

        self._current_temp = self._device.get_room_temperature()
        self._target_temp = self._device.get_temperature()

        self._mode = self._device.get_mode()
        self._preset = self._device.get_preset()
        self._speed = self._device.get_speed()

        self._state = STATE_OFF
        if self._device.is_power_on():
            self._state = self._mode


    def update(self):
        """ Update device properties
        """
        _LOGGER.debug('updating state')
        self._device.force_update()

        self._precision = PRECISION_WHOLE
        self._target_step = 1.0
        if self._device.get_precision_halves():
            self._precision = PRECISION_HALVES
            self._target_step = 0.5

        self._current_temp = self._device.get_room_temperature()
        self._target_temp = self._device.get_temperature()

        self._mode = self._device.get_mode()
        self._preset = self._device.get_preset()
        self._speed = self._device.get_speed()

        self._state = self._mode
        
        if not self._device.is_power_on():
            self._mode = 'off'
            self._state = STATE_OFF

    async def async_update(self):
        """ Update device properties
        """
        _LOGGER.debug('updating state')
        await self._device.async_force_update()

        self._precision = PRECISION_WHOLE
        self._target_step = 1.0
        if self._device.get_precision_halves():
            self._precision = PRECISION_HALVES
            self._target_step = 0.5

        self._current_temp = await self._device.async_get_room_temperature()
        self._target_temp = self._device.get_temperature()

        self._mode = await self._device.async_get_mode()
        self._preset = await self._device.async_get_preset()
        self._speed = await self._device.async_get_speed()

        self._state = self._mode
        
        if not await self._device.async_is_power_on():
            self._mode = 'off'
            self._state = STATE_OFF

    @property
    def name(self):
        """ Diplay name for HASS
        """
        return self._name


    @property
    def unique_id(self):
        """ Get unique_id for HASS
        """
        return self._unique_id


    @property
    def supported_features(self):
        """ Let HASS know feature support
            TODO: Handle looking at the device features?
        """
        if self._device.get_unit_type() == UNIT_TYPE_ERV:
          return (ClimateEntityFeature.PRESET_MODE | ClimateEntityFeature.FAN_MODE | ClimateEntityFeature.TURN_ON | ClimateEntityFeature.TURN_OFF)
        else:
          return (ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.FAN_MODE | ClimateEntityFeature.TURN_ON | ClimateEntityFeature.TURN_OFF)

    @property
    def should_poll(self):
        """ Ensure HASS polls the unit
        """
        return True


    @property
    def state(self):
        """ Return the current state.
        """
        return self._state


    @property
    def is_on(self):
        """ Check unit is on
        """
        return self._state != STATE_OFF


    @property
    def precision(self):
        """ Return the precision of the system.
        """
        return self._precision


    @property
    def temperature_unit(self):
        """ Define unit for temperature
        """
        return UnitOfTemperature.CELSIUS


    @property
    def current_temperature(self):
        """ Get the current room temperature
        """
        return self._current_temp


    @property
    def target_temperature(self):
        """ Get the target temperature
        """
        return self._target_temp


    # TODO
    # @property
    # def min_temp(self):
    #     """ Return the minimum temperature
    #     """
    #     return convert_temperature(DEFAULT_MIN_TEMP, TEMP_CELSIUS,
    #                                self.temperature_unit)


    # @property
    # def max_temp(self):
    #     """ Return the maximum temperature
    #     """
    #     return convert_temperature(DEFAULT_MAX_TEMP, TEMP_CELSIUS,
    #                                self.temperature_unit)


    @property
    def target_temperature_step(self):
        """ Return the supported step of target temperature
        """
        return self._target_step


    @property
    def hvac_mode(self):
        """ Get the current operating mode
        """
        return self._mode


    @property
    def hvac_modes(self):
        """ Get possible operating modes
        """
        return self._operations_list

    @property
    def preset_mode(self):
        """ Get the current preset mode
        """
        return self._preset

    @property
    def preset_modes(self):
        """ Get possible preset modes
        """
        return self.preset_list


    @property
    def fan_mode(self):
        """ Check the unit fan speed
        """
        return self._speed


    @property
    def fan_modes(self):
        """ Get the possible fan speeds
        """
        return self._speeds_list

    async def async_set_temperature(self, **kwargs) -> None:
        """ Set the target temperature
        """
        temp = kwargs.get(ATTR_TEMPERATURE)
        if temp is not None:
            _LOGGER.debug('setting temp %d', temp)
            if await self._device.async_set_temperature(temp):
                self._current_temp = temp


    def set_temperature(self, **kwargs):
        """ Set the target temperature
        """
        temp = kwargs.get(ATTR_TEMPERATURE)
        if temp is not None:
            _LOGGER.debug('setting temp %d', temp)
            if self._device.set_temperature(temp):
                self._current_temp = temp

    async def async_set_fan_mode(self, fan_mode) -> None:
        """ Set the fan speed
        """
        speed = fan_mode
        _LOGGER.debug('set fan mode: %s', speed)
        if await self._device.async_set_speed(speed):
            self._speed = speed
            self._mode = self._device.get_mode()
            self._state = self._mode


    def set_fan_mode(self, speed):
        """ Set the fan speed
        """
        _LOGGER.debug('set fan mode: %s', speed)
        if self._device.set_speed(speed):
            self._speed = speed
            self._mode = self._device.get_mode()
            self._state = self._mode

    async def async_set_hvac_mode(self, hvac_mode) -> None:
        _LOGGER.debug('set mode: %s', hvac_mode)
        if hvac_mode == 'off':
            await self.async_turn_off()
        elif await self._device.async_set_mode(hvac_mode):
            self._mode = hvac_mode
            self._state = hvac_mode
        
    def set_hvac_mode(self, mode):
        """ Set the operation mode
        """
        _LOGGER.debug('set mode: %s', mode)
        if mode == 'off':
            self.turn_off()
        elif self._device.set_mode(mode):
            self._mode = mode
            self._state = mode
    
    def set_preset_mode(self, preset_mode):
        """Set new target preset mode."""
        if self._device.set_preset(preset_mode):
            self._preset = preset_mode

    async def async_set_preset_mode(self, preset_mode):
        """Set new target preset mode."""
        if await self._device.async_set_preset(preset_mode):
            self._preset = preset_mode

    async def async_turn_on(self) ->None:
        """ Turn on the unit
        """
        _LOGGER.debug('power on')
        if await self._device.async_power_on():
            self._mode = self._device.get_mode()
            self._state = self._mode

    def turn_on(self):
        """ Turn on the unit
        """
        _LOGGER.debug('power on')
        if self._device.power_on():
            self._mode = self._device.get_mode()
            self._state = self._mode

    async def async_turn_off(self) -> None:
        """ Turn off the unit
        """
        _LOGGER.debug('power off')
        if await self._device.async_power_off():
            self._mode = 'off'
            self._state = STATE_OFF

    def turn_off(self):
        """ Turn off the unit
        """
        _LOGGER.debug('power off')
        if self._device.power_off():
            self._mode = 'off'
            self._state = STATE_OFF

# ---------------------------------------------------------------

def setup_platform(hass, config, add_devices, discovery_info=None):
    """ Set up the HASS component
    """
    _LOGGER.debug('adding component')

    # email = config.get('email')
    # password = config.get('password')
    # local = config.get('local')
    email = config[DOMAIN][CONF_EMAIL]
    password = config[DOMAIN][CONF_PASSWORD]
    local = config[DOMAIN][CONF_LOCAL]

    if email is None:
        _LOGGER.error('no email provided')
        return False

    if password is None:
        _LOGGER.error('no password provided')
        return False

    if local is None:
        _LOGGER.warning('local unspecified, defaulting to false')
        local = False

    mv_auth = MelViewAuthentication(email, password)
    if not mv_auth.login():
        _LOGGER.error('login combination')
        return False

    melview = MelView(mv_auth, localcontrol=local)

    device_list = []

    devices = melview.get_devices_list()
    for device in devices:
        _LOGGER.debug('new device: %s', device.get_friendly_name())
        device_list.append(device)

    add_devices(device_list)

    _LOGGER.debug('component successfully added')
    return True

async def _async_setup_platform(hass, config, add_devices, discovery_info=None):
    """ Set up the HASS component
    """
    _LOGGER.debug('adding component')

    # email = config.get('email')
    # password = config.get('password')
    # local = config.get('local')
    email = config[DOMAIN][CONF_EMAIL]
    password = config[DOMAIN][CONF_PASSWORD]
    local = config[DOMAIN][CONF_LOCAL]

    if email is None:
        _LOGGER.error('no email provided')
        return False

    if password is None:
        _LOGGER.error('no password provided')
        return False

    if local is None:
        _LOGGER.warning('local unspecified, defaulting to false')
        local = False

    mv_auth = MelViewAuthentication(email, password)
    result= await mv_auth.asynclogin()
    if not result:
        _LOGGER.error('login combination')
        return False

    melview = MelView(mv_auth, localcontrol=local)

    device_list = []

    devices = await melview.async_get_devices_list()
    for device in devices:
        await device.async_refresh()
        _LOGGER.debug('new device: %s', device.get_friendly_name())
        device_list.append(MelViewClimate(device))

    add_devices(device_list)

    _LOGGER.debug('component successfully added')
    return True

async def async_setup_entry(
    hass, entry, async_add_entities
) -> None:
    """Set up MelView device climate based on config_entry."""
    mel_devices = hass.data[DOMAIN][entry.entry_id]
    
    async_add_entities(
        [   
            MelViewClimate(mel_device)
            for mel_device in mel_devices
        ],False
    )

 
# ---------------------------------------------------------------
