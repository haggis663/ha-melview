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
import time
import requests
import asyncio
from aiohttp import ClientError, ClientResponseError, ClientSession

from .const import DOMAIN, CONF_LOCAL, APPVERSION, HEADERS, APIVERSION


from homeassistant.components.climate.const import (
    HVACMode
)

_LOGGER = logging.getLogger(__name__)


LOCAL_DATA = """<?xml version="1.0" encoding="UTF-8"?>
<CSV>
    <CONNECT>ON</CONNECT>
    <CODE>
        <VALUE>{}</VALUE>
    </CODE>
</CSV>"""


# ---------------------------------------------------------------

# This seems to be a standard heat pump
MODE_ATA = {
    HVACMode.AUTO: 8,
    HVACMode.HEAT: 1,
    HVACMode.COOL: 3,
    HVACMode.DRY: 2,
    HVACMode.FAN_ONLY: 7
}

# This section is for a Lossney ERV (Energy Recovery Ventilator)
# Since it's not possible to add custom climate modes in home assistant,
# all Lossney modes are modelled as presets: https://developers.home-assistant.io/docs/core/entity/climate?_highlight=climate#hvac-modes`
PRESET_AUTO = "Auto"
PRESET_LOSSNAY = "Lossnay"
PRESET_BYPASS = "Bypass"

MODE_ERV = {
    PRESET_AUTO: 3,
    PRESET_LOSSNAY: 1,
    PRESET_BYPASS: 7,
}

UNIT_TYPE_ERV = "ERV"

FANSTAGES = {
    1: {5: "On"},
    2: {2: "Low", 5: "High"},
    3: {2: "Low", 3: "Medium", 5: "High"},
    4: {2: "Low", 3: "Medium Low", 5: "Medium High", 6: "High"},
    5: {1: "Low", 2: "Medium Low", 3: "Medium", 5: "Medium High", 6: "High"},
}

# ---------------------------------------------------------------


class MelViewAuthentication:
    """ Implementation to remember and refresh melview cookies.
    """

    def __init__(self, email, password):
        self._email = email
        self._password = password
        self._cookie = None

    def is_login(self):
        """ Return login status.
        """
        return self._cookie is not None


    def login(self):
        """ Generate a new login cookie.
        """
        _LOGGER.debug('trying to login')

        self._cookie = None
        req = requests.post('https://api.melview.net/api/login.aspx',
                            json={'user': self._email, 'pass': self._password,
                                  'appversion': APPVERSION},
                            headers=HEADERS)

        if req.status_code == 200:
            cks = req.cookies
            if 'auth' in cks:
                self._cookie = cks['auth']
                return True
            _LOGGER.error('missing auth cookie -> cookies: %s', cks)
        else:
            _LOGGER.error('login status code: %d', req.status_code)

        return False

    async def  asynclogin(self):
        """ Generate a new login cookie.
        """
        _LOGGER.debug('trying to login')

        self._cookie = None
        async with ClientSession() as session:
            req = await session.post('https://api.melview.net/api/login.aspx',
                    json={'user': self._email, 'pass': self._password,
                          'appversion': APPVERSION},
                    headers=HEADERS) 
        if req.status == 200:
            cks = req.cookies
            if 'auth' in cks:
                self._cookie = cks['auth'].value
                return True
            _LOGGER.error('missing auth cookie -> cookies: %s', cks)
        else:
            _LOGGER.error('login status code: %d', req.status)

        return False

    def get_cookie(self):
        """ Return authentication cookie.
        """
        return {'auth': self._cookie}

# ---------------------------------------------------------------

class MelViewZone:
    def __init__(self, id, name, status):
        self.id = id
        self.name = name
        self.status = status

# ---------------------------------------------------------------

