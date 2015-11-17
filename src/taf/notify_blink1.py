#!/usr/bin/env python3
#Copyright 2015 Sebastian Hagen
# This file is part of taf.
#
# taf is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 of the License, or
# (at your option) any later version.
#
# taf is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import usb
import logging

logger = logging.getLogger('notify_blink1')
log = logger.log

REPORT_ID = 1


class Blinker:
  REQ_TYPE = usb.util.build_request_type(usb.util.CTRL_OUT, usb.util.CTRL_TYPE_CLASS, usb.util.CTRL_RECIPIENT_INTERFACE)
  def __init__(self, dev):
    if (dev.is_kernel_driver_active(0)):
      dev.detach_kernel_driver(0)

    self.dev = dev

  def write_buf(self, buf):
    return self.dev.ctrl_transfer(self.REQ_TYPE, 0x09, 768 | REPORT_ID, 0, buf)

  def set_color(self, r, g, b):
    self.write_buf([REPORT_ID, 0x6e, r, g, b, 0, 0, 0])

  def off(self):
    self.set_color(0,0,0)

  @classmethod
  def build_auto(cls):
    dev = usb.core.find(idVendor=0x27b8, idProduct=0x01ed)
    return cls(dev)


class BlinkNotifier:
  def __init__(self, color):
    self.blinker = None
    color = [int(x) for x in color]
    if (len(color) != 3):
      raise ValueError('Invalid color value {!r}; expected 3-sequence.'.format(color))
    self.signal_color = color

  def add_menu_sep(self, *a, **k):
    pass
  def add_menu_item(self, *a, **k):
    pass

  def get_blinker(self):
    rv = self.blinker
    if (rv is None):
      rv = self.blinker = Blinker.build_auto()
    return rv

  def notify(self, idx):
    try:
      self.get_blinker().set_color(*self.signal_color)
    except Exception as exc:
      self.blinker = None
      log(30, 'Failed to blink1-notify(): {!r}'.format(str(exc)))

  def reset(self):
    bl = self.blinker
    if (bl is None):
      return
    try:
      bl.off()
    except Exception as exc:
      self.blinker = None
      log(30, 'Failed to blink1-reset(): {!r}'.format(str(exc)))
