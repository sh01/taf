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

import os
import sys

from gonium.fdm import AsyncDataStream
from taf.event_proto import EventStreamServer


def ed_shutdown(ed):
  def shutdown(*args, **kwargs):
    ed.shutdown()
  return shutdown

# Usage: start_stdio(), (scan_dir()*, watch_all())
class FileGazer:
  def __init__(self, ed, *args, **kwargs):
    self.ed = ed
    self.stream = None
    self.wd2pn = []

  def _start_watch(self):
    from gonium.fdm import inotify

    self.iw = inotify.InotifyWatch(self.ed)
    self.iw.process_event = self._process_inotify_event

  def _process_inotify_event(self, wd, mask, cookie, name):
    pn = self.wd2pn[wd]
    # TODO: Match line patterns
    self.stream.notify(pn)

  def start_stdio(self):
    fl_in = AsyncDataStream(self.ed, os.fdopen(sys.stdin.fileno(), 'rb', 0, closefd=False))
    fl_out = AsyncDataStream(self.ed, os.fdopen(sys.stdout.fileno(), 'wb', 0, closefd=False), read_r=False)

    sd = ed_shutdown(self.ed)
    fl_in.process_close = sd
    fl_out.process_close = sd

    self.stream = EventStreamServer(fl_in, fl_out)
    self.stream.watch_files = self._watch_files
    self._start_watch()

  def scan_dir(self, path):
    from os import walk
    from os.path import join

    for (p, dns, fns) in walk(path):
      for fn in fns:
        fp = join(p, fn)
        if fp.startswith(b'./'):
          fp = fp[2:]
        self.stream.add_file(fp)

  def watch_all(self):
    self._watch_files(self.stream.get_watched_files())

  def _add_watch_descriptor(self, wd, pn):
    off = wd - len(self.wd2pn) + 1
    if (off > 0):
      from itertools import repeat
      self.wd2pn.extend(repeat(None, off))

    self.wd2pn[wd] = pn

  def _watch_files(self, pns):
    from gonium.fdm.inotify import IN_MODIFY

    for pn in pns:
      wd = self.iw.add_watch(pn, IN_MODIFY)
      self._add_watch_descriptor(wd, pn)


def main():
  from gonium.fdm import ED_get
  import argparse

  p = argparse.ArgumentParser()
  p.add_argument('--cd')

  args = p.parse_args()

  if (args.cd):
    os.chdir(args.cd)

  ed = ED_get()()

  fg = FileGazer(ed)
  fg.start_stdio()
  fg.scan_dir(b'.')
  
  ed.event_loop()


if (__name__ == '__main__'):
  main()
