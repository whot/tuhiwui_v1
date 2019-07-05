#!/usr/bin/env python3
#
#  This program is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation; either version 2 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#

from gi.repository import GObject, Gio, GLib
import sys
import argparse
import binascii
import cmd
import errno
import os
import json
import logging
import re
import readline
import struct
import threading
import time
import svgwrite
import xdg.BaseDirectory
import configparser


CONFIG_PATH = os.path.join(xdg.BaseDirectory.xdg_data_home, 'tuhi-kete')


class ColorFormatter(logging.Formatter):
    BLACK, RED, GREEN, YELLOW, BLUE, MAGENTA, CYAN, LIGHT_GRAY = range(30, 38)
    DARK_GRAY, LIGHT_RED, LIGHT_GREEN, LIGHT_YELLOW, LIGHT_BLUE, LIGHT_MAGENTA, LIGHT_CYAN, WHITE = range(90, 98)
    COLORS = {
        'WARNING': LIGHT_RED,
        'INFO': LIGHT_GREEN,
        'DEBUG': LIGHT_GRAY,
        'CRITICAL': YELLOW,
        'ERROR': RED,
    }
    RESET_SEQ = '\033[0m'
    COLOR_SEQ = '\033[%dm'
    BOLD_SEQ = '\033[1m'

    def __init__(self, *args, **kwargs):
        logging.Formatter.__init__(self, *args, **kwargs)

    def format(self, record):
        levelname = record.levelname
        color = self.COLOR_SEQ % (self.COLORS[levelname])
        message = logging.Formatter.format(self, record)
        message = message.replace('$RESET', self.RESET_SEQ)\
                         .replace('$BOLD', self.BOLD_SEQ)\
                         .replace('$COLOR', color)
        for k, v in self.COLORS.items():
            message = message.replace('$' + k, self.COLOR_SEQ % (v + 30))
        return message + self.RESET_SEQ


log_format = '$COLOR%(levelname)s: %(message)s'
logger_handler = logging.StreamHandler()
logger_handler.setFormatter(ColorFormatter(log_format))
logger = logging.getLogger('tuhi-kete')
logger.addHandler(logger_handler)
logger.setLevel(logging.INFO)

TUHI_DBUS_NAME = 'org.freedesktop.tuhi1'
ORG_FREEDESKTOP_TUHI1_MANAGER = 'org.freedesktop.tuhi1.Manager'
ORG_FREEDESKTOP_TUHI1_DEVICE = 'org.freedesktop.tuhi1.Device'
ROOT_PATH = '/org/freedesktop/tuhi1'

ORG_BLUEZ_DEVICE1 = 'org.bluez.Device1'

# remove ':' from the completer delimiters of readline so we can match on
# device addresses
completer_delims = readline.get_completer_delims()
completer_delims = completer_delims.replace(':', '')
readline.set_completer_delims(completer_delims)


def b2hex(bs):
    '''Convert bytes() to a two-letter hex string in the form "1a 2b c3"'''
    hx = binascii.hexlify(bs).decode('ascii')
    return ' '.join([''.join(s) for s in zip(hx[::2], hx[1::2])])


class DBusError(Exception):
    def __init__(self, message):
        self.message = message


class _DBusObject(GObject.Object):
    _connection = None

    def __init__(self, name, interface, objpath):
        GObject.GObject.__init__(self)

        if _DBusObject._connection is None:
            self._connect_to_session()

        self.interface = interface
        self.objpath = objpath

        try:
            self.proxy = Gio.DBusProxy.new_sync(self._connection,
                                                Gio.DBusProxyFlags.NONE, None,
                                                name, objpath, interface, None)
        except GLib.Error as e:
            if (e.domain == 'g-io-error-quark' and
                    e.code == Gio.IOErrorEnum.DBUS_ERROR):
                raise DBusError(e.message)
            else:
                raise e

        if self.proxy.get_name_owner() is None:
            raise DBusError(f'No-one is handling {name}, is the daemon running?')

        self.proxy.connect('g-properties-changed', self._on_properties_changed)
        self.proxy.connect('g-signal', self._on_signal_received)

    def _connect_to_session(self):
        try:
            _DBusObject._connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        except GLib.Error as e:
            if (e.domain == 'g-io-error-quark' and
                    e.code == Gio.IOErrorEnum.DBUS_ERROR):
                raise DBusError(e.message)
            else:
                raise e

    def _on_properties_changed(self, proxy, changed_props, invalidated_props):
        # Implement this in derived classes to respond to property changes
        pass

    def _on_signal_received(self, proxy, sender, signal, parameters):
        # Implement this in derived classes to respond to signals
        pass

    def property(self, name):
        p = self.proxy.get_cached_property(name)
        if p is not None:
            return p.unpack()
        return p

    def terminate(self):
        del(self.proxy)


