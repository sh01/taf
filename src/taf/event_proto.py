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

# All TAF protocol objects are prefixed by a 5-octet header:
#   <recursive total object (not incl. header) length (uint32)>, <object type (uint8)>.
# Protocol objects and type codes:
#
#   0x01: UInts
#   0x02: String (i.e. octet sequence)
#   0x03: Lists (<uint32 object count>, <object...>)
# All integers are encoded big-endian.

# A TAF protocol /message/ is a [Uint, ...] list, where the initial uint element specifies the message type:
#   0x00: Ping.
#   0x01: Pong.
#   0x02: Ack.
#   0x03: Watch setup: <string filename pattern>,<string line pattern>
#   0x04: Watch set: <string bitmask>
#   0x05: Reset.
#   0x06: Notify

import logging
import re
import struct
import sys

logger = logging.getLogger('event_proto')
log = logger.log

class TafProtocolError(Exception):
  pass

# ================================ Decoder structures
def get_size(data):
  (v,) = struct.unpack('>L', data[:4])
  return v + 5

object_parsers = {
}
def reg_parser(tc):
  def reg(p):
    object_parsers[tc] = p
    return p
  return reg

@reg_parser(0x01)
def parse_uint(data):
  size_total = get_size(data)
  rv = int.from_bytes(data[5:size_total], 'big')
  return (rv, size_total)

@reg_parser(0x02)
def parse_string(data):
  size_total = get_size(data)
  return (data[5:size_total], size_total)

@reg_parser(0x03)
def parse_list(data):
  size_total = get_size(data)
  (el_count,) = struct.unpack('>L', data[5:9])
  off = 9
  rv = [None]*el_count
  for i in range(el_count):
    (rv[i], sz) = parse_object(data[off:])
    off += sz

  if (off != size_total):
    raise TafProtocolError('List depth contents mismatch in {!r}: {} != {}'.format(data, size_total, off))

  return (rv, size_total)

def parse_object(data):
  tc = data[4]
  try:
    p = object_parsers[tc]
  except KeyError:
    raise TafProtocolError('Unknown type code {!r}.'.format(tc))
  return p(data)

def parse_message(data):
  (rv, _) = parse_object(data)
  if (type(rv) != list):
    raise TafProtocolError('Got non-list message: {!r}'.format(msg))  
  if (len(rv) < 1):
    raise TafProtocolError('Got empty list message.')
  if (type(rv[0]) != int):
    raise TafProtocolError('Got message with invalid payload types: {!r}'.format(msg))
  return rv

# ================================ Encoder structures
object_encoders = {
}
def reg_encoder(tc):
  def reg(p):
    object_encoders[tc] = p
    return p
  return reg


def encode_vint(i, bo='big'):
   length_b = i.bit_length()
   length, length_m = divmod(length_b, 8)
   length += bool(length_m)

   b = i.to_bytes(length, bo)
   return b

class Encoder:
  def __init__(self):
    self.data = bytearray()

  def drop_size(self):
    self.data.extend(b'\x00\x00\x00\x00')

  def set_size(self, sz, off):
    b = struct.pack('>L', sz)
    self.data[off:off+4] = b
    
  @reg_encoder(int)
  def encode_uint(self, val):
    b = encode_vint(val)
    self.set_size(len(b), len(self.data))
    self.data.append(0x01)
    
    self.data.extend(b)

  @reg_encoder(bytes)
  def encode_string(self, val):
    length = len(val)
    self.set_size(length, len(self.data))
    self.data.append(0x02)
    self.data.extend(val)
    
  @reg_encoder(list)
  def encode_list(self, val):
    b = len(self.data)
    self.drop_size()
    self.data.append(0x03)
    self.set_size(len(val), len(self.data))
    
    for el in val:
      self.encode_any(el)
    sz = len(self.data) - b - 5
    self.set_size(sz, b)
    
  def encode_any(self, val):
    return object_encoders[type(val)](self, val)

def encode_msg(msg):
  e = Encoder()
  e.encode_list(msg)
  return e.data

def _test_serialization():
  for v in (0, 42, 127, 128, b'', b'foo', [], [42], [b'foo'], [b'', 0, 3, b'bar'], [[[], b'foo']]):
    e = Encoder()
    e.encode_any(v)
    (v2, _) = parse_object(e.data)
    if (v != v2):
      raise ValueError('Serial mismatch: {!r} != {!r}'.format(v, v2))
    if (type(v) == list):
      msg = v
    else:
      msg = [v]

    (msg2, _) = parse_object(encode_msg(msg))
    if (msg != msg2):
      raise ValueError('Serial mismatch: {!r} != {!r}'.format(msg, msg2))


# ================================ Stream interface

MSG_NAMES = {
  'PING': 0x00,
  'PONG': 0x01,
  'ACK': 0x02,
  'WATCH_SETUP': 0x03,
  'WATCH_SET': 0x04,
  'RESET': 0x05,
  'NOTIFY': 0x06,
}

for (k,v) in MSG_NAMES.items():
  globals()['MSG_ID_{}'.format(k)] = v

