#!/usr/bin/env python3
#Copyright 20015 Sebastian Hagen
# This file is part of taf.

# taf is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2
# as published by the Free Software Foundation
#
# taf is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import sys
from distutils.core import setup

if (sys.version_info[0] <= 2):
   raise Exception('This program needs a python >= 3.0')


setup(name='taf',
   version='0.1',
   description='TAF: Tunneled attention flags.',
   author='Sebastian Hagen',
   author_email='sebastian_hagen@memespace.net',
   #url='http://git.memespace.net/git/??',
   packages=('taf',),
   scripts=(
	'src/bin/logs2stdout.py',
	'src/bin/gui_gtk.py'
   ),
   package_dir={'taf':'src/taf'}
)
