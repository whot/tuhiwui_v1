import kete
import threading
import json

from gi.repository import GObject, Gio, GLib

from openapi_server.models.api_response import ApiResponse  # noqa: E501
from openapi_server.models.device import Device  # noqa: E501
from openapi_server import util

class Tuhi(object):
    _instance = None

    @classmethod
    def tuhi(cls):
        if cls._instance is None:
            cls._instance = Tuhi()
        return cls._instance

    def __init__(self):
        # We need the glib mainloop to handle dbus stuff, so let's push it
        # to a separate thread
        self._mainloop = GLib.MainLoop.new(None, False)
        self._glib_thread = threading.Thread(target=self._mainloop.run)
        self._glib_thread.daemon = True
        self._glib_thread.start()
        try:
            self._manager = kete.TuhiKeteManager()
            for d in self._manager.devices:
                d.connect('notify::listening', self._on_device_listening)
            self._manager.connect('unregistered-device', self._on_unregistered_device)
        except kete.DBusError:
            pass

        self._unregistered_devices = []

    def register(self, device_id):
        for d in self._unregistered_devices:
            if d.address != device_id:
                continue

            d.register()
            return True

        return False

    @property
    def devices(self):
        devices = []
        for d in self._manager.devices:
            dev = Device(id=d.address,
                         name=d.name,
                         width=0,  # FIXME: missing in kete
                         height=0,   # FIXME: missing in kete
                         battery=d.battery_percent,
                         battery_state=d.battery_state,
                         is_listening=d.listening,
                         is_in_live_mode=d.live,
                         drawings=self.fetch_drawings(d))
            devices.append(dev)

        return devices

    @property
    def unregistered_devices(self):
        devices = []
        self._manager.start_search()
        GObject.timeout_add_seconds(30, self._discovery_timeout_expired)

        # FIXME: the kete manager resets _unregisted_devices on startSearch,
        # so it's useless for how we are doing things here.
        # this needs to be fixed. meanwhile, we just intercept the signal
        # also, I think the signal isn't always sent by tuhi
        for d in self._unregistered_devices:
            dev = Device(id=d.address, name=d.name)
            devices.append(dev)

        return devices

    def _on_unregistered_device(self, manager, device):
        self._unregistered_devices.append(device);

    def _discovery_timeout_expired(self):
        self._manager.stop_search()
        self._unregistered_devices = []

    def _on_device_listening(self, device, pspec):
        print(f'.... listening signal: {device.listening}')

    @property
    def device(self):
        return { d.address: d for d in self._manager.devices }

    def fetch_drawings(self, device):
        drawings = []
        for t in device.drawings_available:
            j = json.loads(device.json(t))
            drawings.append(j)
        return drawings


class DeviceController(object):
    @classmethod
    def get_device_by_id(self, device_id):  # noqa: E501
        d = [d for d in Tuhi.tuhi().devices if d.id == device_id]
        if not d:
            return []
        else:
            return d[0]

    @classmethod
    def list_devices(self):  # noqa: E501
        return Tuhi.tuhi().devices

    @classmethod
    def register_device_id_post(cls, device_id):
        result = Tuhi.tuhi().register(device_id)
        if result:
            return ApiResponse(200, message=f'success')
        return None, 400

    @classmethod
    def search(self):  # noqa: E501
        return Tuhi.tuhi().unregistered_devices

    @classmethod
    def toggle_listen(self, device_id, listen):  # noqa: E501
        device = Tuhi.tuhi().device[device_id]
        if listen:
            device.start_listening()
        else:
            device.stop_listening()
        return ApiResponse(200, message=f'listening: {device.listening}')
