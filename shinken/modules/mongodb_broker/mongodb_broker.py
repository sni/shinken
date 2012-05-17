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

import pprint
import pymongo
from shinken.macroresolver import MacroResolver
from shinken.objects.config import Config
from shinken.bin import VERSION
from shinken.external_command import ExternalCommand
from shinken.log import logger
from shinken.basemodule import BaseModule

version = 0.1

class Mongodb_broker(BaseModule):
    """
     This broker module puts objects into a mongodb.
    """


    def __init__(self, modconf):
        BaseModule.__init__(self, modconf)
        # mongodb://host1,host2,host3/?safe=true;w=2;wtimeoutMS=2000
        self.mongodb_uri = getattr(modconf, 'mongodb_uri', None)
        self.database    = getattr(modconf, 'database', 'shinken')
        self.version     = version
        self.pp          = pprint.PrettyPrinter()


    # database connect
    def init(self):
        logger.info("[mongodb_broker] I connect to Mongodb database")
        self.connect_database()


    # internal loop
    def do_loop_turn(self):
        try:
            l = self.to_q.get() # this may block
        except IOError, e:
            if e.errno != os.errno.EINTR:
                raise
        else:
            for b in l:
                b.prepare()
                self.manage_brok(b)
        self.check_commands();


    # functions will be like manage_ type _brok
    def manage_brok(self, b):
        logger.info("[mongodb_broker] %s" % self.pp.pformat(b.type))
        return BaseModule.manage_brok(self, b)


    # Create the database connection
    def connect_database(self):
        # First connect to server
        self.conn = pymongo.Connection(self.mongodb_uri)

        tables = ['commands', 'comments', 'contacts', 'contactgroups', 'downtimes', 'hosts',
                  'hostgroups', 'logs', 'program_status', 'services', 'servicegroups',
                  'status', 'timeperiods'
                 ]

        # OK, now we store ours dbs
        self.db = self.conn[self.database]
        # An we clean them
        for table in tables:
            # We get the database. From now, we drop all the database and recreate a new one
            # TODO : don't drop tables
            self.db.drop_collection(table)
            self.db.create_collection(table)
            self.db[table].ensure_index('_key');


    # create document
    def create_document(self, table, data, key):
        if key != None:
            data['_key'] = key
            self.db[table].update({"_key": key}, data, True)
        else:
            self.db[table].insert(data)


    def check_commands(self):
        cmd = self.db['cmd'].find_one()
        if cmd != None:
            res = self.db['cmd'].remove(cmd['_id'], True)
            # only execute command if delete returned 1 to ensure the command
            # will be only executed once
            if res['n'] == 1:
                logger.info("[mongodb_broker] new command: [%s] %s" % (cmd['time'], cmd['cmd']))
                e = ExternalCommand("[%s] %s" % (cmd['time'], cmd['cmd'] ))
                self.from_q.put(e)
            return
        logger.debug("[mongodb_broker] no new commands")


    # Program status is .. status of program? :)
    # Like pid, daemon mode, last activity, etc
    # We aleady clean database, so insert
    def manage_program_status_brok(self, b):
        d = b.data
        data = {
            'accept_passive_host_checks':       self.bool2int(d['passive_host_checks_enabled']),
            'accept_passive_service_checks':    self.bool2int(d['passive_service_checks_enabled']),
            'check_external_commands':          self.bool2int(d['check_external_commands']),
            'check_host_freshness':             self.bool2int(d['check_host_freshness']),
            'check_service_freshness':          self.bool2int(d['check_service_freshness']),
            'enable_event_handlers':            self.bool2int(d['event_handlers_enabled']),
            'enable_flap_detection':            self.bool2int(d['flap_detection_enabled']),
            'enable_notifications':             self.bool2int(d['notifications_enabled']),
            'execute_host_checks':              self.bool2int(d['active_host_checks_enabled']),
            'execute_service_checks':           self.bool2int(d['active_service_checks_enabled']),
            'last_command_check':               d['last_command_check'],
            'last_log_rotation':                d['last_log_rotation'],
            'data_source_version':              'MongoDB %2.1f' % self.version,
            'nagios_pid':                       d['pid'],
            'obsess_over_hosts':                self.bool2int(d['obsess_over_hosts']),
            'obsess_over_services':             self.bool2int(d['obsess_over_services']),
            'process_performance_data':         self.bool2int(d['process_performance_data']),
            'program_start':                    d['program_start'],
            'program_version':                  VERSION,
            'interval_length':                  60, # TODO: implement
        }
        self.create_document('status', data, b.data['instance_name'])


    # Initial service status is at start. We need to insert because we
    # clean the base
    def manage_initial_service_status_brok(self, b):
        d = b.data
        key = '%s,%s' % (d['host_name'], d['service_description'])
        data = {
            'accept_passive_checks':        self.bool2int(d['passive_checks_enabled']),
            'acknowledged':                 0, # TODO: implement
            'action_url':                   d['action_url'],
            'action_url_expanded':          '', # TODO: implement
            'active_checks_enabled':        self.bool2int(d['active_checks_enabled']),
            'check_command':                '', # TODO: implement
            'check_interval':               d['check_interval'],
            'check_options':                0, # TODO: implement
            'check_period':                 d['check_period'],
            'check_type':                   d['check_type'],
            'checks_enabled':               self.bool2int(d['active_checks_enabled']),
            'comments':                     [], # TODO: implement
            'current_attempt':              d['attempt'],
            'current_notification_number':  d['current_notification_number'],
            'description':                  d['service_description'],
            'event_handler':                '', # TODO: implement
            'event_handler_enabled':        self.bool2int(d['event_handler_enabled']),
            'custom_variable_names':        [], # TODO: implement
            'custom_variable_values':       [], # TODO: implement
            'execution_time':               d['execution_time'],
            'first_notification_delay':     d['first_notification_delay'],
            'flap_detection_enabled':       self.bool2int(d['flap_detection_enabled']),
            'groups':                       [], # TODO: implement
            'has_been_checked':             self.bool2int(d['has_been_checked']),
            'high_flap_threshold':          d['high_flap_threshold'],
            'icon_image':                   d['icon_image'],
            'icon_image_alt':               d['icon_image_alt'],
            'icon_image_expanded':          '', # TODO: implement
            'is_executing':                 0,  # TODO: check if possible
            'is_flapping':                  self.bool2int(d['is_flapping']),
            'last_check':                   d['last_chk'],
            'last_notification':            d['last_notification'],
            'last_state_change':            d['last_state_change'],
            'latency':                      d['latency'],
            'long_plugin_output':           d['long_output'],
            'low_flap_threshold':           d['low_flap_threshold'],
            'max_check_attempts':           d['max_check_attempts'],
            'next_check':                   d['next_chk'],
            'notes':                        d['notes'],
            'notes_expanded':               '', # TODO: implement
            'notes_url':                    d['notes_url'],
            'notes_url_expanded':           '', # TODO: implement
            'notification_interval':        d['notification_interval'],
            'notification_period':          d['notification_period'],
            'notifications_enabled':        self.bool2int(d['notifications_enabled']),
            'obsess_over_service':          self.bool2int(d['obsess_over_service']),
            'percent_state_change':         d['percent_state_change'],
            'perf_data':                    d['perf_data'],
            'plugin_output':                d['output'],
            'process_performance_data':     self.bool2int(d['process_perf_data']),
            'retry_interval':               d['retry_interval'],
            'scheduled_downtime_depth':     d['scheduled_downtime_depth'],
            'state':                        d['state_id'],
            'state_type':                   self.state_type2int(d['state_type']),
            'modified_attributes_list':     d['modified_attributes'],
            'last_time_critical':           d['last_time_critical'],
            'last_time_ok':                 d['last_time_ok'],
            'last_time_unknown':            d['last_time_unknown'],
            'last_time_warning':            d['last_time_warning'],
            'display_name':                 d['display_name'],

            'host_acknowledged':            0,  # TODO: implement
            'host_action_url_expanded':     '', # TODO: implement
            'host_active_checks_enabled':   0,  # TODO: implement
            'host_address':                 '', # TODO: implement
            'host_alias':                   '', # TODO: implement
            'host_checks_enabled':          0,  # TODO: implement
            'host_check_type':              0,  # TODO: implement
            'host_comments':                [], # TODO: implement
            'host_groups':                  [], # TODO: implement
            'host_has_been_checked':        '', # TODO: implement
            'host_icon_image_expanded':     '', # TODO: implement
            'host_icon_image_alt':          '', # TODO: implement
            'host_is_executing':            0,  # TODO: implement
            'host_is_flapping':             0,  # TODO: implement
            'host_name':                    '', # TODO: implement
            'host_notes_url_expanded':      '', # TODO: implement
            'host_notifications_enabled':   0,  # TODO: implement
            'host_scheduled_downtime_depth':0,  # TODO: implement
            'host_state':                   0,  # TODO: implement
            'host_accept_passive_checks':   0,  # TODO: implement
            'host_display_name':            '', # TODO: implement
            'host_custom_variable_names':   [], # TODO: implement
            'host_custom_variable_values':  [], # TODO: implement
        }
        self.create_document('services', data, key)



    # A host has just been created, database is clean, we INSERT it
    def manage_initial_host_status_brok(self, b):
        d = b.data
        data = {
            'accept_passive_checks':        self.bool2int(d['passive_checks_enabled']),
            'acknowledged':                 0, # TODO: implement
            'action_url':                   d['action_url'],
            'action_url_expanded':          '', # TODO: implement
            'active_checks_enabled':        self.bool2int(d['active_checks_enabled']),
            'address':                      d['address'],
            'alias':                        d['alias'],
            'check_command':                '', # TODO: implement
            'check_freshness':              self.bool2int(d['check_freshness']),
            'check_interval':               d['check_interval'],
            'check_options':                0, # TODO: implement
            'check_period':                 d['check_period'],
            'check_type':                   d['check_type'],
            'checks_enabled':               self.bool2int(d['active_checks_enabled']),
            'childs':                       [], # TODO: implement
            'comments':                     [], # TODO: implement
            'current_attempt':              d['attempt'],
            'current_notification_number':  d['current_notification_number'],
            'event_handler_enabled':        self.bool2int(d['event_handler_enabled']),
            'execution_time':               d['execution_time'],
            'custom_variable_names':        [], # TODO: implement
            'custom_variable_values':       [], # TODO: implement
            'first_notification_delay':     d['first_notification_delay'],
            'flap_detection_enabled':       self.bool2int(d['flap_detection_enabled']),
            'groups':                       [], # TODO: implement
            'has_been_checked':             self.bool2int(d['has_been_checked']),
            'high_flap_threshold':          d['high_flap_threshold'],
            'icon_image':                   d['icon_image'],
            'icon_image_alt':               d['icon_image_alt'],
            'icon_image_expanded':          '', # TODO: implement
            'is_executing':                 0,  # TODO: check if possible
            'is_flapping':                  self.bool2int(d['is_flapping']),
            'last_check':                   d['last_chk'],
            'last_notification':            d['last_notification'],
            'last_state_change':            d['last_state_change'],
            'latency':                      d['latency'],
            'long_plugin_output':           d['long_output'],
            'low_flap_threshold':           d['low_flap_threshold'],
            'max_check_attempts':           d['max_check_attempts'],
            'name':                         d['host_name'],
            'next_check':                   d['next_chk'],
            'notes':                        d['notes'],
            'notes_expanded':               '', # TODO: implement
            'notes_url':                    d['notes_url'],
            'notes_url_expanded':           '', # TODO: implement
            'notification_interval':        d['notification_interval'],
            'notification_period':          d['notification_period'],
            'notifications_enabled':        self.bool2int(d['notifications_enabled']),
            'num_services_crit':            0, # TODO: implement
            'num_services_ok':              0, # TODO: implement
            'num_services_pending':         0, # TODO: implement
            'num_services_unknown':         0, # TODO: implement
            'num_services_warn':            0, # TODO: implement
            'num_services':                 0, # TODO: implement
            'obsess_over_host':             self.bool2int(d['obsess_over_host']),
            'parents':                      [], # TODO: implement
            'percent_state_change':         d['percent_state_change'],
            'perf_data':                    d['perf_data'],
            'plugin_output':                d['output'],
            'process_performance_data':     self.bool2int(d['process_perf_data']),
            'retry_interval':               d['retry_interval'],
            'scheduled_downtime_depth':     d['scheduled_downtime_depth'],
            'state':                        d['state_id'],
            'state_type':                   self.state_type2int(d['state_type']),
            'modified_attributes_list':     d['modified_attributes'],
            'last_time_down':               d['last_time_down'],
            'last_time_unreachable':        d['last_time_unreachable'],
            'last_time_up':                 d['last_time_up'],
            'display_name':                 d['display_name'],
        }
        self.create_document('hosts', data, b.data['host_name'])


    # initial hostgroups
    def manage_initial_hostgroup_status_brok(self, b):
        d = b.data
        data = {
            'name':       d['hostgroup_name'],
            'alias':      d['alias'],
            'members':    [x[1] for x in d['members']],
            'action_url': d['action_url'],
            'notes':      d['notes'],
            'notes_url':  d['notes_url'],
        }
        self.create_document('hostgroups', data, d['hostgroup_name'])


    # initial servicegroups
    def manage_initial_servicegroup_status_brok(self, b):
        d = b.data
        data = {
            'name':       d['servicegroup_name'],
            'alias':      d['alias'],
            'members':    [], # TODO: implement
            'action_url': d['action_url'],
            'notes':      d['notes'],
            'notes_url':  d['notes_url'],
        }
        self.create_document('servicegroups', data, d['servicegroup_name'])


    # initial contacts
    def manage_initial_contact_status_brok(self, b):
        d = b.data
        data = {
            'name':                        d['contact_name'],
            'alias':                       d['alias'],
            'email':                       d['email'],
            'pager':                       d['pager'],
            'can_submit_commands':         self.bool2int(d['can_submit_commands']),
            'service_notification_period': d['service_notification_period'],
            'host_notification_period':    d['host_notification_period'],
        }
        self.create_document('contacts', data, d['contact_name'])


    # initial contactgroups
    def manage_initial_contactgroup_status_brok(self, b):
        d = b.data
        data = {
            'name':    d['contactgroup_name'],
            'alias':   d['alias'],
            'members': [x[1] for x in d['members']],
        }
        self.create_document('contactgroups', data, d['contactgroup_name'])


    # initial timeperiods
    def manage_initial_timeperiod_status_brok(self, b):
        d = b.data
        data = {
            'name':      d['timeperiod_name'],
            'alias':     d['alias'],
            'exclusion': '',
            'monday':    '',
            'tuesday':   '',
            'wednesday': '',
            'thursday':  '',
            'friday':    '',
            'saturday':  '',
            'sunday':    '',
        }
        self.create_document('timeperiods', data, d['timeperiod_name'])


    # initial commands
    def manage_initial_command_status_brok(self, b):
        d = b.data
        data = {
            'name':      d['command_name'],
            'line':      d['command_line'],
        }
        self.create_document('commands', data, d['command_name'])

    def manage_log_brok(self, b):
        return
        # TODO: use livestatus parser
        d = b.data
        data = {
            'class':                    '',
            'time':                     '',
            'type':                     '',
            'state':                    '',
            'host_name':                '',
            'service_description':      '',
            'plugin_output':            '',
            'message':                  '',
            'options':                  '',
            'contact_name':             '',
            'command_name':             '',
            'state_type':               '',
            'current_host_groups':      '',
            'current_service_groups':   '',
        }
        self.create_document('log', data, None)


    # updating program status
    def manage_update_program_status_brok(self, b):
        self.manage_program_status_brok(b);


    # service check result?
    #def manage_service_check_result_brok(self, b):
    #    self.manage_initial_service_status_brok(b);


    # new service status?
    def manage_update_service_status_brok(self, b):
        self.manage_initial_service_status_brok(b);


    # host check result?
    #def manage_host_check_result_brok(self, b):
    #    self.manage_initial_host_status_brok(b);


    # new host status
    def manage_update_host_status_brok(self, b):
        self.manage_initial_host_status_brok(b);


    # convert bool to int
    def bool2int(self, b):
        if b:
            return 1
        return 0


    # convert state string to int
    def state_type2int(self, s):
        if s == 'HARD':
            return 1
        return 0
