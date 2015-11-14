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

from threading import Thread

import gi; gi.require_version('Gtk', '3.0'); gi.require_version('AppIndicator3', '0.1')
from gi.repository import AppIndicator3 as app_indicator
from gi.repository import Gtk as gtk

def init():
  # gtk setup
  ui_thread = Thread(target=gtk.main, name='ui', daemon=True)
  ui_thread.start()


class GtkTrayIcon:
  IS_ACTIVE = app_indicator.IndicatorStatus.ACTIVE
  IS_ATTENTION = app_indicator.IndicatorStatus.ATTENTION

  def __init__(self, sa, ip_inactive, ip_active):
    self.sa = sa
    self.ip_inactive = ip_inactive
    self.ip_active = ip_active

    self.ai = ai = app_indicator.Indicator.new('TAF', ip_inactive, app_indicator.IndicatorCategory.COMMUNICATIONS)
    ai.set_status(self.IS_ACTIVE)

    self.menu = menu = gtk.Menu()

    def sd(*_):
      sa.ed.shutdown()
      sa.bump_ml()

    self.add_menu_item('Quit', sd)
    self.add_menu_sep()

    ai.connect('scroll-event', sd)

    menu.show_all()
    ai.set_menu(menu)

  def add_menu_sep(self):
    sep = gtk.SeparatorMenuItem()
    self.menu.append(sep)

  def add_menu_item(self, title, callback):
    item = gtk.MenuItem(title)
    item.connect('activate', callback)
    item.show()
    self.menu.append(item)
    return item

  def notify(self, *args, **kwargs):
    self.ai.set_status(self.IS_ATTENTION)
    self.ai.set_icon(self.ip_active)

  def reset(self):
    self.ai.set_status(self.IS_ACTIVE)
    self.ai.set_icon(self.ip_inactive)
