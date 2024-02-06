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

import logging
from prometheus_client.core import GaugeMetricFamily
from keystoneauth1 import session
from keystoneauth1.identity import v3
from cinderclient import client as cinder
from openstack_exporter import BaseCollector

LOG = logging.getLogger('openstack_exporter.exporter')

class CinderServiceCollector(BaseCollector.BaseCollector):
    version = "1.0.0"

    def __init__(self, openstack_config, collector_config):
        super().__init__(openstack_config, collector_config)
        self.cinder_client = self._create_cinder_client()

    def _create_cinder_client(self):
        """Create a Cinder client"""
        os_auth_url = self.config['auth_url']
        os_username = self.config['username']
        os_password = self.config['password']
        os_project_name = self.config['project_name']
        os_project_domain_name = self.config['project_domain_name']
        os_user_domain_name = self.config['user_domain_name']

        auth = v3.Password(auth_url=os_auth_url,
                           username=os_username,
                           password=os_password,
                           project_name=os_project_name,
                           project_domain_name=os_project_domain_name,
                           user_domain_name=os_user_domain_name)

        sess = session.Session(auth=auth)
        return cinder.Client('3.64', session=sess, region_name=self.region) # Adjust API version when required

    def describe(self):
        yield GaugeMetricFamily('cinder_service_status',
                                'Current status of Cinder services (enabled/disabled)',
                                labels=['service', 'host', 'zone'])
        yield GaugeMetricFamily('cinder_service_state',
                                'Current state of Cinder services (up/down)',
                                labels=['service', 'host', 'zone'])

    def collect(self):
        LOG.info("Collecting Cinder service info.")
        try:
            services = self.cinder_client.services.list()
        except Exception as e:
            LOG.error(f"Error while collecting Cinder service metrics: {e}")
            return

        g_status = GaugeMetricFamily('cinder_service_status',
                                     'Current status of Cinder services (enabled/disabled)',
                                     labels=['service', 'host', 'zone'])
        g_state = GaugeMetricFamily('cinder_service_state',
                                    'Current state of Cinder services (up/down)',
                                    labels=['service', 'host', 'zone'])

        for service in services:
            LOG.debug(f"Service: {service.binary}, Host: {service.host}, "
                      f"Zone: {service.zone}, Status: {service.status}, State: {service.state}")

            status_value = 1 if service.status == 'enabled' else 0
            state_value = 1 if service.state == 'up' else 0
            g_status.add_metric([service.binary, service.host, service.zone], status_value)
            g_state.add_metric([service.binary, service.host, service.zone], state_value)

        yield g_status
        yield g_state
