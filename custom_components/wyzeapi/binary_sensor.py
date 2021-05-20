import logging
import time
from datetime import timedelta
from typing import List

from homeassistant.const import ATTR_ATTRIBUTION
from wyzeapy.base_client import DeviceTypes, Device, AccessTokenError, PropertyIDs, EventTypes
from wyzeapy.client import Client
from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    DEVICE_CLASS_MOTION,
    DEVICE_CLASS_SOUND,
    DEVICE_CLASS_GAS,
    DEVICE_CLASS_SMOKE,
    DEVICE_CLASS_OPENING,    
)

from .const import DOMAIN, CONF_CAM_MOTION, CONF_CAM_SOUND, CONF_CAM_SMOKE, CONF_CAM_CO2, CONF_WYZE_MOTION, CONF_WYZE_CONTACT
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)
ATTRIBUTION = "Data provided by Wyze"
SCAN_INTERVAL = timedelta(seconds=20)


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities):
    _LOGGER.debug("""Creating new WyzeApi binary sensor component""")
    client = hass.data[DOMAIN][config_entry.entry_id]["wyze_client"]

    def get_devices() -> List[Device]:
        try:
            devices = client.get_devices()
        except AccessTokenError as e:
            _LOGGER.warning(e)
            client.reauthenticate()
            devices = client.get_devices()

        return devices

    devices = await hass.async_add_executor_job(get_devices)

    sensor = []
    for device in devices:
        try:
            device_type = DeviceTypes(device.product_type)
            if device_type == DeviceTypes.CAMERA:
                if config_entry.options.get(CONF_CAM_MOTION) in (None, True):
                    sensor.append(WyzeCameraSensor(client, device, EventTypes.MOTION))
                if config_entry.options.get(CONF_CAM_SOUND):
                    sensor.append(WyzeCameraSensor(client, device, EventTypes.SOUND))
                if config_entry.options.get(CONF_CAM_SMOKE):
                    sensor.append(WyzeCameraSensor(client, device, EventTypes.SMOKE))
                if config_entry.options.get(CONF_CAM_CO2):
                    sensor.append(WyzeCameraSensor(client, device, EventTypes.CO2))
            elif device_type == DeviceTypes.MOTION_SENSOR:
                if config_entry.options.get(CONF_WYZE_MOTION):
                    sensor.append(WyzeSensor(client, device, EventTypes.MOTION))
            elif device_type == DeviceTypes.CONTACT_SENSOR:
                if config_entry.options.get(CONF_WYZE_CONTACT):
                    sensor.append(WyzeSensor(client, device, EventTypes.TRIGGERED))
        except ValueError as e:
            _LOGGER.warning("{}: Please report this error to https://github.com/JoshuaMulliken/ha-wyzeapi".format(e))

    async_add_entities(sensor, True)


