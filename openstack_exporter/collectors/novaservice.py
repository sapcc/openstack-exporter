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

from openstack_exporter import BaseCollector

LOG = logging.getLogger('openstack_exporter.exporter')


class NovaServiceCollector(BaseCollector.BaseCollector):

    def describe(self):
        yield GaugeMetricFamily('nova_compute_status',
                               'An administrator has enabled or disabled that service')

        yield GaugeMetricFamily('nova_compute_state',
                               'That running service is working or not')

    def collect(self):
        # logic goes in here
        LOG.info("Collect nova backend info. {}".format(
            self.config['auth_url']
        ))

        g_status = GaugeMetricFamily('nova_compute_service_status',
                                      'An admin has enabled or disabled that service',
                                      labels=['availability_zone', 'host'])

        g_state  = GaugeMetricFamily('nova_compute_service_state',
                                      'That running service is working or not',
                                      labels=['availability_zone', 'host'])

        for service in self.client.compute.services(binary='nova-compute'):

            LOG.debug('host-{} status-{} state-{} reason-{}'.format(
                service['host'], service['status'], service['state'], service['disabled_reason']))

            g_status.add_metric([service['availability_zone'], service['host']],
                                value=(1 if service['status'] == 'enabled' else 0))

            g_state.add_metric([service['availability_zone'], service['host']],
                               value=(1 if service['state'] == 'up' else 0))

        yield g_status
        yield g_state