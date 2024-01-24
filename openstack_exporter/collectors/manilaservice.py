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
from manilaclient import client as manila
from openstack_exporter import BaseCollector

LOG = logging.getLogger('openstack_exporter.exporter')

class ManilaServiceCollector(BaseCollector.BaseCollector):

    def __init__(self, openstack_config, collector_config):
        super().__init__(openstack_config, collector_config)
        self._init_manila_client()

    def _init_manila_client(self):
        """Initialize the Manila client."""
        self.manila_client = self._create_manila_client()

    def _create_manila_client(self):
        """Create a Manila client."""
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
        return manila.Client('2.65', session=sess, region_name=self.region)

    def _renew_manila_client(self):
        """Renew the Manila client."""
        LOG.info("Renewing Manila client")
        self._init_manila_client()

    def describe(self):
        yield GaugeMetricFamily('manila_service_status',
                                'An admin has enabled or disabled the Manila service',
                                labels=['service', 'host', 'zone'])
        yield GaugeMetricFamily('manila_service_state',
                                'State of the running Manila service',
                                labels=['service', 'host', 'zone'])

    def collect(self):
        LOG.info("Collect Manila service info. {}".format(self.config['auth_url']))

        try:
            services = self.manila_client.services.list()
        except Exception as e:
            if "requires authentication" in str(e):
                LOG.info("Authentication required, renewing Manila client")
                self._renew_manila_client()
                services = self.manila_client.services.list()
            else:
                LOG.error(f"Error while collecting Manila service metrics: {e}")
                return

        g_status = GaugeMetricFamily('manila_service_status',
                                     'An admin has enabled or disabled the Manila service',
                                     labels=['service', 'host', 'zone'])
        g_state = GaugeMetricFamily('manila_service_state',
                                    'State of the running Manila service',
                                     labels=['service', 'host', 'zone'])

        for service in services:
            LOG.debug(f"Service: {service.binary}, Host: {service.host}, "
                      f"Zone: {service.zone}, Status: {service.status}, State: {service.state}")

            g_status.add_metric([service.binary, service.host, service.zone],
                                1 if service.status == 'enabled' else 0)
            g_state.add_metric([service.binary, service.host, service.zone],
                                1 if service.state == 'up' else 0)

        yield g_status
        yield g_state
