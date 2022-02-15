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

import math
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
        yield GaugeMetricFamily('cinder_reserved_percentage',
                                'Cinder Reserved Space Percentage')
        yield GaugeMetricFamily('cinder_free_until_overcommit_gib',
                                'Cinder free space until Overcommit reached')
        yield GaugeMetricFamily('cinder_free_until_reserved_achieved_gib',
                                'Cinder free space until Reserved Percentage Met')
        yield GaugeMetricFamily('cinder_reserved_percent_available',
                                "Cinder percentage available until reserved is met")

    def _parse_pool_data(self, pool, volume_type):
        """Construct the data from the pool information from the scheduler."""
        caps = pool['capabilities']
        data = {"backend": caps["volume_backend_name"],
                "pool": pool['name'].split('#')[1],
                "shard": caps["vcenter-shard"]}
        can_overcommit = False
        # Only allow overcommit if the volume type that matches
        # The backend is thin provisioned.
        # A missing key of provisioning:type means thin provisioning.
        if volume_type['extra_specs'].get('provisioning:type') != 'thick':
            can_overcommit = True

        data["can_overcommit"] = can_overcommit
        data['total_capacity_gb'] = caps.get('total_capacity_gb', 0)

        if data['total_capacity_gb'] > 0:
            overcommit_ratio = caps['allocated_capacity_gb'] / data['total_capacity_gb']
        else:
            overcommit_ratio = 0
        data['overcommit_ratio'] = overcommit_ratio
        data['provisioned_capacity_gb'] = caps.get('provisioned_capacity_gb', 0)

        free_until_overcommit = 0
        if (data['total_capacity_gb'] > 0 and 'max_over_subscription_ratio'
                in caps):
            free_until_overcommit = (
                data['total_capacity_gb'] * float(caps['max_over_subscription_ratio'])
                - caps['allocated_capacity_gb'])
        data['free_until_overcommit'] = free_until_overcommit
        data['free_capacity_gb'] = caps.get('free_capacity_gb', 0)

        if data['total_capacity_gb'] > 0:
            percent_left = (data['free_capacity_gb'] / data['total_capacity_gb']) * 100
        else:
            percent_left = 0
        data['percent_left'] = percent_left

        data['allocated_capacity_gb'] = caps.get('allocated_capacity', 0)
        data['reserved_percentage'] = caps.get('reserved_percentage', 0)
        if data['reserved_percentage'] > 0:
            reserved_percentage = float(data['reserved_percentage']) / 100
            # Calculate available free based off of reserved_percentage
            available_capacity_gb = data['free_capacity_gb'] - math.floor(
                data['total_capacity_gb'] * reserved_percentage)
            if available_capacity_gb < 0:
                available_capacity_gb = 0
            data['available_capacity_gb'] = available_capacity_gb
            if data['free_capacity_gb'] > 0:
                available_left_percent = (available_capacity_gb / data['free_capacity_gb']) * 100
            else:
                available_left_percent = 0
            data['available_until_reserved'] = available_capacity_gb
            data['available_until_reserved_percent'] = available_left_percent
        else:
            data['available_capacity_gb'] = data['free_capacity_gb']
            data['available_until_reserved'] = 0
            data['available_until_reserved_percent'] = 0

        if can_overcommit:
            data['current_overcommit'] = overcommit_ratio
            data['overcommit_ratio_percent'] = (overcommit_ratio / int(
                caps['max_over_subscription_ratio'])) * 100
            if 'max_over_subscription_ratio' in caps:
                data['max_overcommit'] = caps['max_over_subscription_ratio']
            if free_until_overcommit is not None:
                data['capacity_until_overcommit'] = free_until_overcommit
            data['provisioning_type'] = 'thin'
        else:
            data['provisioning_type'] = 'thick'

        data['driver_version'] = caps['driver_version']
        return data

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

            volume_type = volume_types[backend]
            data = self._parse_pool_data(pool, volume_type)
            pool_name = data['pool']

            # The volume backend can do overcommit if and only if
            # the backdnd and volume type are set to thin provisioning.
            can_overcommit = data["can_overcommit"]

            g = InfoMetricFamily('cinder_provisioning_type',
                                 'Cinder provisioning type',
                                 labels=['backend', 'pool', 'shard'])
            provisioning_type = ('thin' if can_overcommit else 'thick')
            g.add_metric([backend, pool_name, shard_name],
                         value={'provisioning_type': provisioning_type})
            yield g

            total_capacity_gb = data.get('total_capacity_gb')
            g = GaugeMetricFamily('cinder_total_capacity_gib',
                                  'Cinder total capacity in GiB',
                                  labels=['backend', 'pool', 'shard'])
            g.add_metric([backend, pool_name, shard_name],
                         value=total_capacity_gb)
            yield g

            free_cap = data['free_capacity_gb']
            g = GaugeMetricFamily('cinder_free_capacity_gib',
                                  'Cinder free capacity in GiB',
                                  labels=['backend', 'pool', 'shard'])
            g.add_metric([backend, pool_name, shard_name], value=free_cap)
            yield g

            g = GaugeMetricFamily('cinder_allocated_capacity_gib',
                                  'Cinder allocated capacity in GiB',
                                  labels=['backend', 'pool', 'shard'])
            g.add_metric([backend, pool_name, shard_name],
                         value=data['allocated_capacity_gb'])
            yield g

            if can_overcommit:
                g = GaugeMetricFamily('cinder_max_oversubscription_ratio',
                                      'Cinder max overcommit ratio',
                                      labels=['backend', 'pool', 'shard'])
                g.add_metric([backend, pool_name, shard_name],
                             value=data['max_over_subscription_ratio'])
                yield g

                g = GaugeMetricFamily('cinder_overcommit_ratio',
                                      'Cinder Overcommit ratio',
                                      labels=['backend', 'pool', 'shard'])
                g.add_metric([backend, pool_name, shard_name],
                             value=data['overcommit_ratio'])
                yield g

                g = GaugeMetricFamily('cinder_free_until_overcommit_gib',
                                      'Cinder free space until Overcommit in GiB',
                                      labels=['backend', 'pool', 'shard'])
                g.add_metric([backend, pool_name, shard_name],
                             value=data['free_until_overcommit'])
                yield g
            else:
                g = GaugeMetricFamily('cinder_reserved_precentage',
                                      'Cinder Reserved Space Percentage',
                                      labels=['backend', 'pool', 'shard'])
                g.add_metric([backend, pool_name, shard_name],
                             value=data['reserved_percentage'])

                yield g

                g = GaugeMetricFamily('cinder_free_until_reserved_achieved_gib',
                                      'Cinder free space until Reserved Percentage Met',
                                      labels=['backend', 'pool', 'shard'])
                g.add_metric([backend, pool_name, shard_name],
                             value=data['available_capacity_gb'])
                yield g

                g = GaugeMetricFamily('cinder_reserved_percent_available',
                                      'Cinder percentage available until reserved is met',
                                      labels=['backend', 'pool', 'shard'])
                g.add_metric([backend, pool_name, shard_name],
                             value=data['available_until_reserved_percent'])
                yield g




            LOG.debug('({}/{}/{})-provisioning_type = {}'.format(
                shard_name, data['backend'], data['pool'],
                provisioning_type
            ))
            LOG.debug('({}/{}/{})-total_capacity_gb = {}'.format(
                shard_name, data['backend'], data['pool'],
                data['total_capacity_gb']
            ))
            LOG.debug('({}/{}/{})-free_capacity_gb = {}'.format(
                shard_name, data['backend'], data['pool'],
                data['free_capacity_gb']
            ))
            LOG.debug('({}/{}/{})-allocated_capacity_gb = {}'.format(
                shard_name, caps['volume_backend_name'], data['pool'],
                data['allocated_capacity_gb']
            ))

            if can_overcommit:
                LOG.debug('({}/{}/{})-free_until_overcommit = {}'.format(
                    shard_name, data['backend'], data['pool'],
                    data['free_until_overcommit']
                ))
                LOG.debug('({}/{}/{})-max_over_subscription_ratio = {}'.format(
                    shard_name, caps['volume_backend_name'], pool['pool'],
                    caps['max_over_subscription_ratio']
                ))
                LOG.debug('({}/{}/{})-overcommit_ratio = {}'.format(
                    shard_name, caps['volume_backend_name'], pool['pool'],
                    data['overcommit_ratio']
                ))
            else:
                LOG.debug('({}/{}/{})-reserved_percentage = {}'.format(
                    shard_name, caps['volume_backend_name'], data['pool'],
                    data['reserved_percentage']
                ))
                LOG.debug('({}/{}/{})-free_until_reserved_met = {}'.format(
                    shard_name, caps['volume_backend_name'], data['pool'],
                    data['available_capacity_gb']
                ))
