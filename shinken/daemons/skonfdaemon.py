#!/usr/bin/env python
#Copyright (C) 2009-2010 :
#    Gabes Jean, naparuba@gmail.com
#    Gerhard Lausser, Gerhard.Lausser@consol.de
#    Gregory Starck, g.starck@gmail.com
#    Hartmut Goebel, h.goebel@goebel-consult.de
#
#This file is part of Shinken.
#
#Shinken is free software: you can redistribute it and/or modify
#it under the terms of the GNU Affero General Public License as published by
#the Free Software Foundation, either version 3 of the License, or
#(at your option) any later version.
#
#Shinken is distributed in the hope that it will be useful,
#but WITHOUT ANY WARRANTY; without even the implied warranty of
#MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#GNU Affero General Public License for more details.
#
#You should have received a copy of the GNU Affero General Public License
#along with Shinken.  If not, see <http://www.gnu.org/licenses/>.

import sys
import os
import time
import traceback
from Queue import Empty
import socket

from shinken.objects import Config
from shinken.external_command import ExternalCommandManager
from shinken.dispatcher import Dispatcher
from shinken.daemon import Daemon, Interface
from shinken.log import logger
from shinken.brok import Brok
from shinken.external_command import ExternalCommand
from shinken.util import safe_print


# Now the bottle HTTP part :)
from shinken.webui.bottle import Bottle, run, static_file, view, route, request, response
# Debug
import shinken.webui.bottle as bottle
bottle.debug(True)

#Import bottle lib to make bottle happy
bottle_dir = os.path.abspath(os.path.dirname(bottle.__file__))
sys.path.insert(0, bottle_dir)


bottle.TEMPLATE_PATH.append(os.path.join(bottle_dir, 'views'))
bottle.TEMPLATE_PATH.append(bottle_dir)



# Interface for the other Arbiter
# It connects, and together we decide who's the Master and who's the Slave, etc.
# Here is a also a function to get a new conf from the master
class IForArbiter(Interface):
    
    def have_conf(self, magic_hash):
        # I've got a conf and a good one
        if self.app.cur_conf and self.app.cur_conf.magic_hash == magic_hash:
            return True
        else: #I've no conf or a bad one
            return False

    # The master Arbiter is sending us a new conf. Ok, we take it
    def put_conf(self, conf):
        super(IForArbiter, self).put_conf(conf)
        self.app.must_run = False

    def get_config(self):
        return self.app.conf

    # The master arbiter asks me not to run!
    def do_not_run(self):
        # If i'm the master, then F**K YOU!
        if self.app.is_master:
            print "Some f***ing idiot asks me not to run. I'm a proud master, so I decide to run anyway"
        # Else, I'm just a spare, so I listen to my master
        else:
            print "Someone asks me not to run"
            self.app.last_master_speack = time.time()
            self.app.must_run = False



    # Here a function called by check_shinken to get daemon status
    def get_satellite_status(self, daemon_type, daemon_name):
        daemon_name_attr = daemon_type+"_name"
        daemons = self.app.get_daemons(daemon_type)
        if daemons:
            for dae in daemons:
                if hasattr(dae, daemon_name_attr) and getattr(dae, daemon_name_attr) == daemon_name:
                    if hasattr(dae, 'alive') and hasattr(dae, 'spare'):
                        return {'alive' : dae.alive, 'spare' : dae.spare}
        return None

    # Here a function called by check_shinken to get daemons list
    def get_satellite_list(self, daemon_type):
        satellite_list = []
        daemon_name_attr = daemon_type+"_name"
        daemons = self.app.get_daemons(daemon_type)
        if daemons:
            for dae in daemons:
                if hasattr(dae, daemon_name_attr):
                    satellite_list.append(getattr(dae, daemon_name_attr))
                else:
                    #If one daemon has no name... ouch!
                    return None
            return satellite_list
        return None


    # Dummy call. We are a master, we managed what we want
    def what_i_managed(self):
        return []


    def get_all_states(self):
        res = {'arbiter' : self.app.conf.arbiterlinks,
               'scheduler' : self.app.conf.schedulerlinks,
               'poller' : self.app.conf.pollers,
               'reactionner' : self.app.conf.reactionners,
               'receiver' : self.app.conf.receivers,
               'broker' : self.app.conf.brokers}
        return res


