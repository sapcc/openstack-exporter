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

"""
CachingCollector - A wrapper that adds background collection and caching
to any Prometheus collector.

This allows slow collectors (like those making OpenStack API calls) to
return cached metrics instantly while refreshing data in the background.
"""

import logging
import threading
import time

from prometheus_client.core import GaugeMetricFamily, CounterMetricFamily

LOG = logging.getLogger("openstack_exporter.exporter")


class CachingCollector:
    """
    Wraps a Prometheus collector to provide background collection and caching.

    The wrapped collector's collect() method is called periodically in a
    background thread, and the results are cached. When Prometheus scrapes,
    the cached metrics are returned instantly.

    Args:
        inner_collector: The collector to wrap (must have collect() and describe() methods)
        refresh_interval: Seconds between background collections (default: 120)
        serve_stale_on_error: If True, serve previous cached data on collection failure.
                              If False, clear cache and return empty on failure. (default: True)
    """

    def __init__(
        self, inner_collector, refresh_interval=120, serve_stale_on_error=True
    ):
        self.inner = inner_collector
        self.name = inner_collector.__class__.__name__
        self.refresh_interval = refresh_interval
        self.serve_stale_on_error = serve_stale_on_error

        # Cached metrics from the inner collector
        self._cached_metrics = []

        # Thread synchronization
        self._lock = threading.Lock()
        self._first_collect_done = threading.Event()
        self._stop_event = threading.Event()

        # Health tracking (protected by _lock)
        self._last_success = None
        self._last_duration = 0.0
        self._scrape_errors = 0

        # Start background thread immediately
        LOG.info(
            f"[{self.name}] Starting background collection thread "
            f"(refresh_interval={refresh_interval}s)"
        )
        self._thread = threading.Thread(
            target=self._background_loop,
            name=f"CachingCollector-{self.name}",
            daemon=True,
        )
        self._thread.start()

    def stop(self):
        """Stop the background collection thread gracefully."""
        LOG.info(f"Stopping background collection for {self.name}")
        self._stop_event.set()
        self._thread.join(timeout=5)

    def collect(self):
        """
        Called by Prometheus during scrape - returns cached metrics instantly.

        Blocks on first call until initial collection completes.
        """
        # Block until first collection attempt completes (with timeout)
        if not self._first_collect_done.wait(timeout=300):
            LOG.warning(f"Timeout waiting for first collection of {self.name}")

        # Always yield health metrics
        yield from self._health_metrics()

        # Yield cached data metrics
        with self._lock:
            yield from self._cached_metrics

    def describe(self):
        """Describe metrics for Prometheus."""
        # Describe health metrics
        yield GaugeMetricFamily(
            "collector_last_success_timestamp",
            "Unix timestamp of last successful collection",
            labels=["collector"],
        )
        yield GaugeMetricFamily(
            "collector_scrape_duration_seconds",
            "Duration of last successful collection in seconds",
            labels=["collector"],
        )
        yield GaugeMetricFamily(
            "collector_scrape_errors_total",
            "Total number of collection errors",
            labels=["collector"],
        )

        # Describe inner collector metrics
        yield from self.inner.describe()

    def _background_loop(self):
        """
        Background thread loop - runs forever, never dies from exceptions.

        Collects metrics from the inner collector periodically and caches them.
        """
        while not self._stop_event.is_set():
            try:
                LOG.info(
                    f"[{self.name}] Starting metrics collection from wrapped collector"
                )
                start = time.time()

                # Collect metrics from inner collector
                metrics = list(self.inner.collect())

                duration = time.time() - start
                LOG.info(
                    f"[{self.name}] Collection completed: {len(metrics)} metrics "
                    f"in {duration:.2f}s"
                )

                # Update cache (protected by lock)
                with self._lock:
                    self._cached_metrics = metrics
                    self._last_success = time.time()
                    self._last_duration = duration

            except Exception as e:
                # Log but NEVER re-raise - thread must survive
                LOG.exception(f"Background collection failed for {self.name}: {e}")

                with self._lock:
                    self._scrape_errors += 1

                    # Optionally clear cache on error
                    if not self.serve_stale_on_error:
                        self._cached_metrics = []
                        LOG.warning(
                            f"Cleared cached metrics for {self.name} due to error"
                        )

            finally:
                # Always signal first collection attempt complete
                self._first_collect_done.set()

            # Wait for next interval (or until stopped)
            LOG.info(f"[{self.name}] Next collection in {self.refresh_interval}s")
            self._stop_event.wait(timeout=self.refresh_interval)

        LOG.info(f"Background collection thread for {self.name} stopped")

    def _health_metrics(self):
        """Generate health metrics about collection status."""
        with self._lock:
            last_success = self._last_success
            last_duration = self._last_duration
            scrape_errors = self._scrape_errors

        # collector_last_success_timestamp
        last_success_metric = GaugeMetricFamily(
            "collector_last_success_timestamp",
            "Unix timestamp of last successful collection",
            labels=["collector"],
        )
        if last_success is not None:
            last_success_metric.add_metric([self.name], last_success)
        else:
            last_success_metric.add_metric([self.name], 0)
        yield last_success_metric

        # collector_scrape_duration_seconds
        duration_metric = GaugeMetricFamily(
            "collector_scrape_duration_seconds",
            "Duration of last successful collection in seconds",
            labels=["collector"],
        )
        duration_metric.add_metric([self.name], last_duration)
        yield duration_metric

        # collector_scrape_errors_total
        errors_metric = GaugeMetricFamily(
            "collector_scrape_errors_total",
            "Total number of collection errors",
            labels=["collector"],
        )
        errors_metric.add_metric([self.name], scrape_errors)
        yield errors_metric