class _DBusSystemObject(_DBusObject):
    '''
    Same as the _DBusObject, but connects to the system bus instead
    '''
    def __init__(self, name, interface, objpath):
        self._connect_to_system()
        super().__init__(name, interface, objpath)

    def _connect_to_system(self):
        try:
            self._connection = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
        except GLib.Error as e:
            if (e.domain == 'g-io-error-quark' and
                    e.code == Gio.IOErrorEnum.DBUS_ERROR):
                raise DBusError(e.message)
            else:
                raise e


class BlueZDevice(_DBusSystemObject):
    def __init__(self, objpath):
        super().__init__('org.bluez', ORG_BLUEZ_DEVICE1, objpath)
        self.proxy.connect('g-properties-changed', self._on_properties_changed)

    @GObject.Property
    def connected(self):
        return self.proxy.get_cached_property('Connected').unpack()

    def _on_properties_changed(self, obj, properties, invalidated_properties):
        properties = properties.unpack()

        if 'Connected' in properties:
            self.notify('connected')


class TuhiKeteDevice(_DBusObject):
    def __init__(self, manager, objpath):
        _DBusObject.__init__(self, TUHI_DBUS_NAME,
                             ORG_FREEDESKTOP_TUHI1_DEVICE,
                             objpath)
        self.manager = manager
        self.is_registering = False
        self.live = False
        self._bluez_device = BlueZDevice(self.property('BlueZDevice'))
        self._bluez_device.connect('notify::connected', self._on_connected)

    @classmethod
    def is_device_address(cls, string):
        if re.match(r'[0-9a-f]{2}(:[0-9a-f]{2}){5}$', string.lower()):
            return string
        raise argparse.ArgumentTypeError(f'"{string}" is not a valid device address')

    @GObject.Property
    def address(self):
        return self._bluez_device.property('Address')

    @GObject.Property
    def name(self):
        return self._bluez_device.property('Name')

    @GObject.Property
    def listening(self):
        return self.property('Listening')

    @GObject.Property
    def drawings_available(self):
        return self.property('DrawingsAvailable')

    @GObject.Property
    def battery_percent(self):
        return self.property('BatteryPercent')

    @GObject.Property
    def battery_state(self):
        return self.property('BatteryState')

    @GObject.Property
    def connected(self):
        return self._bluez_device.connected

    def _on_connected(self, bluez_device, pspec):
        self.notify('connected')

    def register(self):
        logger.debug(f'{self}: Register')
        # FIXME: Register() doesn't return anything useful yet, so we wait until
        # the device is in the Manager's Devices property
        self.s1 = self.manager.connect('notify::devices', self._on_mgr_devices_updated)
        self.is_registering = True
        self.proxy.Register()

    def start_listening(self):
        self.proxy.StartListening()

    def stop_listening(self):
        try:
            self.proxy.StopListening()
        except GLib.Error as e:
            if (e.domain != 'g-dbus-error-quark' or
                    e.code != Gio.IOErrorEnum.EXISTS or
                    Gio.dbus_error_get_remote_error(e) != 'org.freedesktop.DBus.Error.ServiceUnknown'):
                raise e

    def start_live(self, fd):
        fd_list = Gio.UnixFDList.new()
        fd_list.append(fd)

        res, fds = self.proxy.call_with_unix_fd_list_sync('org.freedesktop.tuhi1.Device.StartLive',
                                                          GLib.Variant('(h)', (fd,)),
                                                          Gio.DBusCallFlags.NO_AUTO_START,
                                                          -1,
                                                          fd_list,
                                                          None)
        if res[0] == 0:
            self.live = True

    def stop_live(self):
        self.proxy.StopLive()
        self.live = False

    def json(self, timestamp):
        SUPPORTED_FILE_FORMAT = 1
        return self.proxy.GetJSONData('(ut)', SUPPORTED_FILE_FORMAT, timestamp)

    def _on_signal_received(self, proxy, sender, signal, parameters):
        if signal == 'ButtonPressRequired':
            logger.info(f'{self}: Press button on device now')
        elif signal == 'ListeningStopped':
            err = parameters[0]
            if err == -errno.EACCES:
                logger.error(f'{self}: wrong device, please re-register.')
            elif err < 0:
                logger.error(f'{self}: an error occured: {os.strerror(-err)}')
            self.notify('listening')

    def _on_properties_changed(self, proxy, changed_props, invalidated_props):
        if changed_props is None:
            return

        changed_props = changed_props.unpack()

        if 'DrawingsAvailable' in changed_props:
            self.notify('drawings-available')
        elif 'Listening' in changed_props:
            self.notify('listening')
        elif 'BatteryPercent' in changed_props:
            self.notify('battery-percent')
        elif 'BatteryState' in changed_props:
            self.notify('battery-state')

    def __repr__(self):
        return f'{self.address} - {self.name}'

    def _on_mgr_devices_updated(self, manager, pspec):
        if not self.is_registering:
            return

        for d in manager.devices:
            if d.address == self.address:
                self.is_registering = False
                self.manager.disconnect(self.s1)
                del(self.s1)
                logger.info(f'{self}: Registration successful')

    def terminate(self):
        try:
            self.manager.disconnect(self.s1)
        except AttributeError:
            pass
        self._bluez_device.terminate()
        super(TuhiKeteDevice, self).terminate()


