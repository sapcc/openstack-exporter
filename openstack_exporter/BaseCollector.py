# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

from abc import ABC, abstractmethod
import logging
import sys

import openstack
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

LOG = logging.getLogger('openstack_exporter.exporter')
openstack.enable_logging(debug=False, http_debug=False, stream=sys.stdout)


class BaseCollector(ABC):

    def __init__(self, openstack_config):
        self.config = openstack_config
        self.region = self.config['region']
        self.client = self._connect()

    def _connect(self):
        """Connect to the OpenStack Service."""

        LOG.debug("Connecting to Openstack API {}".format(
            self.config['auth_url']
        ))
        conn = openstack.connect(
            auth_url=self.config['auth_url'],
            username=self.config['username'],
            password=self.config['password'],
            user_domain_name=self.config['user_domain_name'],
            project_domain_name=self.config['project_domain_name'],
            project_name=self.config['project_name'],
            region_name=self.region,
            app_name='Openstack prometheus exporter',
            app_version='1.0'
        )
        LOG.debug("Connected to OpenStack {}".format(
            self.config['auth_url']
        ))
        return conn

    @abstractmethod
    def describe(self):
        pass

    @abstractmethod
    def collect(self):
        pass
