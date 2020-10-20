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
from prometheus_client.core import GaugeMetricFamily, InfoMetricFamily

from openstack_exporter import BaseCollector

LOG = logging.getLogger('openstack_exporter.exporter')


class CinderBackendCollector(BaseCollector.BaseCollector):

    def describe(self):
        yield InfoMetricFamily('cinder_provisioning_type',
                               'Cinder provisioning type')
        yield GaugeMetricFamily('cinder_total_capacity_gib',
                                'Cinder total capacity in GiB')
        yield GaugeMetricFamily('cinder_free_capacity_gib',
                                'Cinder free capacity in GiB')
        yield GaugeMetricFamily('cinder_allocated_capacity_gib',
                                'Cinder allocated capacity in GiB')
        yield GaugeMetricFamily('cinder_max_oversubscription_ratio',
                                'Cinder max overcommit ratio')
        yield GaugeMetricFamily('cinder_overcommit_ratio',
                                'Cinder Overcommit ratio')
        yield GaugeMetricFamily('cinder_free_until_overcommit_gib',
                                'Cinder free space until Overcommit reached')

    def _can_overcommit(self, caps, volume_types):
        can_overcommit = False
        # Find the volume type associated with the backend
        vt = volume_types[caps['volume_backend_name']]

        # Only allow overcommit if the volume type that matches
        # The backend is thin provisioned.
        if (vt['extra_specs'].get('provisioning:type', 'thin') == 'thin'):
            can_overcommit = True

        return can_overcommit

    def collect(self):
        # logic goes in here
        LOG.info("Collect cinder backend info. {}".format(
            self.config['auth_url']
        ))

        v_types = list(self.client.volume.types())
        # Ignore volume types that aren't tied to a backend.
        volume_types = (
            {vt['extra_specs']['volume_backend_name']:
             vt for vt in v_types if 'volume_backend_name' in vt['extra_specs']})

        pools = self.client.volume.backend_pools()
        for pool in pools:
            caps = pool['capabilities']
            backend = caps['volume_backend_name']
            shard_name = caps['vcenter-shard']
            LOG.debug("Got stats for pool {} ({}/{})".format(
                self.region,
                shard_name,
                backend))

            # The volume backend can do overcommit if and only if
            # the backdnd and volume type are set to thin provisioning.
            can_overcommit = self._can_overcommit(caps, volume_types)

            g = InfoMetricFamily('cinder_provisioning_type',
                                 'Cinder provisioning type',
                                 labels=['backend', 'shard'])
            provisioning_type = ('thin' if can_overcommit else 'thick')
            g.add_metric([backend, shard_name],
                         value={'provisioning_type': provisioning_type})
            yield g

            g = GaugeMetricFamily('cinder_total_capacity_gib',
                                  'Cinder total capacity in GiB',
                                  labels=['backend', 'shard'])
            g.add_metric([backend, shard_name],
                         value=caps['total_capacity_gb'])
            yield g

            g = GaugeMetricFamily('cinder_free_capacity_gib',
                                  'Cinder free capacity in GiB',
                                  labels=['backend', 'shard'])
            g.add_metric([backend, shard_name],
                         value=caps['free_capacity_gb'])
            yield g

            g = GaugeMetricFamily('cinder_allocated_capacity_gib',
                                  'Cinder allocated capacity in GiB',
                                  labels=['backend', 'shard'])
            g.add_metric([backend, shard_name],
                         value=caps['allocated_capacity_gb'])
            yield g

            if can_overcommit:
                g = GaugeMetricFamily('cinder_max_oversubscription_ratio',
                                      'Cinder max overcommit ratio',
                                      labels=['backend', 'shard'])
                g.add_metric([backend, shard_name],
                             value=caps['max_over_subscription_ratio'])
                yield g

                if caps['total_capacity_gb']:
                    overcommit_ratio = (caps['allocated_capacity_gb'] /
                                        caps['total_capacity_gb'])
                else:
                    overcommit_ratio = 0
                g = GaugeMetricFamily('cinder_overcommit_ratio',
                                      'Cinder Overcommit ratio',
                                      labels=['backend', 'shard'])
                g.add_metric([backend, shard_name],
                             value=overcommit_ratio)
                yield g

                free_until_overcommit = 0
                if (caps['total_capacity_gb'] and
                   'max_over_subscription_ratio' in caps):
                    tmp = (caps['total_capacity_gb'] *
                        float(caps['max_over_subscription_ratio']))
                    free_until_overcommit = tmp - caps['allocated_capacity_gb']
                g = GaugeMetricFamily('cinder_free_until_overcommit_gib',
                                      'Cinder free space until Overcommit in GiB',
                                      labels=['backend', 'shard'])
                g.add_metric([backend, shard_name],
                             value=free_until_overcommit)
                yield g

            LOG.debug('({}/{})-provisioning_type = {}'.format(
                shard_name, caps['volume_backend_name'],
                provisioning_type
            ))
            LOG.debug('({}/{})-total_capacity_gb = {}'.format(
                shard_name, caps['volume_backend_name'],
                caps['total_capacity_gb']
            ))
            LOG.debug('({}/{})-free_capacity_gb = {}'.format(
                shard_name, caps['volume_backend_name'],
                caps['free_capacity_gb']
            ))
            LOG.debug('({}/{})-allocated_capacity_gb = {}'.format(
                shard_name, caps['volume_backend_name'],
                caps['allocated_capacity_gb']
            ))

            if can_overcommit:
                LOG.debug('({}/{})-free_until_overcommit = {}'.format(
                    shard_name, caps['volume_backend_name'],
                    free_until_overcommit
                ))
                LOG.debug('({}/{})-max_over_subscription_ratio = {}'.format(
                    shard_name, caps['volume_backend_name'],
                    caps['max_over_subscription_ratio']
                ))
                LOG.debug('({}/{})-overcommit_ratio = {}'.format(
                    shard_name, caps['volume_backend_name'],
                    overcommit_ratio
                ))