class MelViewDevice:
    """ Handler class for a melview unit.
    """

    def __init__(self, deviceid, buildingid, friendlyname,
                 authentication, localcontrol=False):
        self._deviceid = deviceid
        self._buildingid = buildingid
        self._friendlyname = friendlyname
        self._authentication = authentication

        self._caps = None
        self._localip = localcontrol
        self.unit_type = None

        self._info_lease_seconds = 30  # Data lasts for 30s.
        self._json = None
        self._rtemp_list = []
        self._otemp_list = []
        self._zones = {}

        self.fan = FANSTAGES[3]
    
    def refresh(self):
        self._refresh_device_caps()
        self._refresh_device_info()
    async def async_refresh(self):
        await self.async_refresh_device_caps()
        await self.async_refresh_device_info()
        

    def __str__(self):
        return str(self._json)
    
    def _refresh_device_caps(self, retry=True):
        self._json = None
        self._last_info_time_s = time.time()

        req = requests.post('https://api.melview.net/api/unitcapabilities.aspx',
                            cookies=self._authentication.get_cookie(),
                            json={'unitid': self._deviceid, 'v': APIVERSION})
        if req.status_code == 200:
            self._caps = req.json()
            if self._localip and 'localip' in self._caps:
                self._localip = self._caps['localip']
            if self._caps['fanstage']:
                self.fan = FANSTAGES[self._caps['fanstage']]
            if 'hasautofan' in self._caps and self._caps['hasautofan'] == 1:
                self.fan[0] = 'auto'
            if self._caps['unittype']:
                self.unit_type = self._caps['unittype']
            self.fan_keyed = {value: key for key, value in self.fan.items()}
            return True
        if req.status_code == 401 and retry:
            _LOGGER.error('caps error 401 (trying to re-login)')
            if self._authentication.login():
                return self._refresh_device_caps(retry=False)
        else:
            _LOGGER.error('unable to retrieve caps '
                          '(invalid status code: %d)', req.status_code)
        return False
   
    def _refresh_device_info(self, retry=True):
        self._json = None
        self._last_info_time_s = time.time()

        req = requests.post('https://api.melview.net/api/unitcommand.aspx',
                            cookies=self._authentication.get_cookie(),
                            json={'unitid': self._deviceid, 'v': APIVERSION})
        if req.status_code == 200:
            self._json = req.json()
            if 'roomtemp' in self._json:
                self._rtemp_list.append(float(self._json['roomtemp']))
                # Keep only last 10 temperature values.
                self._rtemp_list = self._rtemp_list[-10:]
            if 'outdoortemp' in self._json:
                self._otemp_list.append(float(self._json['outdoortemp']))
                # Keep only last 10 temperature values.
                self._otemp_list = self._otemp_list[-10:]
            if 'zones' in self._json:
                self._zones = {z['zoneid'] : MelViewZone(z['zoneid'], z['name'], z['status']) for z in self._json['zones']}
            return True
        if req.status_code == 401 and retry:
            _LOGGER.error('info error 401 (trying to re-login)')
            if self._authentication.login():
                return self._refresh_device_info(retry=False)
        else:
            _LOGGER.error('unable to retrieve info (invalid status code: %d)',
                          req.status_code)
        return False

    async def async_refresh_device_caps(self, retry=True):
        self._json = None
        self._last_info_time_s = time.time()

        async with ClientSession() as session:
            req = await session.post('https://api.melview.net/api/unitcapabilities.aspx',
                            cookies=self._authentication.get_cookie(),
                            json={'unitid': self._deviceid, 'v': APIVERSION})
        if req.status == 200:
            self._caps = await req.json()
            if self._localip and 'localip' in self._caps:
                self._localip = self._caps['localip']
            if self._caps['fanstage']:
                self.fan = FANSTAGES[self._caps['fanstage']]
            if 'hasautofan' in self._caps and self._caps['hasautofan'] == 1:
                self.fan[0] = 'auto'
            if self._caps['unittype']:
                self.unit_type = self._caps['unittype']
            self.fan_keyed = {value: key for key, value in self.fan.items()}
            return True
        if req.status == 401 and retry:
            _LOGGER.error('caps error 401 (trying to re-login)')
            if await self._authentication.asynclogin():
                return await self.async_refresh_device_caps(retry=False)
        else:
            _LOGGER.error('unable to retrieve caps '
                          '(invalid status code: %d)', req.status)
        return False
   
    async def async_refresh_device_info(self, retry=True):
        self._json = None
        self._last_info_time_s = time.time()

        async with ClientSession() as session:
            req = await session.post('https://api.melview.net/api/unitcommand.aspx',
                            cookies=self._authentication.get_cookie(),
                            json={'unitid': self._deviceid, 'v': APIVERSION})
        if req.status == 200:
            self._json = await req.json()
            if 'roomtemp' in self._json:
                self._rtemp_list.append(float(self._json['roomtemp']))
                # Keep only last 10 temperature values.
                self._rtemp_list = self._rtemp_list[-10:]
            if 'outdoortemp' in self._json:
                self._otemp_list.append(float(self._json['outdoortemp']))
                # Keep only last 10 temperature values.
                self._otemp_list = self._otemp_list[-10:]
            if 'zones' in self._json:
                self._zones = {z['zoneid'] : MelViewZone(z['zoneid'], z['name'], z['status']) for z in self._json['zones']}
            return True
        if req.status == 401 and retry:
            _LOGGER.error('info error 401 (trying to re-login)')
            if await self._authentication.asynclogin():
                return await self.async_refresh_device_info(retry=False)
        else:
            _LOGGER.error('unable to retrieve info (invalid status code: %d)',
                          req.status)
        return False


    def _is_info_valid(self):
        if self._json is None:
            return self._refresh_device_info()

        if (time.time() - self._last_info_time_s) >= self._info_lease_seconds:
            _LOGGER.debug('current settings out of date, refreshing')
            return self._refresh_device_info()

        return True
    async def async_is_info_valid(self):
        if self._json is None:
            return await self.async_refresh_device_info()

        if (time.time() - self._last_info_time_s) >= self._info_lease_seconds:
            _LOGGER.debug('current settings out of date, refreshing')
            return await self.async_refresh_device_info()

        return True
        
    async def async_is_caps_valid(self):
        if self._caps is None:
            return await self.async_refresh_device_caps()

        return True

    def _is_caps_valid(self):
        if self._caps is None:
            return self._refresh_device_caps()

        return True
        
    async def async_send_command(self, command, retry=True):
        _LOGGER.debug('command issued %s', command)

        if not await self.async_is_info_valid():
            _LOGGER.error('data outdated, command %s failed', command)
            return False

        async with ClientSession() as session:
            req = await session.post('https://api.melview.net/api/unitcommand.aspx',
                            cookies=self._authentication.get_cookie(),
                            json={'unitid': self._deviceid, 'v': APIVERSION,
                                  'commands': command, 'lc': 1})
        if req.status == 200:
            _LOGGER.debug('command sent to remote')

            resp = await req.json()
            if self._localip:
                if 'lc' in resp:
                    local_command = req.json()['lc']
                    async with ClientSession() as session:
                        req = await session.post('http://{}/smart'.format(self._localip),
                                        data=LOCAL_DATA.format(local_command))
                    if req.status == 200:
                        _LOGGER.debug('command sent locally')
                    else:
                        _LOGGER.error('local submission failed')
                else:
                    _LOGGER.error('missing local command key')

            return True
        if req.status == 401 and retry:
            _LOGGER.error('command send error 401 (trying to relogin)')
            if await self._authentication.asynclogin():
                return await self.async_send_command(command, retry=False)
        else:
            _LOGGER.error('unable to send command (invalid status code: %d',
                          req.status)

        return False

    def _send_command(self, command, retry=True):
        _LOGGER.debug('command issued %s', command)

        if not self._is_info_valid():
            _LOGGER.error('data outdated, command %s failed', command)
            return False

        req =requests.post('https://api.melview.net/api/unitcommand.aspx',
                            cookies=self._authentication.get_cookie(),
                            json={'unitid': self._deviceid, 'v': APIVERSION,
                                  'commands': command, 'lc': 1})
        if req.status_code == 200:
            _LOGGER.debug('command sent to remote')

            resp = req.json()
            if self._localip:
                if 'lc' in resp:
                    local_command = req.json()['lc']
                    req = requests.post('http://{}/smart'.format(self._localip),
                                        data=LOCAL_DATA.format(local_command))
                    if req.status_code == 200:
                        _LOGGER.debug('command sent locally')
                    else:
                        _LOGGER.error('local submission failed')
                else:
                    _LOGGER.error('missing local command key')

            return True
        if req.status_code == 401 and retry:
            _LOGGER.error('command send error 401 (trying to relogin)')
            if self._authentication.login():
                return self._send_command(command, retry=False)
        else:
            _LOGGER.error('unable to send command (invalid status code: %d',
                          req.status_code)

        return False

    def force_update(self):
        """ Force info refresh
        """
        return self._refresh_device_info()

    async def async_force_update(self):
        """ Force info refresh
        """
        return await self.async_refresh_device_info()


    def get_id(self):
        """ Get device ID.
        """
        return self._deviceid

    def get_friendly_name(self):
        """ Get customised device name.
        """
        return self._friendlyname

    def get_precision_halves(self):
        """ Get unit support for half degrees.
        """
        if not self._is_caps_valid():
            return False

        return 'halfdeg' in self._caps and self._caps['halfdeg'] == 1

    def get_temperature(self):
        """ Get set temperature.
        """
        if not self._is_info_valid():
            return 0

        return float(self._json['settemp'])

    async def async_get_temperature(self):
        """ Get set temperature.
        """
        if not await self.async_is_info_valid():
            return 0

        return float(self._json['settemp'])

    def get_room_temperature(self):
        """ Get current room temperature.
        """
        if not self._is_info_valid():
            return 0

        if not self._rtemp_list:
            return 0  # Avoid div 0.

        return round(sum(self._rtemp_list) / len(self._rtemp_list), 1)

    async def async_get_room_temperature(self):
        """ Get current room temperature.
        """
        if not await self.async_is_info_valid():
            return 0

        if not self._rtemp_list:
            return 0  # Avoid div 0.

        return round(sum(self._rtemp_list) / len(self._rtemp_list), 1)

    def get_outside_temperature(self):
        """ Get current outside temperature.
        """
        if not 'hasoutdoortemp' in self._caps or self._caps['hasoutdoortemp'] == 0:
            _LOGGER.error('outdoor temperature not supported')
            return 0

        if not self._is_info_valid():
            return 0

        if not self._otemp_list:
            return 0  # Avoid div 0.

        return round((sum(self._otemp_list) / len(self._otemp_list)), 1)

    def get_speed(self):
        """ Get the set fan speed.
        """
        if not self._is_info_valid():
            return 'Auto'

        for key, val in self.fan_keyed.items():
            if self._json['setfan'] == val:
                return key

        return 'Auto'
    async def async_get_speed(self):
        """ Get the set fan speed.
        """
        if not await self.async_is_info_valid():
            return 'Auto'

        for key, val in self.fan_keyed.items():
            if self._json['setfan'] == val:
                return key

        return 'Auto'

    def get_mode(self):
        """ Get the set mode.
        """
        if self.unit_type == UNIT_TYPE_ERV:
            return None

        if not self._is_info_valid():
            return HVACMode.AUTO

        if self.is_power_on():
            for key, val in MODE_ATA.items():
                if self._json['setmode'] == val:
                    return key

        return HVACMode.AUTO
    
    def get_preset(self):
        """ Get the set preset (for ERV units).
        """
        if self.unit_type != UNIT_TYPE_ERV:
            return None

        if not self._is_info_valid():
            return PRESET_AUTO

        if self.is_power_on():
            for key, val in MODE_ERV.items():
                if self._json['setmode'] == val:
                    return key

        return PRESET_AUTO


    async def async_get_mode(self):
        """ Get the set mode.
        """
        if self.unit_type == UNIT_TYPE_ERV:
            return None

        if not await self.async_is_info_valid():
            return HVACMode.AUTO

        if await self.async_is_power_on():
            for key, val in MODE_ATA.items():
                if self._json['setmode'] == val:
                    return key

        return HVACMode.AUTO

    async def async_get_preset(self):
        """ Get the set preset (for ERV units).
        """
        if self.unit_type != UNIT_TYPE_ERV:
            return None

        if not await self.async_is_info_valid():
            return PRESET_AUTO

        if await self.async_is_power_on():
            for key, val in MODE_ERV.items():
                if self._json['setmode'] == val:
                    return key

        return PRESET_AUTO

    def get_zone(self, zoneid):
        return self._zones.get(zoneid)

    def get_zones(self):
        return self._zones.values()

    def get_unit_type(self):
        """ Get the unit type.
        """
        return self.unit_type

    def is_power_on(self):
        """ Check unit is on.
        """
        if not self._is_info_valid():
            return False

        return self._json['power']

    async def async_is_power_on(self):
        """ Check unit is on.
        """
        if not await self.async_is_info_valid():
            return False

        return self._json['power']

    def set_temperature(self, temperature):
        """ Set the target temperature.
        """
        mode = self.get_mode()
        min_temp = self._caps['max'][str(MODE_ATA[mode])]['min']
        max_temp = self._caps['max'][str(MODE_ATA[mode])]['max']
        if temperature < min_temp:
            _LOGGER.error('temp %.1f lower than min %d for mode %d',
                          temperature, min_temp, mode)
            return False
        if temperature > max_temp:
            _LOGGER.error('temp %.1f greater than max %d for mode %d',
                          temperature, max_temp, mode)
            return False
        return self._send_command('TS{:.2f}'.format(temperature))

    async def async_set_temperature(self, temperature):
        """ Set the target temperature.
        """
        mode = await self.async_get_mode()
        min_temp =19
        max_temp=28
        if str(MODE_ATA[mode]) in self._caps['max']:
            min_temp = self._caps['max'][str(MODE_ATA[mode])]['min']
            max_temp = self._caps['max'][str(MODE_ATA[mode])]['max']
        else:
            min_temp = self._caps['max']['8']['min']
            max_temp = self._caps['max']['8']['max']
        if temperature < min_temp:
            _LOGGER.error('temp %.1f lower than min %d for mode %d',
                          temperature, min_temp, mode)
            return False
        if temperature > max_temp:
            _LOGGER.error('temp %.1f greater than max %d for mode %d',
                          temperature, max_temp, mode)
            return False
        return await self.async_send_command('TS{:.2f}'.format(temperature))

    async def async_set_speed(self, speed):
        """ Set the fan speed.
        """
        if not await self.async_is_power_on():
            # Try turn on the unit if off.
            if not await self.async_power_on():
                return False

        if speed not in self.fan_keyed.keys():
            _LOGGER.error('fan speed %d not supported', speed)
            return False
        return await self.async_send_command('FS{:.2f}'.format(self.fan_keyed[speed]))

    def set_speed(self, speed):
        """ Set the fan speed.
        """
        if not self.is_power_on():
            # Try turn on the unit if off.
            if not self.power_on():
                return False

        if speed not in self.fan_keyed.keys():
            _LOGGER.error('fan speed %d not supported', speed)
            return False
        return self._send_command('FS{:.2f}'.format(self.fan_keyed[speed]))

    async def async_set_mode(self, mode):
        """ Set operating mode.
        """
        if not await self.async_is_power_on():
            # Try turn on the unit if off.
            if not await self.async_power_on():
                return False

        if mode == 'Auto' and (not 'hasautomode' in self._caps or self._caps['hasautomode'] == 0):
            _LOGGER.error('auto mode not supported')
            return False
        if mode == 'Dry' and (not 'hasdrymode' in self._caps or self._caps['hasdrymode'] == 0):
            _LOGGER.error('dry mode not supported')
            return False
        if mode != 'Cool' and ('hascoolonly' in self._caps and self._caps['hascoolonly'] == 1):
            _LOGGER.error('only cool mode supported')
            return False
        if mode not in MODE_ATA.keys():
            _LOGGER.error('mode %d not supported', mode)
            return False
        return await self.async_send_command('MD{}'.format(MODE_ATA[mode]))


    def set_mode(self, mode):
        """ Set operating mode.
        """
        if not self.is_power_on():
            # Try turn on the unit if off.
            if not self.power_on():
                return False

        if mode == 'Auto' and (not 'hasautomode' in self._caps or self._caps['hasautomode'] == 0):
            _LOGGER.error('auto mode not supported')
            return False
        if mode == 'Dry' and (not 'hasdrymode' in self._caps or self._caps['hasdrymode'] == 0):
            _LOGGER.error('dry mode not supported')
            return False
        if mode != 'Cool' and ('hascoolonly' in self._caps and self._caps['hascoolonly'] == 1):
            _LOGGER.error('only cool mode supported')
            return False
        if mode not in MODE_ATA.keys():
            _LOGGER.error('mode %d not supported', mode)
            return False
        return self._send_command('MD{}'.format(MODE_ATA[mode]))
    
    def set_preset(self, preset):
        """ Set operating preset (for ERV units).
        """
        if self.unit_type != UNIT_TYPE_ERV:
            _LOGGER.error('presets not supported for non-ERV units')
            return False

        if not self.is_power_on():
            # Try turn on the unit if off.
            if not self.power_on():
                return False

        if preset not in MODE_ERV.keys():
            _LOGGER.error('preset %s not supported', preset)
            return False
        return self._send_command('MD{}'.format(MODE_ERV[preset]))
    
    async def async_set_preset(self, preset):
        """ Set operating preset (for ERV units).
        """
        if self.unit_type != UNIT_TYPE_ERV:
            _LOGGER.error('presets not supported for non-ERV units')
            return False

        if not await self.async_is_power_on():
            # Try turn on the unit if off.
            if not await self.async_power_on():
                return False

        if preset not in MODE_ERV.keys():
            _LOGGER.error('preset %s not supported', preset)
            return False

        return await self.async_send_command('MD{}'.format(MODE_ERV[preset]))

    async def async_enable_zone(self, zoneid):
        """ Turn on a zone.
        """
        return await self.async_send_command(f"Z{zoneid}1")

    def enable_zone(self, zoneid):
        """ Turn on a zone.
        """
        return self._send_command(f"Z{zoneid}1")

    async def async_disable_zone(self, zoneid):
        """ Turn off a zone.
        """
        return await self.async_send_command(f"Z{zoneid}0")

    def disable_zone(self, zoneid):
        """ Turn off a zone.
        """
        return self._send_command(f"Z{zoneid}0")

    async def async_power_on(self):
        """ Turn on the unit.
        """
        return await self.async_send_command('PW1')

    def power_on(self):
        """ Turn on the unit.
        """
        return self._send_command('PW1')
        
    async def async_power_off(self):
        """ Turn off the unit.
        """
        return await self.async_send_command('PW0')

    def power_off(self):
        """ Turn off the unit.
        """
        return self._send_command('PW0')

