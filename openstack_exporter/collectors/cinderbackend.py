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

from openstack_exporter.utils import cinder as cinder_utils

LOG = logging.getLogger('openstack_exporter.exporter')

DEFAULT_VALID_SHARDING_BACKENDS = ['standard_hdd', 'vmware', 'vmware_fcd']
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
        LOG.debug(f"Reporting stats for {shard_name}/{backend}/{pool_name}")
        LOG.debug(f"Data {data}")
        LOG.debug(f"Capabilities {caps}")
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
        down_reason = caps.get('pool_down_reason', 'unknown')
        if caps.get('backend_state', 'down') == 'down':
            down_reason = 'backend_down'
        elif 'Datastore marked as draining' in down_reason:
            down_reason = 'draining'
        yield self.add_info_metric_gauge(
            'cinder_pool_down_reason',
            'Reason for pool state being down',
            {'pool_down_reason': down_reason},
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

        aggregate_id = data.get("aggregate_id")
        if aggregate_id:
            yield self.add_info_metric_gauge(
                'cinder_aggregate_id',
                'Cinder aggregate id',
                {'aggregate_id': aggregate_id},
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

    def _report_aggregated_stats(self, backend):
        pool_name = backend['name']
        LOG.debug(f"Reporting stats for {backend}/{pool_name}")
        LOG.debug(f"Aggregate Data {backend}")

        yield self.add_info_metric_gauge(
            'cinder_aggregate_id',
            'Cinder aggregate id',
            {'aggregate_id': backend['aggregate_id']},
            'aggregate', 'aggregate', pool_name
        )

        yield self.add_gauge_metric_gauge(
            'cinder_total_capacity_gib',
            'Cinder total capacity in GiB',
            backend['total_capacity_gb'],
            'aggregate', 'aggregate', pool_name
        )

        yield self.add_gauge_metric_gauge(
            'cinder_free_capacity_gib',
            'Cinder reported free capacity in GiB',
            backend['free_capacity_gb'],
            'aggregate', 'aggregate', pool_name
        )

        yield self.add_gauge_metric_gauge(
            'cinder_allocated_capacity_gib',
            'Cinder allocated capacity in GiB',
            backend['allocated_capacity_gb'],
            'aggregate', 'aggregate', pool_name
        )

        yield self.add_gauge_metric_gauge(
            'cinder_max_oversubscription_ratio',
            'Cinder max overcommit ratio',
            backend['max_over_subscription_ratio'],
            'aggregate', 'aggregate', pool_name
        )

        yield self.add_gauge_metric_gauge(
            'cinder_free_percent',
            'Cinder Percentage of available space is free.',
            backend['free_percent'],
            'aggregate', 'aggregate', pool_name
        )

        yield self.add_gauge_metric_gauge(
            'cinder_virtual_free_capacity_gib',
            'Cinder virtual free capacity in GiB',
            backend['virtual_free_capacity_gb'],
            'aggregate', 'aggregate', pool_name
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

        volume_types = cinder_utils.get_volume_types(self.client)
        # Now filter the pools through the volumes types to get the
        # pools associated with a volume type.
        pools = cinder_utils.filter_pools(
            self.client,
            cinder_utils.get_cinder_pools(self.client)
        )
        # build the aggregated pools list so we can report them as well.
        aggregated_pools = cinder_utils.aggregate_pools(pools)

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
        type_by_name = cinder_utils.get_volume_types_by_name(self.client)
        for volume_type_name in pools:
            for pool in pools[volume_type_name]:
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

                data = cinder_utils.parse_pool_data(pool, volume_type)
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

        for pool_name in aggregated_pools:
            yield from self._report_aggregated_stats(
                aggregated_pools[pool_name]
            )