class WyzeCameraSensor(BinarySensorEntity):
    _on: bool
    _available: bool

    def __init__(self, wyzeapi_client: Client, device: Device, sensor_class: EventTypes = EventTypes.MOTION):
        self._client = wyzeapi_client
        self._device = device
        self._sensor_class = sensor_class
        self._last_event = int(str(int(time.time())) + "000")

    @property
    def device_info(self):
        return {
            "identifiers": {
                (DOMAIN, self._device.mac)
            },
            "name": self.name,
            "manufacturer": "WyzeLabs",
            "model": self._device.product_model
        }

    @property
    def available(self) -> bool:
        return self._available

    @property
    def icon(self):
        """Return the icon."""
        if self._sensor_class == EventTypes.SOUND:
            return "hass:music-note" if self._on else "hass:music-note-off"
        elif self._sensor_class == EventTypes.CO2:
            return "mdi:molecule-co2"
        elif self._sensor_class == EventTypes.SMOKE:
            return "mdi:smoking" if self._on else "mdi:smoking-off"
        else:
            return "hass:run" if self._on else "hass:walk"

    @property
    def name(self):
        """Return the display name of this switch."""
        return self._device.nickname

    @property
    def is_on(self):
        """Return true if switch is on."""
        return self._on

    @property
    def unique_id(self):
        if self._sensor_class == EventTypes.SOUND:
            return "{}-sound".format(self._device.mac)
        elif self._sensor_class == EventTypes.CO2:
            return "{}-co2".format(self._device.mac)
        elif self._sensor_class == EventTypes.SMOKE:
            return "{}-smoke".format(self._device.mac)
        else:
            return "{}-motion".format(self._device.mac)

    @property
    def device_state_attributes(self):
        """Return device attributes of the entity."""
        return {
            ATTR_ATTRIBUTION: ATTRIBUTION,
            "state": self.is_on,
            "available": self.available,
            "device model": self._device.product_model,
            "mac": self.unique_id
        }

    @property
    def device_class(self):
        if self._sensor_class == EventTypes.SOUND:
            return DEVICE_CLASS_SOUND
        elif self._sensor_class == EventTypes.CO2:
            return DEVICE_CLASS_GAS 
        elif self._sensor_class == EventTypes.SMOKE:
            return DEVICE_CLASS_SMOKE
        else:
            return DEVICE_CLASS_MOTION

    def update(self):
        try:
            device_info = self._client.get_info(self._device)
        except AccessTokenError:
            self._client.reauthenticate()
            device_info = self._client.get_info(self._device)

        for property_id, value in device_info:
            if property_id == PropertyIDs.AVAILABLE:
                self._available = True if value == "1" else False

        latest_event = self._client.get_latest_event(self._device, self._sensor_class)
        if latest_event is not None:
            if latest_event.event_ts > self._last_event:
                self._on = True
                self._last_event = latest_event.event_ts
            else:
                self._on = False
                self._last_event = latest_event.event_ts
        else:
            self._on = False

class WyzeSensor(BinarySensorEntity):
    _on: bool
    _available: bool

    def __init__(self, wyzeapi_client: Client, device: Device, sensor_class: EventTypes = EventTypes.MOTION):
        self._client = wyzeapi_client
        self._device = device
        self._sensor_class = sensor_class
        self._last_event = int(str(int(time.time())) + "000")

    @property
    def device_info(self):
        return {
            "identifiers": {
                (DOMAIN, self._device.mac)
            },
            "name": self.name,
            "manufacturer": "WyzeLabs",
            "model": self._device.product_model
        }

    @property
    def available(self) -> bool:
        return self._available

    @property
    def icon(self):
        """Return the icon."""
        if self._sensor_class == EventTypes.TRIGGERED:
            return "hass:door-closed" if self._on else "hass:door-open"
        else:
            return "hass:run" if self._on else "hass:walk"

    @property
    def name(self):
        """Return the display name of this switch."""
        return self._device.nickname

    @property
    def is_on(self):
        """Return true if switch is on."""
        return self._on

    @property
    def unique_id(self):
        if self._sensor_class == EventTypes.TRIGGERED:
            return "{}-trigger".format(self._device.mac)
        else:
            return "{}-motion".format(self._device.mac)

    @property
    def device_state_attributes(self):
        """Return device attributes of the entity."""
        return {
            ATTR_ATTRIBUTION: ATTRIBUTION,
            "state": self.is_on,
            "available": self.available,
            "device model": self._device.product_model,
            "mac": self.unique_id
        }

    @property
    def extra_state_attributes(self):
        """Return the state attributes of the sensor."""
        return {
            "device_model": self._device.product_model,
            "rssi": self._device.device_params["rssi"],
            "voltage": self._device.device_params["voltage"],
            "mac": self._device.mac
            }

    @property
    def device_class(self):
        if self._sensor_class == EventTypes.TRIGGERED:
            return DEVICE_CLASS_OPENING
        else:
            return DEVICE_CLASS_MOTION

    def update(self):
        try:
            device_info = self._client.get_info(self._device)
        except AccessTokenError:
            self._client.reauthenticate()
            device_info = self._client.get_info(self._device)

        for property_id, value in device_info:
            if property_id == PropertyIDs.AVAILABLE:
                self._available = True if value == "1" else False

        latest_event = self._client.get_latest_event(self._device, EventTypes.ALL)
        if latest_event is not None:
            if latest_event.event_ts > self._last_event:
                self._on = True
                self._last_event = latest_event.event_ts
            else:
                self._on = False
                self._last_event = latest_event.event_ts
        else:
            self._on = False

