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
from keystoneauth1 import session
from keystoneauth1.identity import v3
from prometheus_client.core import GaugeMetricFamily
from manilaclient import client as manila  # Ensure manilaclient is installed
from openstack_exporter import BaseCollector

logging.basicConfig(level=logging.DEBUG)
LOG = logging.getLogger('openstack_exporter.exporter')

class ManilaBackendCollector(BaseCollector.BaseCollector):
    version = "1.0.0"

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
        api_version = '2.65'  # Adjust the API version as needed
        os_project_domain_name = self.config['project_domain_name']
        os_user_domain_name = self.config['user_domain_name']
        
        auth = v3.Password(auth_url=os_auth_url,
                           username=os_username,
                           password=os_password,
                           project_name=os_project_name,
                           project_domain_name=os_project_domain_name,
                           user_domain_name=os_user_domain_name)
        
        sess = session.Session(auth=auth)
        
        return manila.Client(
            '2.65',
            session=sess,
            region_name=self.region,
            service_type="sharev2",
            endpoint_type="publicURL"
        )

    def _renew_manila_client(self):
        """Renew the Manila client."""
        LOG.info("Renewing Manila client")
        self._init_manila_client()

    def describe(self):
        # Define metrics for description
        label_names = [
            'name', 'pool_name', 'share_backend_name', 
            'driver_version', 'hardware_state'
        ]
        
        yield GaugeMetricFamily(
            'manila_total_capacity_gb', 
            'Total capacity of the Manila backend in GiB', 
            labels=label_names
        )
        yield GaugeMetricFamily(
            'manila_free_capacity_gb', 
            'Free capacity of the Manila backend in GiB', 
            labels=label_names
        )
        yield GaugeMetricFamily(
            'manila_allocated_capacity_gb', 
            'Allocated capacity of the Manila backend in GiB', 
            labels=label_names
        )
        yield GaugeMetricFamily(
            'manila_reserved_percentage', 
            'Reserved percentage of the Manila backend', 
            labels=label_names
        )
        yield GaugeMetricFamily(
            'manila_reserved_snapshot_percentage', 
            'Reserved snapshot percentage of the Manila backend', 
            labels=label_names
        )
        yield GaugeMetricFamily(
            'manila_reserved_share_extend_percentage', 
            'Reserved share extend percentage of the Manila backend', 
            labels=label_names
        )
        yield GaugeMetricFamily(
            'manila_max_over_subscription_ratio', 
            'Max over-subscription ratio of the Manila backend', 
            labels=label_names
        )

    def _parse_pool_data(self, pool):
        # Parse pool data to extract metrics
        capabilities = pool.get('capabilities', {})
        return {
            "name": pool.get('name', 'N/A'),
            "pool_name": capabilities.get('pool_name', 'N/A'),
            "total_capacity_gb": capabilities.get('total_capacity_gb', 0),
            "free_capacity_gb": capabilities.get('free_capacity_gb', 0),
            "allocated_capacity_gb": capabilities.get('allocated_capacity_gb', 0),
            "reserved_percentage": capabilities.get('reserved_percentage', 0),
            "reserved_snapshot_percentage": capabilities.get(
                'reserved_snapshot_percentage', 0),
            "reserved_share_extend_percentage": capabilities.get(
                'reserved_share_extend_percentage', 0),
            "max_over_subscription_ratio": capabilities.get(
                'max_over_subscription_ratio', 1),
            "hardware_state": capabilities.get('hardware_state', 'N/A'),
            "share_backend_name": capabilities.get('share_backend_name', 'N/A'),
            "driver_version": str(capabilities.get('driver_version', 'N/A'))
        }

    def _create_gauge_metric(self, name, description, value, labels):
        metric = GaugeMetricFamily(
            name, description, 
            labels=[
                'name', 'pool_name', 'share_backend_name', 
                'driver_version', 'hardware_state'
            ]
        )
        metric.add_metric(labels, value)
        return metric
            
    def collect(self): 
        LOG.info("Collect Manila backend info. {}".format(
            self.config['auth_url']
        ))
        
        try:
            pools = self.manila_client.pools.list(detailed=True)

        except Exception as e:
            if "requires authentication" in str(e):
                LOG.info("Authentication required, renewing Manila client")
                self._renew_manila_client()
                pools = self.manila_client.pools.list(detailed=True)
            else:
                LOG.error(f"Error while collecting Manila backend metrics: {e}")
                return

        for pool in pools:
            data = self._parse_pool_data(pool._info)
            LOG.debug(f"Pool data: {data}")
            
            labels = [
                data['name'],
                data['pool_name'],
                data['share_backend_name'],
                data['driver_version'],
                data['hardware_state']
            ]

            yield self._create_gauge_metric(
                'manila_total_capacity_gb',
                'Total capacity of the pool in GiB',
                data['total_capacity_gb'],
                labels
            )
            yield self._create_gauge_metric(
                'manila_free_capacity_gb',
                'Free capacity of the pool in GiB',
                data['free_capacity_gb'],
                labels
            )
            yield self._create_gauge_metric(
                'manila_allocated_capacity_gb',
                'Allocated capacity of the pool in GiB',
                data['allocated_capacity_gb'],
                labels
            )
            yield self._create_gauge_metric(
                'manila_reserved_percentage',
                'Percentage of capacity reserved in the pool',
                data['reserved_percentage'],
                labels
            )
            yield self._create_gauge_metric(
                'manila_reserved_snapshot_percentage',
                'Percentage of capacity reserved for snapshots',
                data['reserved_snapshot_percentage'],
                labels
            )
            yield self._create_gauge_metric(
                'manila_reserved_share_extend_percentage',
                'Percentage of capacity reserved for share extension',
                data['reserved_share_extend_percentage'],
                labels
            )
            yield self._create_gauge_metric(
                'manila_max_over_subscription_ratio',
                'Maximum over-subscription ratio of the pool',
                data['max_over_subscription_ratio'],
                labels
            )
