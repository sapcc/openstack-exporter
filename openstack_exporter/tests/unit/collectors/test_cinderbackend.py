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

"""Tests for the Cinder backend collector."""

import unittest

from openstack_exporter.collectors.cinderbackend import CinderBackendCollector


class FakeQuota:
    """Minimal quota object required by the collector."""

    per_volume_gigabytes = 100


class CinderBackendCollectorTest(unittest.TestCase):
    """Test Cinder backend metric reporting."""

    def setUp(self):
        """Create a collector without connecting to OpenStack."""
        self.collector = CinderBackendCollector.__new__(CinderBackendCollector)
        self.collector.labels = [
            'backend', 'pool', 'shard', 'availability_zone'
        ]
        self.collector.aggregate_labels = ['backend', 'pool', 'shard']

    def _report_pool(self, aggregate_id_marker=None, include_aggregate_id=False):
        data = {
            'pool': 'pool-a',
            'can_overcommit': False,
            'total_capacity_gb': 100,
            'available_capacity_gb': 90,
            'free_capacity_gb': 80,
            'virtual_free_capacity_gb': 80,
            'allocated_capacity_gb': 20,
            'max_over_subscription_ratio': 1.0,
            'overcommit_ratio': 0.2,
            'reserved_percentage': 0,
        }
        caps = {
            'backend_state': 'up',
            'pool_state': 'up',
            'volume_backend_name': 'backend-a',
            'driver_version': '1',
            'custom_attributes': {},
        }
        if include_aggregate_id:
            data['aggregate_id'] = aggregate_id_marker
        return list(self.collector._report_stats(
            'shard-a', 'backend-a', data, caps, FakeQuota()))

    @staticmethod
    def _metric(metrics, name):
        return next(metric for metric in metrics if metric.name == name)

    def test_describe_registers_aggregate_id_missing_metric(self):
        """Register the aggregate ID missing metric in describe output."""
        names = [metric.name for metric in self.collector.describe()]

        self.assertIn('cinder_pool_aggregate_id_missing', names)

    def test_real_aggregate_id_is_not_missing(self):
        """Report zero when a pool has a real aggregate ID."""
        metrics = self._report_pool('aggregate-a', include_aggregate_id=True)

        aggregate_id = self._metric(metrics, 'cinder_aggregate_id')
        missing = self._metric(metrics, 'cinder_pool_aggregate_id_missing')
        self.assertEqual('aggregate-a', aggregate_id.samples[0].labels['aggregate_id'])
        self.assertEqual(0, missing.samples[0].value)
        self.assertEqual({
            'backend': 'backend-a',
            'pool': 'pool-a',
            'shard': 'shard-a',
            'availability_zone': 'unknown',
        }, missing.samples[0].labels)

    def test_missing_aggregate_id_is_reported(self):
        """Report one for null and empty aggregate IDs."""
        for marker in (None, ''):
            with self.subTest(marker=marker):
                metrics = self._report_pool(marker, include_aggregate_id=True)
                names = [metric.name for metric in metrics]

                self.assertNotIn('cinder_aggregate_id', names)
                missing = self._metric(metrics, 'cinder_pool_aggregate_id_missing')
                self.assertEqual(1, missing.samples[0].value)

    def test_absent_aggregate_id_is_reported(self):
        """Report one when aggregate ID is absent."""
        metrics = self._report_pool()

        names = [metric.name for metric in metrics]
        self.assertNotIn('cinder_aggregate_id', names)
        missing = self._metric(metrics, 'cinder_pool_aggregate_id_missing')
        self.assertEqual(1, missing.samples[0].value)
