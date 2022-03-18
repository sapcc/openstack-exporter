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
import math
from prometheus_client.core import GaugeMetricFamily, InfoMetricFamily

from openstack_exporter import BaseCollector

LOG = logging.getLogger('openstack_exporter.exporter')


class CinderBackendCollector(BaseCollector.BaseCollector):

    def describe(self):
        yield InfoMetricFamily('cinder_provisioning_type',
                               'Cinder provisioning type')
        yield GaugeMetricFamily('cinder_total_capacity_gib',
                                'Cinder total capacity in GiB')
        yield GaugeMetricFamily('cinder_available_capacity_gib',
                                'Cinder available capacity in GiB')
        yield GaugeMetricFamily('cinder_free_capacity_gib',
                                'Cinder reported free capacity in GiB')
        yield GaugeMetricFamily('cinder_virtual_free_capacity_gib',
                                'Cinder virtual free capacity in GiB')
        yield GaugeMetricFamily('cinder_allocated_capacity_gib',
                                'Cinder allocated capacity in GiB')
        yield GaugeMetricFamily('cinder_max_oversubscription_ratio',
                                'Cinder max overcommit ratio')
        yield GaugeMetricFamily('cinder_overcommit_ratio',
                                'Cinder Overcommit ratio')
        yield GaugeMetricFamily('cinder_reserved_percentage',
                                'Cinder Reserved Space Percentage')

    def calculate_capacity_factors(self,
                                   total_capacity: float,
                                   free_capacity: float,
                                   provisioned_capacity: float,
                                   thin_provisioning_support: bool,
                                   max_over_subscription_ratio: float,
                                   reserved_percentage: float,
                                   thin: bool) -> dict:
        """Create the various capacity factors of the a particular backend.

        Based off of definition of terms
        cinder-specs/specs/queens/provisioning-improvements.html

        total_capacity - The reported total capacity in the backend.
        free_capacity - The free space/capacity as reported by the backend.
        reserved_capacity - The amount of space reserved from the total_capacity
        as reported by the backend.
        total_reserved_available_capacity - The total capacity minus reserved
        capacity

        max_over_subscription_ratio - as reported by the backend
        total_available_capacity - The total capacity available to cinder
        calculated
        thick: total_reserved_available_capacity
        OR
        thin: total_reserved_available_capacity and max_over_subscription_ratio

        provisioned_capacity - as reported by backend or volume manager
        (allocated_capacity_gb)

        calculated_free_capacity - total_available_capacity - provisioned_capacity
        virtual_free_capacity - The calculated free capacity available to cinder
        to allocate new storage.
        For thin: calculated_free_capacity
        For thick: the reported free_capacity can be less than the calculated
        Capacity, so we use free_capacity - reserved_capacity.

        free_percent - the percentage of the virtual_free and
        total_available_capacity is left over
        provisioned_ratio - The ratio of provisioned storage to
        total_available_capacity
        """

        total = float(total_capacity)
        reserved = float(reserved_percentage) / 100
        reserved_capacity = math.floor(total * reserved)
        total_reserved_available = total - reserved_capacity

        if thin and thin_provisioning_support:
            total_available_capacity = (
                total_reserved_available * max_over_subscription_ratio
            )
            calculated_free = total_available_capacity - provisioned_capacity
            virtual_free = calculated_free
            provisioned_type = 'thin'
        else:
            # Calculate how much free space is left after taking into
            # account the reserved space.
            total_available_capacity = total_reserved_available
            calculated_free = total_available_capacity - provisioned_capacity
            virtual_free = calculated_free
            if free_capacity < calculated_free:
                virtual_free = free_capacity
            provisioned_type = 'thick'

        if total_available_capacity:
            provisioned_ratio = provisioned_capacity / total_available_capacity
            free_percent = (virtual_free / total_available_capacity) * 100
        else:
            provisioned_ratio = 0
            free_percent = 0

        return {
            "total_capacity": total,
            "free_capacity": free_capacity,
            "reserved_capacity": reserved_capacity,
            "total_reserved_available_capacity": int(total_reserved_available),
            "max_over_subscription_ratio": (
                max_over_subscription_ratio if provisioned_type == 'thin' else None
            ),
            "total_available_capacity": int(total_available_capacity),
            "provisioned_capacity": provisioned_capacity,
            "calculated_free_capacity": int(calculated_free),
            "virtual_free_capacity": int(virtual_free),
            "free_percent": free_percent,
            "provisioned_ratio": provisioned_ratio,
            "provisioned_type": provisioned_type
        }

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

        total_capacity_gb = caps.get('total_capacity_gb', 0)
        allocated_capacity_gb = caps.get('allocated_capacity_gb', 0)
        reserved_percentage = caps.get('reserved_percentage', 0)
        max_over_subscription_ratio = float(
            caps.get('max_over_subscription_ratio', 1)
        )
        free_capacity_gb = caps.get('free_capacity_gb', 0)

        capacity_factors = self.calculate_capacity_factors(
            total_capacity_gb,
            free_capacity_gb,
            allocated_capacity_gb,
            caps.get('thin_provisioning_support', False),
            max_over_subscription_ratio,
            reserved_percentage,
            can_overcommit,
        )
        available_capacity_gb = capacity_factors["total_available_capacity"]
        virtual_free_gb = capacity_factors["virtual_free_capacity"]
        percent_left = capacity_factors["free_percent"]
        overcommit_ratio = capacity_factors["provisioned_ratio"]

        data["can_overcommit"] = can_overcommit
        data['total_capacity_gb'] = total_capacity_gb
        data['max_over_subscription_ratio'] = max_over_subscription_ratio
        data['provisioned_capacity_gb'] = caps.get('provisioned_capacity_gb', 0)
        data['overcommit_ratio'] = overcommit_ratio

        data['available_capacity_gb'] = available_capacity_gb
        data['allocated_capacity_gb'] = allocated_capacity_gb
        # What the backend is reporting
        data['free_capacity_gb'] = free_capacity_gb
        # What cinder can use
        data['virtual_free_capacity_gb'] = virtual_free_gb
        data['percent_left'] = percent_left
        data['reserved_percentage'] = reserved_percentage

        if can_overcommit:
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

            available_capacity_gb = data.get('available_capacity_gb')
            g = GaugeMetricFamily('cinder_available_capacity_gib',
                                  'Cinder available capacity in GiB',
                                  labels=['backend', 'pool', 'shard'])
            g.add_metric([backend, pool_name, shard_name],
                         value=available_capacity_gb)
            yield g

            free_cap = data['free_capacity_gb']
            g = GaugeMetricFamily('cinder_free_capacity_gib',
                                  'Cinder reported free capacity in GiB',
                                  labels=['backend', 'pool', 'shard'])
            g.add_metric([backend, pool_name, shard_name], value=free_cap)
            yield g

            virtual_free_cap = data['virtual_free_capacity_gb']
            g = GaugeMetricFamily('cinder_virtual_free_capacity_gib',
                                  'Cinder virtual free capacity in GiB',
                                  labels=['backend', 'pool', 'shard'])
            g.add_metric([backend, pool_name, shard_name],
                         value=virtual_free_cap)
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

            g = GaugeMetricFamily('cinder_reserved_precentage',
                                  'Cinder Reserved Space Percentage',
                                  labels=['backend', 'pool', 'shard'])
            g.add_metric([backend, pool_name, shard_name],
                         value=data['reserved_percentage'])

            yield g

            LOG.debug('({}/{}/{})-provisioning_type = {}'.format(
                shard_name, data['backend'], data['pool'],
                provisioning_type
            ))
            LOG.debug('({}/{}/{})-total_capacity_gb = {}'.format(
                shard_name, data['backend'], data['pool'],
                data['total_capacity_gb']
            ))
            LOG.debug('({}/{}/{})-available_capacity_gb = {}'.format(
                shard_name, data['backend'], data['pool'],
                data['available_capacity_gb']
            ))
            LOG.debug('({}/{}/{})-free_capacity_gb = {}'.format(
                shard_name, data['backend'], data['pool'],
                data['free_capacity_gb']
            ))
            LOG.debug('({}/{}/{})-virtual_free_capacity_gb = {}'.format(
                shard_name, data['backend'], data['pool'],
                data['virtual_free_capacity_gb']
            ))
            LOG.debug('({}/{}/{})-allocated_capacity_gb = {}'.format(
                shard_name, caps['volume_backend_name'], data['pool'],
                data['allocated_capacity_gb']
            ))

            if can_overcommit:
                LOG.debug('({}/{}/{})-max_over_subscription_ratio = {}'.format(
                    shard_name, caps['volume_backend_name'], data['pool'],
                    caps['max_over_subscription_ratio']
                ))
                LOG.debug('({}/{}/{})-overcommit_ratio = {}'.format(
                    shard_name, caps['volume_backend_name'], data['pool'],
                    data['overcommit_ratio']
                ))

            LOG.debug('({}/{}/{})-reserved_percentage = {}'.format(
                shard_name, caps['volume_backend_name'], data['pool'],
                data['reserved_percentage']
            ))