def reg_es_parsers(cls):
  prefix = 'process_msg_'
  m = {}
  for name in dir(cls):
    if not (name.startswith(prefix)):
      continue
    suffix = name[len(prefix):]
    
    num = MSG_NAMES.get(suffix)
    if (num is None):
      continue
    m[num] = getattr(cls, name)

  cls.msg_handlers = m
  return cls


@reg_es_parsers
class EventStream:
  def __init__(self, fl_in, fl_out):
    self.fl_in = fl_in
    fl_in.process_input = self.process_input
    self.fl_out = fl_out
    self.fl_in.size_need = 4

  def process_input(self, data):
    disc = 0
    while len(data) > 4:
      sz = get_size(data)
      if (len(data) < sz):
        self.fl_in.size_need = sz + 5
        break

      log(8, 'Parsing: {!a}'.format(bytes(data)))
      msg = parse_message(data)
      log(8, 'Parsed: {!a}'.format(msg))
      mtype = msg[0]

      #sys.stderr.write('DO1: {}\n'.format(msg)); sys.stderr.flush()
      p = self.msg_handlers.get(mtype)
      if (p is None):
        raise TafProtocolError('Unknown mtype in {}.'.format(msg))
      p(self, msg)

      data = data[sz:]
      disc += sz
    else:
      self.fl_in.size_need = 4

    if (disc > 0):
      self.fl_in.discard_inbuf_data(disc)

  def send_msg(self, msg):
    #sys.stderr.write('DO0: {}\n'.format(msg)); sys.stderr.flush()
    log(8, 'Sending: {!a}'.format(msg))
    data = encode_msg(msg)
    self.fl_out.send_bytes((data,))
    log(8, 'Sent: {!a}'.format(data))

  def send_ping(self, arg):
    self.send_msg([MSG_ID_PING, arg])

  def process_msg_PING(self, msg):
    arg = msg[1]
    self.send_msg([MSG_ID_PONG, arg])


class Watch:
  def __init__(self, fn_p, line_p):
    self.fn_p = fn_p
    self.line_p = line_p
    self.set = False
    self.idx = None

  def __repr__(self):
    return '{}<**{}>'.format(type(self).__name__, self.__dict__)

@reg_es_parsers
class EventStreamClient(EventStream):
  def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)
    self.watch_count = 0

  def process_msg_NOTIFY(self, msg):
    (_, idx) = msg
    self.process_notify(idx)

  def process_msg_ACK(self, msg):
    pass

  def reset(self):
    self.send_msg([MSG_ID_RESET])

  def watch_set(self, wids):
    self.send_msg([MSG_ID_WATCH_SET, wids])

  def add_watch(self, fn_p, line_p):
    w = Watch(fn_p, line_p)
    w.idx = self.watch_count
    self.watch_count += 1
    self.send_msg([MSG_ID_WATCH_SETUP, fn_p, line_p])

    return w
    

@reg_es_parsers
class EventStreamServer(EventStream):
  def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)
    self.watchs = []
    self.fn2ws = {}

  def send_ACK(self):
    self.send_msg([MSG_ID_ACK])

  def watch_files(self, fns):
    pass

  def get_watched_files(self):
    return [k for (k,v) in self.fn2ws.items() if v]

  def add_file(self, fn):
    self.fn2ws.setdefault(fn, [])

  def add_watch(self, w):
    w.idx = len(self.watchs)
    w.__active = False
    self.watchs.append(w)
    fns = []
    for (fn, ws) in self.fn2ws.items():
      if w.fn_p.search(fn):
        ws.append(w)
        fns.append(fn)
    self.watch_files(fns)

  def notify(self, fn, get_lines):
    for w in self.get_watchs(fn):
      if (not w.__active) or w.set:
        continue

      # See if any of the new lines are matched by our line pattern.
      for line in get_lines():
        m = w.line_p.search(line)
        if (m is None):
          continue

        w.set = True
        self.send_msg([MSG_ID_NOTIFY, w.idx])
        break

  def process_msg_WATCH_SETUP(self, msg):
    (_, fn_p, line_p) = msg
    fn_r = re.compile(bytes(fn_p))
    line_r = re.compile(bytes(line_p))
    w = Watch(fn_r, line_r)
    self.add_watch(w)
    self.send_msg([MSG_ID_ACK])

  def process_msg_WATCH_SET(self, msg):
    (_, mask) = msg
    v = int.from_bytes(mask, 'little')

    p = 1
    for (i, w) in enumerate(self.watchs):
      w.__active = bool(p & v)
      p <<= 1

  def process_msg_RESET(self, msg):
    for w in self.watchs:
      w.set = False

  def get_watchs(self, fn):
    ws = self.fn2ws.get(fn)
    if (ws is None):
      ws = []
      for w in self.watches:
        if w.fn_p.search(fn):
          ws.append(w)
      self.fn2ws[fn] = ws
    
    return ws

if (__name__ == '__main__'):
  _test_serialization()
  print('Tests done.')