class TuhiKeteManager(_DBusObject):
    __gsignals__ = {
        'unregistered-device':
            (GObject.SignalFlags.RUN_FIRST, None, (GObject.TYPE_PYOBJECT,)),
    }

    def __init__(self):
        _DBusObject.__init__(self, TUHI_DBUS_NAME,
                             ORG_FREEDESKTOP_TUHI1_MANAGER,
                             ROOT_PATH)

        self._devices = {}
        self._unregistered_devices = {}

        for objpath in self.property('Devices'):
            device = TuhiKeteDevice(self, objpath)
            self._devices[device.address] = device

    @GObject.Property
    def devices(self):
        return [v for k, v in self._devices.items()]

    @GObject.Property
    def unregistered_devices(self):
        return [v for k, v in self._unregistered_devices.items()]

    @GObject.Property
    def searching(self):
        return self.proxy.get_cached_property('Searching')

    def start_search(self):
        self._unregistered_devices = {}
        self.proxy.StartSearch()

    def stop_search(self):
        try:
            self.proxy.StopSearch()
        except GLib.Error as e:
            if (e.domain != 'g-dbus-error-quark' or
                    e.code != Gio.IOErrorEnum.EXISTS or
                    Gio.dbus_error_get_remote_error(e) != 'org.freedesktop.DBus.Error.ServiceUnknown'):
                raise e
        self._unregistered_devices = {}

    def terminate(self):
        for dev in self._devices.values():
            dev.terminate()
        self._devices = {}
        self._unregistered_devices = {}
        super(TuhiKeteManager, self).terminate()

    def _on_properties_changed(self, proxy, changed_props, invalidated_props):
        if changed_props is None:
            return

        changed_props = changed_props.unpack()

        if 'Devices' in changed_props:
            objpaths = changed_props['Devices']
            for objpath in objpaths:
                try:
                    d = self._unregistered_devices[objpath]
                    self._devices[d.address] = d
                    del self._unregistered_devices[objpath]
                except KeyError:
                    # if we called Register() on an existing device it's not
                    # in unregistered devices
                    pass
            self.notify('devices')
        if 'Searching' in changed_props:
            self.notify('searching')

    def _handle_unregistered_device(self, objpath):
        for addr, dev in self._devices.items():
            if dev.objpath == objpath:
                self.emit('unregistered-device', dev)
                return

        device = TuhiKeteDevice(self, objpath)
        self._unregistered_devices[objpath] = device

        logger.debug(f'New unregistered device: {device}')
        self.emit('unregistered-device', device)

    def _on_signal_received(self, proxy, sender, signal, parameters):
        if signal == 'SearchStopped':
            self.notify('searching')
        elif signal == 'UnregisteredDevice':
            objpath = parameters[0]
            self._handle_unregistered_device(objpath)

    def __getitem__(self, btaddr):
        return self._devices[btaddr]
