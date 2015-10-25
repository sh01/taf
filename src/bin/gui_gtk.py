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
  def __init__(self):
    self.ai = ai = app_indicator.Indicator.new('goo',os.path.abspath('icon.png'),app_indicator.IndicatorCategory.COMMUNICATIONS)
    ai.set_status(app_indicator.IndicatorStatus.ACTIVE)
    ai.set_attention_icon("indicator-messages-new")

    self.menu = menu = Gtk.Menu()
    ai.set_menu(menu)

  def notify(self):
    pass


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

  def start_forward(self, ed, tspec, dir_):
    self._p = p = AsyncPopen(ed, [b'ssh', tspec, b'strace -tt -otmp/t1.log', b'.exe/logs2stdout.py', b'--cd', dir_], bufsize=0, stdin=PIPE, stdout=PIPE)
    self._esc = c = EventStreamClient(p.stdout_async, p.stdin_async)

    self._set_config()

    sd = ed_shutdown(ed)
    c.fl_in.process_close = sd
    c.fl_out.process_close = sd
    c.process_notify = self.process_notify

    self.pick_ws(0)

  def pick_ws(self, idx):
    self._esc.watch_set(self._watch_sets[idx].mask)

  def process_notify(self, idx):
    print('AX {}'.format(idx))

  def _set_config(self):
    self._p = self._conf.patterns
    for (i, p) in enumerate(self._p):
      w = self._esc.add_watch(p.sp, p.fn_p)
      if (w.idx != i):
        raise ValueError('Watch setup idx mismatch: {} != {}'.format(w.idx, i))

    self._watch_sets = self._conf.watch_sets


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
  def __init__(self):
    self.patterns = []
    self.watch_sets = []

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
    

def main():
  import argparse
  import os

  from gonium.service_aggregation import ServiceAggregate
  from threading import Thread

  p = argparse.ArgumentParser()
  p.add_argument('--config', '-c', default='taf.conf')

  args = p.parse_args()
  sa = ServiceAggregate()

  config_fn = os.path.expanduser(args.config)
  config = Config()
  config.load_config_by_fn(config_fn)

  n = Notifier(config)
  n.start_forward(sa.ed, *config.forward_args)

  # Signal handling
  def handle_signals(si_l):
    for si in si_l:
      if ((si.signo == signal.SIGTERM) or (si.signo == signal.SIGINT)):
        sa.ed.shutdown()
        #log(50, 'Shutting down on signal {}.'.format(si.signo))
        break
  sa.sc.handle_signals.new_listener(handle_signals)

  # gtk setup
  #ui_thread = Thread(target=gtk.main, name='ui', daemon=True)
  #ui_thread.start()

  sa.ed.event_loop()
  

if (__name__ == '__main__'):
  main()
