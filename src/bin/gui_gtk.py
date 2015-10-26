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

from subprocess import PIPE

from gonium.fdm import AsyncDataStream, AsyncPopen
from taf.event_proto import EventStreamClient, encode_vint


import gi; gi.require_version('Gtk', '3.0'); gi.require_version('AppIndicator3', '0.1')
from gi.repository import AppIndicator3 as app_indicator
from gi.repository import Gtk as gtk


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

  def notify(self):
    self.ai.set_status(self.IS_ATTENTION)
    self.ai.set_icon(self.ip_active)

  def reset(self):
    self.ai.set_status(self.IS_ACTIVE)
    self.ai.set_icon(self.ip_inactive)
  

def ed_shutdown(ed):
  def shutdown(*args, **kwargs):
    ed.shutdown()
  return shutdown

class Notifier:
  def __init__(self, conf):
    self._esc = None
    self._p = None
    self._watch_sets = None
    self._conf = conf
    self._ed = conf.sa.ed
    self.ti = conf.build_icon()

  def start_forward(self, tspec, dir_):
    self._p = p = AsyncPopen(self._ed, [b'ssh', tspec, b'~/.local/bin/logs2stdout.py', b'--cd', dir_], bufsize=0, stdin=PIPE, stdout=PIPE)
    self._esc = c = EventStreamClient(p.stdout_async, p.stdin_async)

    self._set_config()

    sd = ed_shutdown(self._ed)
    c.fl_in.process_close = sd
    c.fl_out.process_close = sd
    c.process_notify = self.process_notify

    self.pick_ws(0)

  def pick_ws(self, idx):
    self._esc.watch_set(self._watch_sets[idx].mask)
    self._esc.reset()

  def get_ws_picker(self, idx):
    return self.wrap_bump_ml(self.pick_ws, idx)

  def wrap_bump_ml(self, f, *args, **kwargs):
    def wrap(*_):
      self._ed.set_timer(0, f, args=args, kwargs=kwargs, interval_relative=False)
      self._conf.sa.bump_ml()

    return wrap

  def reset(self, *_):
    self.wrap_bump_ml(self._esc.reset)()
    self.ti.reset()

  def process_notify(self, idx):
    print('AX {}'.format(idx))
    self.ti.notify()

  def _set_config(self):
    self._p = self._conf.patterns
    for (i, p) in enumerate(self._p):
      w = self._esc.add_watch(p.sp, p.fn_p)
      if (w.idx != i):
        raise ValueError('Watch setup idx mismatch: {} != {}'.format(w.idx, i))

    self._watch_sets = wss = self._conf.watch_sets
    for (i, ws) in enumerate(wss):
      self.ti.add_menu_item(ws.desc, self.get_ws_picker(i))

    self.ti.add_menu_sep()
    self.ti.add_menu_item('Reset', self.reset)
    

class Pattern:
  def __init__(self, sp, fn_p, idx):
    self.sp = sp
    self.fn_p = fn_p
    self.idx = idx

  def __repr__(self):
    return '{}{}'.format(type(self).__name__, (self.sp, self.fn_p, self.idx))
    
class WatchSet:
  def __init__(self, mask, desc):
    self.mask = mask
    self.desc = desc

class Config:
  def __init__(self, sa):
    self.sa = sa
    self.patterns = []
    self.watch_sets = []
    self.pid_path = None

    ns = {}
    for name in dir(self):
      if (name.startswith('_')):
        continue
      ns[name] = getattr(self, name)

    self._config_ns = ns

  def load_config_by_fn(self, fn):
    file = open(fn, 'rb')
    file_data = file.read()
    file.close()
    exec(file_data, self._config_ns)

  def add_pattern(self, sp, fn_p):
    idx = len(self.patterns)
    p = Pattern(sp, fn_p, idx)
    self.patterns.append(p)
    return p

  def add_watchset(self, patterns, desc):
    mask = 0
    for p in patterns:
      mask += 1<<p.idx

    mask = encode_vint(mask, 'little')
    ws = WatchSet(mask, desc)
    self.watch_sets.append(ws)
    return ws

  def set_forward_args(self, *args):
    self.forward_args = args

  def set_icons(self, ip_inactive, ip_active):
    self.ip_inactive = ip_inactive
    self.ip_active = ip_active

  def set_pid_file(self, path):
    from os.path import expanduser
    self.pid_path = expanduser(path)

  def build_icon(self):
    return GtkTrayIcon(self.sa, self.ip_inactive, self.ip_active)
  
  def file_pid(self):
    if (self.pid_path is None):
      return
    from gonium.pid_filing import PidFile
    self.pid_file = f = PidFile(self.pid_path)
    f.lock()


def main():
  import argparse
  import os
  import signal

  from gonium.service_aggregation import ServiceAggregate
  from threading import Thread

  p = argparse.ArgumentParser()
  p.add_argument('--config', '-c', default='~/.taf/config')

  args = p.parse_args()
  sa = ServiceAggregate()

  sa.bump_ml = lambda: os.write(sa.sc._pipe_w, b'\x00')

  config_fn = os.path.expanduser(args.config)
  config = Config(sa)
  config.load_config_by_fn(config_fn)

  config.file_pid()

  n = Notifier(config)
  n.start_forward(*config.forward_args)

  # Signal handling
  def handle_signals(si_l):
    for si in si_l:
      if (si.signo in (signal.SIGTERM, signal.SIGINT)):
        sa.ed.shutdown()
        #log(50, 'Shutting down on signal {}.'.format(si.signo))
        break
      if (si.signo == signal.SIGUSR1):
        n.reset()
        break

  sa.sc.handle_signals.new_listener(handle_signals)
  for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGUSR1):
    sa.sc.sighandler_install(sig, sa.sc.SA_RESTART)

  # gtk setup
  ui_thread = Thread(target=gtk.main, name='ui', daemon=True)
  ui_thread.start()

  sa.ed.event_loop()
  

if (__name__ == '__main__'):
  main()
