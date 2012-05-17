#!/usr/bin/python

# -*- coding: utf-8 -*-

# Copyright (C) 2012:
#    Sven Nierlein, sven@consol.de
#
# This file is part of Shinken.
#
# Shinken is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Shinken is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with Shinken.  If not, see <http://www.gnu.org/licenses/>.


properties = {
    # TODO: verify if broker is enough
    'daemons': ['broker', 'scheduler'],
    'type': 'mongodb',
    'phases': ['running'],
    'external': True,
}


# called by the plugin manager to get a broker
def get_instance(plugin):
    print "[mongodb_broker] Get a Mongodb broker for plugin %s" % plugin.get_name()

    # first try the import
    try:
        from mongodb_broker import Mongodb_broker
    except ImportError, exp:
        print "[mongodb_broker] Warning : the plugin type mongodb is unavailable : %s" % exp
        return None

    instance = Mongodb_broker(plugin)
    return instance