# Main Skonf Class
class Skonf(Daemon):

    def __init__(self, config_files, is_daemon, do_replace, verify_only, debug, debug_file):
        
        super(Skonf, self).__init__('skonf', config_files[0], is_daemon, do_replace, debug, debug_file)
        
        self.config_files = config_files

        self.verify_only = verify_only

        self.broks = {}
        self.is_master = False
        self.me = None

        self.nb_broks_send = 0

        # Now tab for external_commands
        self.external_commands = []

        self.fifo = None

        # Use to know if we must still be alive or not
        self.must_run = True

        self.interface = IForArbiter(self)
        self.conf = Config()


    # Use for adding things like broks
    def add(self, b):
        if isinstance(b, Brok):
            self.broks[b.id] = b
        elif isinstance(b, ExternalCommand):
            self.external_commands.append(b)
        else:
            logger.log('Warning : cannot manage object type %s (%s)' % (type(b), b))

            

    def load_config_file(self):
        print "Loading configuration"
        # REF: doc/shinken-conf-dispatching.png (1)
        buf = self.conf.read_config(self.config_files)
        raw_objects = self.conf.read_config_buf(buf)

        print "Opening local log file"


        # First we need to get arbiters and modules first
        # so we can ask them some objects too
        self.conf.create_objects_for_type(raw_objects, 'arbiter')
        self.conf.create_objects_for_type(raw_objects, 'module')

        self.conf.early_arbiter_linking()

        # Search wich Arbiterlink I am
        for arb in self.conf.arbiterlinks:
            if arb.is_me():
                arb.need_conf = False
                self.me = arb
                self.is_master = not self.me.spare
                if self.is_master:
                    logger.log("I am the master Arbiter : %s" % arb.get_name())
                else:
                    logger.log("I am the spare Arbiter : %s" % arb.get_name())

                # Set myself as alive ;)
                self.me.alive = True
            else: #not me
                arb.need_conf = True

        if not self.me:
            sys.exit("Error: I cannot find my own Arbiter object, I bail out. \
                     To solve it, please change the host_name parameter in \
                     the object Arbiter in the file shinken-specific.cfg. \
                     With the value %s \
                     Thanks." % socket.gethostname())

        logger.log("My own modules : " + ','.join([m.get_name() for m in self.me.modules]))

        # we request the instances without them being *started* 
        # (for these that are concerned ("external" modules):
        # we will *start* these instances after we have been daemonized (if requested)
        self.modules_manager.set_modules(self.me.modules)
        self.do_load_modules()

        # Call modules that manage this read configuration pass
        self.hook_point('read_configuration')

        # Now we ask for configuration modules if they
        # got items for us
        for inst in self.modules_manager.instances:
            if 'configuration' in inst.phases:
                try :
                    r = inst.get_objects()
                except Exception, exp:
                    print "The instance %s raise an exception %s. I bypass it" % (inst.get_name(), str(exp))
                    continue
                
                types_creations = self.conf.types_creations
                for k in types_creations:
                    (cls, clss, prop) = types_creations[k]
                    if prop in r:
                        for x in r[prop]:
                            # test if raw_objects[k] is already set - if not, add empty array
                            if not k in raw_objects:
                                raw_objects[k] = []
                            # now append the object
                            raw_objects[k].append(x)
                        print "Added %i objects to %s from module %s" % (len(r[prop]), k, inst.get_name())


        ### Resume standard operations ###
        self.conf.create_objects(raw_objects)

        # Maybe conf is already invalid
        if not self.conf.conf_is_correct:
            sys.exit("***> One or more problems was encountered while processing the config files...")

        # Change Nagios2 names to Nagios3 ones
        self.conf.old_properties_names_to_new()

        # Manage all post-conf modules
        self.hook_point('early_configuration')

        # Create Template links
        self.conf.linkify_templates()

        # All inheritances
        self.conf.apply_inheritance()

        # Explode between types
        self.conf.explode()

        # Create Name reversed list for searching list
        self.conf.create_reversed_list()

        # Cleaning Twins objects
        self.conf.remove_twins()

        # Implicit inheritance for services
        self.conf.apply_implicit_inheritance()

        # Fill default values
        self.conf.fill_default()
        
        # Remove templates from config
        self.conf.remove_templates()

        # We removed templates, and so we must recompute the
        # search lists
        self.conf.create_reversed_list()
        
        # Pythonize values
        self.conf.pythonize()

        # Linkify objects each others
        self.conf.linkify()

        # applying dependencies
        self.conf.apply_dependencies()

        # Hacking some global parameter inherited from Nagios to create
        # on the fly some Broker modules like for status.dat parameters
        # or nagios.log one if there are no already available
        self.conf.hack_old_nagios_parameters()

        # Raise warning about curently unmanaged parameters
        if self.verify_only:
            self.conf.warn_about_unmanaged_parameters()

        # Exlode global conf parameters into Classes
        self.conf.explode_global_conf()

        # set ourown timezone and propagate it to other satellites
        self.conf.propagate_timezone_option()

        # Look for business rules, and create the dep tree
        self.conf.create_business_rules()
        # And link them
        self.conf.create_business_rules_dependencies()


        # Warn about useless parameters in Shinken
        if self.verify_only:
            self.conf.notice_about_useless_parameters()

        # Manage all post-conf modules
        self.hook_point('late_configuration')
        
        # Correct conf?
        self.conf.is_correct()

        #If the conf is not correct, we must get out now
        #if not self.conf.conf_is_correct:
        #    sys.exit("Configuration is incorrect, sorry, I bail out")

        # REF: doc/shinken-conf-dispatching.png (2)
        logger.log("Cutting the hosts and services into parts")
        self.confs = self.conf.cut_into_parts()

        # The conf can be incorrect here if the cut into parts see errors like
        # a realm with hosts and not schedulers for it
        if not self.conf.conf_is_correct:
            self.conf.show_errors()
            sys.exit("Configuration is incorrect, sorry, I bail out")

        logger.log('Things look okay - No serious problems were detected during the pre-flight check')

        # Now clean objects of temporary/unecessary attributes for live work:
        self.conf.clean()

        # Exit if we are just here for config checking
        if self.verify_only:
            sys.exit(0)

        # Some properties need to be "flatten" (put in strings)
        # before being send, like realms for hosts for example
        # BEWARE: after the cutting part, because we stringify some properties
        self.conf.prepare_for_sending()

        # Ok, here we must check if we go on or not.
        # TODO : check OK or not
        self.use_local_log = self.conf.use_local_log
        self.local_log = self.conf.local_log
        self.pidfile = os.path.abspath(self.conf.lock_file)
        self.idontcareaboutsecurity = self.conf.idontcareaboutsecurity
        self.user = self.conf.shinken_user
        self.group = self.conf.shinken_group
        
        # If the user set a workdir, let use it. If not, use the
        # pidfile directory
        if self.conf.workdir == '':
            self.workdir = os.path.abspath(os.path.dirname(self.pidfile))
        else:
            self.workdir = self.conf.workdir
        #print "DBG curpath=", os.getcwd()
        #print "DBG pidfile=", self.pidfile
        #print "DBG workdir=", self.workdir

        ##  We need to set self.host & self.port to be used by do_daemon_init_and_start
        self.host = self.me.address
        self.port = 8766#self.me.port
        
        logger.log("Configuration Loaded")
        print ""


    def load_web_configuration(self):
        self.plugins = []

        self.http_port = 7766#int(getattr(modconf, 'port', '7767'))
        self.http_host = '0.0.0.0'#getattr(modconf, 'host', '0.0.0.0')
        self.auth_secret = 'CHANGE_ME'.encode('utf8', 'replace')#getattr(modconf, 'auth_secret').encode('utf8', 'replace')
        self.http_backend = 'auto'#getattr(modconf, 'http_backend', 'auto')
        self.login_text = None#getattr(modconf, 'login_text', None)
        self.allow_html_output = False#to_bool(getattr(modconf, 'allow_html_output', '0'))
        self.remote_user_enable = '0'#getattr(modconf, 'remote_user_enable', '0')
        self.remote_user_variable = 'X_REMOTE_USER'#getattr(modconf, 'remote_user_variable', 'X_REMOTE_USER')

        # Load the photo dir and make it a absolute path
        self.photo_dir = 'photos'#getattr(modconf, 'photo_dir', 'photos')
        self.photo_dir = os.path.abspath(self.photo_dir)
        print "Webui : using the backend", self.http_backend



    # Main loop function
    def main(self):
        try:
            # Log will be broks
            for line in self.get_header():
                self.log.log(line)

            self.load_config_file()
            self.load_web_configuration()

            self.do_daemon_init_and_start()
            self.uri_arb = self.pyro_daemon.register(self.interface, "ForArbiter")

            # ok we are now fully daemon (if requested)
            # now we can start our "external" modules (if any) :
            self.modules_manager.start_external_instances()
            
            # Ok now we can load the retention data
            self.hook_point('load_retention')

            ## And go for the main loop
            self.do_mainloop()
        except SystemExit, exp:
            # With a 2.4 interpreter the sys.exit() in load_config_file
            # ends up here and must be handled.
            sys.exit(exp.code)
        except Exception, exp:
            logger.log("CRITICAL ERROR: I got an unrecoverable error. I have to exit")
            logger.log("You can log a bug ticket at https://github.com/naparuba/shinken/issues/new to get help")
            logger.log("Back trace of it: %s" % (traceback.format_exc()))
            raise


    def setup_new_conf(self):
        """ Setup a new conf received from a Master arbiter. """
        conf = self.new_conf
        self.new_conf = None
        self.cur_conf = conf
        self.conf = conf        
        for arb in self.conf.arbiterlinks:
            if (arb.address, arb.port) == (self.host, self.port):
                self.me = arb
                arb.is_me = lambda: True  # we now definitively know who we are, just keep it.
            else:
                arb.is_me = lambda: False # and we know who we are not, just keep it.


    def do_loop_turn(self):
        # If I am a spare, I wait for the master arbiter to send me
        # true conf. When
        if self.me.spare:
            self.wait_for_initial_conf()
            if not self.new_conf:
                return
            self.setup_new_conf()
            print "I must wait now"
            self.wait_for_master_death()

        if self.must_run:
            # Main loop
            self.run()


    # Get 'objects' from external modules
    # It can be used for get external commands for example
    def get_objects_from_from_queues(self):
        for f in self.modules_manager.get_external_from_queues():
            #print "Groking from module instance %s" % f
            while True:
                try:
                    o = f.get(block=False)
                    self.add(o)
                except Empty:
                    break
                # Maybe the queue got problem
                # log it and quit it
                except (IOError, EOFError), exp:
                    logger.log("Warning : an external module queue got a problem '%s'" % str(exp))
                    break

    # We wait (block) for arbiter to send us something
    def wait_for_master_death(self):
        logger.log("Waiting for master death")
        timeout = 1.0
        self.last_master_speack = time.time()

        # Look for the master timeout
        master_timeout = 300
        for arb in self.conf.arbiterlinks:
            if not arb.spare:
                master_timeout = arb.check_interval * arb.max_check_attempts
        logger.log("I'll wait master for %d seconds" % master_timeout)

        
        while not self.interrupted:
            elapsed, _, tcdiff = self.handleRequests(timeout)
            # if there was a system Time Change (tcdiff) then we have to adapt last_master_speak:
            if self.new_conf:
                self.setup_new_conf()
            if tcdiff:
                self.last_master_speack += tcdiff
            if elapsed:
                self.last_master_speack = time.time()
                timeout -= elapsed
                if timeout > 0:
                    continue
            
            timeout = 1.0            
            sys.stdout.write(".")
            sys.stdout.flush()

            # Now check if master is dead or not
            now = time.time()
            if now - self.last_master_speack > master_timeout:
                logger.log("Master is dead!!!")
                self.must_run = True
                break

    # Take all external commands, make packs and send them to
    # the schedulers
    def push_external_commands_to_schedulers(self):
        # Now get all external commands and put them into the
        # good schedulers
        for ext_cmd in self.external_commands:
            self.external_command.resolve_command(ext_cmd)

        # Now for all alive schedulers, send the commands
        for sched in self.conf.schedulerlinks:
            cmds = sched.external_commands
            if len(cmds) > 0 and sched.alive:
                safe_print("Sending %d commands" % len(cmds), 'to scheduler', sched.get_name())
                sched.run_external_commands(cmds)
            # clean them
            sched.external_commands = []


    # Main function
    def run(self):
        # Before running, I must be sure who am I
        # The arbiters change, so we must refound the new self.me
        for arb in self.conf.arbiterlinks:
            if arb.is_me():
                self.me = arb

        if self.conf.human_timestamp_log:
            logger.set_human_format()
        
        suppl_socks = None

        # Now create the external commander. It's just here to dispatch
        # the commands to schedulers
        e = ExternalCommandManager(self.conf, 'dispatcher')
        e.load_arbiter(self)
        self.external_command = e

        print "Run baby, run..."
        timeout = 1.0             
        
        while self.must_run and not self.interrupted:
            
            elapsed, ins, _ = self.handleRequests(timeout, suppl_socks)
            
            # If FIFO, read external command
            if ins:
                now = time.time()
                ext_cmds = self.external_command.get()
                if ext_cmds:
                    for ext_cmd in ext_cmds:
                        self.external_commands.append(ext_cmd)
                else:
                    self.fifo = self.external_command.open()
                    if self.fifo is not None:
                        suppl_socks = [ self.fifo ]
                    else:
                        suppl_socks = None
                elapsed += time.time() - now

            if elapsed or ins:
                timeout -= elapsed
                if timeout > 0: # only continue if we are not over timeout
                    continue  
            
            # Timeout
            timeout = 1.0 # reset the timeout value

            # Try to see if one of my module is dead, and
            # try to restart previously dead modules :)
            self.check_and_del_zombie_modules()
            
            # Call modules that manage a starting tick pass
            self.hook_point('tick')
            print "Tick"

            # If ask me to dump my memory, I do it
            if self.need_dump_memory:
                self.dump_memory()
                self.need_dump_memory = False


    def get_daemons(self, daemon_type):
        """ Returns the daemons list defined in our conf for the given type """
        # We get the list of the daemons from their links
        # 'schedulerlinks' for schedulers, 'arbiterlinks' for arbiters
        # and 'pollers', 'brokers', 'reactionners' for the others
        if (daemon_type == 'scheduler' or daemon_type == 'arbiter'):
            daemon_links = daemon_type+'links'
        else:
            daemon_links = daemon_type+'s'

        # shouldn't the 'daemon_links' (whetever it is above) be always present ?
        return getattr(self.conf, daemon_links, None)

    # Helper functions for retention modules
    # So we give our broks and external commands
    def get_retention_data(self):
        r = {}
        r['broks'] = self.broks
        r['external_commands'] = self.external_commands
        return r

    # Get back our data from a retention module
    def restore_retention_data(self, data):
        broks = data['broks']
        external_commands = data['external_commands']
        self.broks.update(broks)
        self.external_commands.extend(external_commands)