# ---------------------------------------------------------------


class MelView:
    """ Handler for multiple melview devices under one user.
    """

    def __init__(self, authentication, localcontrol=False):
        self._authentication = authentication
        self._unitcount = 0

        self._localcontrol = localcontrol

    def get_devices_list(self, retry=True):
        """ Return all the devices found, as handlers.
        """
        devices = []

        req = requests.post('https://api.melview.net/api/rooms.aspx',
                            json={'unitid': 0},
                            headers=HEADERS,
                            cookies=self._authentication.get_cookie())
        if req.status_code == 200:
            reply = req.json()
            for building in reply:
                for unit in building['units']:
                    devices.append(MelViewDevice(unit['unitid'],
                                                 building['buildingid'],
                                                 unit['room'],
                                                 self._authentication,
                                                 self._localcontrol))

        elif req.status_code == 401 and retry:
            _LOGGER.error('device list error 401 (trying to re-login)')
            if self._authentication.login():
                return self.get_devices_list(retry=False)
        else:
            _LOGGER.error('failed to get device list (status code invalid: %d)',
                          req.status_code)

        return devices

    async def async_get_devices_list(self, retry=True):
        """ Return all the devices found, as handlers.
        """
        devices = []

        async with ClientSession() as session:
            req = await session.post('https://api.melview.net/api/rooms.aspx',
                            json={'unitid': 0},
                            headers=HEADERS,
                            cookies=self._authentication.get_cookie())
        if req.status == 200:
            reply = await req.json()
            for building in reply:
                for unit in building['units']:
                    melViewDevice= MelViewDevice(unit['unitid'],
                                                 building['buildingid'],
                                                 unit['room'],
                                                 self._authentication,
                                                 self._localcontrol)
                    await melViewDevice.async_refresh()
                    devices.append(melViewDevice)

        elif req.status == 401 and retry:
            _LOGGER.error('device list error 401 (trying to re-login)')
            if await self._authentication.asynclogin():
                return await self.async_get_devices_list(retry=False)
        else:
            _LOGGER.error('failed to get device list (status code invalid: %d)',
                          req.status)

        return devices
