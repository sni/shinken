#!/usr/bin/python

# -*- coding: utf-8 -*-

# Copyright (C) 2009-2012:
#    Gabes Jean, naparuba@gmail.com
#    Gerhard Lausser, Gerhard.Lausser@consol.de
#    Gregory Starck, g.starck@gmail.com
#    Hartmut Goebel, h.goebel@goebel-consult.de
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

# This Class is an example of an Scheduler module
# Here for the configuration phase AND running one

from shinken.basemodule import BaseModule

properties = {
    'daemons': ['scheduler'],
    'type': 'dummy_scheduler',
    'external': False,
    'phases': ['retention'],
    }


# called by the plugin manager to get a broker
def get_instance(mod_conf):
    print "Get a Dummy scheduler module for plugin %s" % mod_conf.get_name()
    instance = Dummy_scheduler(mod_conf, foo="bar")
    return instance


# Just print some stuff
class Dummy_scheduler(BaseModule):

    def __init__(self, mod_conf, foo):
        BaseModule.__init__(self, mod_conf)
        self.myfoo = foo

    # Called by Scheduler to say 'let's prepare yourself guy'
    def init(self):
        print "Initilisation of the dummy scheduler module"
        # self.return_queue = self.properties['from_queue']


    # Ok, main function that is called in the retention creation pass
    def update_retention_objects(self, sched, log_mgr):
        print "[Dummy] asking me to update the retention objects"

    # Should return if it succeed in the retention load or not
    def load_retention_objects(self, sched, log_mrg):
        print "[Dummy] asking me to load the retention objects"
        return False

# From now external is not used in the scheduler job
#    #When you are in "external" mode, that is the main loop of your process
#    def main(self):
#        while True:
#            print "Raise a external command as example"
#            e = ExternalCommand('Viva la revolution')
#            self.return_queue.put(e)
#            time.sleep(1)
