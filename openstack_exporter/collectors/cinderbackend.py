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

from cachetools import cached, TTLCache
from cinderclient import client as cinder
from openstack_exporter import BaseCollector

LOG = logging.getLogger('openstack_exporter.exporter')

DEFAULT_VALID_SHARDING_BACKENDS = ['standard_hdd', 'vmware']
DEFAULT_VALID_NO_SHARD_BACKENDS = []
ALLOW_UNEXPECTED_BACKENDS_DEFAULT = False


class CinderBackendCollector(BaseCollector.BaseCollector):
    version = "1.0.3"

    def __init__(self, openstack_config, collector_config):
        super().__init__(openstack_config, collector_config)
        # We have to create a cinder client here
        # because the openstacksdk doesn't currently
        # Support the quota functions.
        self.cinder_client = self._cinder_client()
        self.labels = ['backend', 'pool', 'shard']
        LOG.debug(f"Openstack Exporter CinderBackend Version {self.version}")
        LOG.debug(f"Collector configuration {self.collector_config}")
        # Make sure there is a default setting for valid_backends
        cinder_config = self.collector_config['cinderbackend']
        if 'expected_sharding_backends' not in cinder_config:
            self.expected_sharding_backends = DEFAULT_VALID_SHARDING_BACKENDS
        else:
            backends = cinder_config['expected_sharding_backends']
            self.expected_sharding_backends = [x.strip() for x in backends.split(',')]
        if 'expected_no_sharding_backends' not in cinder_config:
            self.expected_no_sharding_backends = DEFAULT_VALID_NO_SHARD_BACKENDS
        else:
            backends = cinder_config['expected_no_sharding_backends']
            self.expected_no_sharding_backends = [x.strip() for x in backends.split(',')]

        self.allow_unexpected_backends = cinder_config.get(
            'allow_unexpected_backends', ALLOW_UNEXPECTED_BACKENDS_DEFAULT)
        LOG.debug("Allowed Expected Sharding Backends "
                  f"{self.expected_sharding_backends}")
        LOG.debug("Allowed Expected Non Sharding Backends "
                  f"{self.expected_no_sharding_backends}")
        LOG.debug(f"Allow Unexpected Backends? {self.allow_unexpected_backends}")
        LOG.debug(f"Shards discovered: {self.shards()}")

    def _cinder_client(self):
        """openstacksdk doesn't have quota functions yet."""
        os_auth_url = self.config['auth_url']
        os_username = self.config['username']
        os_password = self.config['password']
        os_project_name = self.config['project_name']
        api_version = 3.70

        client_args = dict(
            region_name=self.region,
            service_type="volumev3",
            service_name='',
            os_endpoint='',
            endpoint_type="publicURL",
            insecure=False,
            cacert=None,
            auth_plugin=None,
            http_log_debug=True,
            session=self.client.session,
        )

        return cinder.Client(
            api_version,
            os_username,
            os_password,
            os_project_name,
            os_auth_url,
            **client_args,
        )

    # Cache the shards for 30 minutes since it's painful to fetch
    @cached(cache=TTLCache(maxsize=50, ttl=1800))
    def shards(self):
        shard_names = []
        LOG.debug("Fetching shard names")
        for agg in self.client.compute.aggregates():
            if agg.name.startswith('vc-'):
                shard_names.append(agg.name)
        return shard_names

    def describe(self):
        yield GaugeMetricFamily('cinder_per_volume_gigabytes',
                                'Cinder max volume size')
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
        yield GaugeMetricFamily('cinder_percent_free',
                                'Cinder Percentage of available space is free.')

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
        shard_name = caps.get('vcenter-shard')

        data = {"backend": caps["volume_backend_name"],
                "pool": pool['name'].split('#')[1],
                "shard": shard_name}
        can_overcommit = False

        # Only allow overcommit if the volume type that matches
        # The backend is thin provisioned.
        # A missing key of provisioning:type means thin provisioning.
        if volume_type and volume_type['extra_specs'].get('provisioning:type') != 'thick':
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

    def _debug_gauge(self, gauge, name, value, shard, backend, pool):
        LOG.debug(f"({shard}/{backend}/{pool})-{name} = {value}")
        return gauge

    def add_info_metric_gauge(self, name, description, value,
                              shard, backend, pool):
        gauge = InfoMetricFamily(name, description, labels=self.labels)
        gauge.add_metric([backend, pool, shard], value=value)
        return self._debug_gauge(gauge, name, value, shard, backend, pool)

    def add_gauge_metric_gauge(self, name, description, value,
                               shard, backend, pool):
        gauge = GaugeMetricFamily(name, description, labels=self.labels)
        gauge.add_metric([backend, pool, shard], value=value)
        return self._debug_gauge(gauge, name, value, shard, backend, pool)

    def _report_stats(self, shard_name, backend, data, caps, quota_obj):
        pool_name = data['pool']
        yield self.add_gauge_metric_gauge(
            'cinder_per_volume_gigabytes',
            'Cinder max volume size in GiB',
            quota_obj.per_volume_gigabytes,
            shard_name, backend, pool_name
        )
        yield self.add_info_metric_gauge(
            'cinder_backend_state',
            'State of cinder backend up/down',
            {'backend_state': caps.get('backend_state', 'down')},
            shard_name, backend, pool_name
        )
        yield self.add_info_metric_gauge(
            'cinder_pool_state',
            'State of cinder pool up/down',
            {'pool_state': caps.get('pool_state', 'down')},
            shard_name, backend, pool_name
        )

        # The volume backend can do overcommit if and only if
        # the backdnd and volume type are set to thin provisioning.
        can_overcommit = data["can_overcommit"]

        provisioning_type = ('thin' if can_overcommit else 'thick')
        yield self.add_info_metric_gauge(
            'cinder_provisioning_type',
            'Cinder provisioning type',
            {'provisioning_type': provisioning_type},
            shard_name, backend, pool_name
        )

        yield self.add_gauge_metric_gauge(
            'cinder_total_capacity_gib',
            'Cinder total capacity in GiB',
            data['total_capacity_gb'],
            shard_name, backend, pool_name
        )

        yield self.add_gauge_metric_gauge(
            'cinder_available_capacity_gib',
            'Cinder available capacity in GiB',
            data['available_capacity_gb'],
            shard_name, backend, pool_name
        )

        yield self.add_gauge_metric_gauge(
            'cinder_free_capacity_gib',
            'Cinder reported free capacity in GiB',
            data['free_capacity_gb'],
            shard_name, backend, pool_name
        )

        yield self.add_gauge_metric_gauge(
            'cinder_virtual_free_capacity_gib',
            'Cinder virtual free capacity in GiB',
            data['virtual_free_capacity_gb'],
            shard_name, backend, pool_name
        )

        yield self.add_gauge_metric_gauge(
            'cinder_allocated_capacity_gib',
            'Cinder allocated capacity in GiB',
            data['allocated_capacity_gb'],
            shard_name, backend, pool_name
        )

        if can_overcommit:
            yield self.add_gauge_metric_gauge(
                'cinder_max_oversubscription_ratio',
                'Cinder max overcommit ratio',
                data['max_over_subscription_ratio'],
                shard_name, backend, pool_name
            )

            yield self.add_gauge_metric_gauge(
                'cinder_overcommit_ratio',
                'Cinder Overcommit ratio',
                data['overcommit_ratio'],
                shard_name, backend, pool_name
            )
            yield self.add_gauge_metric_gauge(
                'cinder_reserved_percentage',
                'Cinder Reserved Space Percentage',
                data['reserved_percentage'],
                shard_name, backend, pool_name
            )

            yield self.add_gauge_metric_gauge(
                'cinder_percent_free',
                'Cinder Percentage of available space is free.',
                data['percent_left'],
                shard_name, backend, pool_name
            )

            netapp_fqdn = caps.get('custom_attributes', {}).get(
                'netapp_fqdn', 'None')
            yield self.add_info_metric_gauge(
                'cinder_pool_netapp_fqdn',
                'Cinder pool custom attribute netapp_fqdn',
                {'netapp_fqdn': netapp_fqdn},
                shard_name, backend, pool_name
            )

    def collect(self):
        """This is the collector for cinder backends.

        This calls the cinder scheduler api to get all the pool stats
        that the scheduler sees.  If a backend is down and the stats aren't
        being collected by the driver for that backend, then the scheduler will
        not have any stats.  The collector has an expected list of backends
        that it wants to see coming from the scheduler API.  The execpted
        backends are configurable in the config file.  See the sample config

        For each expected backend the collector will report stats.
        If the backend isn't seen in the stats from the scheduler API,
        then the collector will report 0 capacity.

        """
        LOG.info("Collect cinder backend info. {}".format(
            self.config['auth_url']
        ))
        project_id = self.client.volume.get_project_id()
        quota_obj = self.cinder_client.quotas.defaults(project_id)

        v_types = list(self.client.volume.types())
        # Ignore volume types that aren't tied to a backend.
        volume_types = (
            {vt['extra_specs']['volume_backend_name']:
             vt for vt in v_types if 'volume_backend_name' in vt['extra_specs']})

        pools = self.client.volume.backend_pools()

        # Keep a count of each backend in each shard for each pool.
        # If we don't see any pools in a shard/backend then it's down and
        # we will report that shard/backend as reporting 0 capacity.
        default_shard_backends = dict([(key, 0) for key in self.expected_sharding_backends])
        default_no_shard_backends = dict([(key, 0) for key in self.expected_no_sharding_backends])
        # 'None' key means the shard name 'None' for backends
        # That aren't affiliated with sharding.
        no_shard = 'None'
        seen_backends = {no_shard: default_no_shard_backends.copy()}
        # populate the seen_backends with expected shards
        for shard_name in self.shards():
            seen_backends[shard_name] = default_shard_backends.copy()
        LOG.debug(f"Expecting backends {self.expected_sharding_backends}")
        LOG.debug(f"Initial stats {seen_backends}")
        for pool in pools:
            caps = pool['capabilities']
            backend = caps['volume_backend_name']
            shard_name = no_shard
            if 'vcenter-shard' in caps:
                shard_name = caps['vcenter-shard']
            volume_type = None
            if backend in volume_types:
                volume_type = volume_types[backend]
            else:
                LOG.debug(f"Backend {backend} has no associated volume type")

            # initialize the accounting for the shard
            if shard_name not in seen_backends:
                seen_backends[shard_name] = default_shard_backends.copy()

            data = self._parse_pool_data(pool, volume_type)
            pool_name = data['pool']

            if shard_name != no_shard:
                LOG.debug(f"Got stats for {self.region} "
                          f"{shard_name}/{backend}/{pool_name}")
            else:
                LOG.debug(f"Got stats for {self.region} {backend}/{pool_name}")

            yield from self._report_stats(
                shard_name, backend, data, caps, quota_obj)
            if backend in seen_backends[shard_name]:
                seen_backends[shard_name][backend] += 1
            elif self.allow_unexpected_backends:
                LOG.debug(f"Adding unexpected backend {backend} "
                          f"to shard {shard_name}")
                seen_backends[shard_name][backend] = 1
            else:
                LOG.warning(f"Backend {backend} is not in expected "
                            f"backends {self.expected_sharding_backends}")

        LOG.debug(f"seen backends {seen_backends}")
        for shard in seen_backends:
            for backend in seen_backends[shard]:
                if seen_backends[shard][backend] == 0:
                    LOG.debug(f"{shard} / {backend} is down")
                    yield self.add_gauge_metric_gauge(
                        'cinder_free_capacity_gib',
                        'Cinder reported free capacity in GiB',
                        0, shard, backend, "None"
                    )
