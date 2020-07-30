from prometheus_client.core import GaugeMetricFamily
from BaseCollector import BaseCollector


class CinderCollector(BaseCollector):
    def __init__(self):
        pass

    def describe(self):
        # all your metrics go in here, without a label
        yield GaugeMetricFamily('cinder_foo_stat', 'Cinder status of foo')

    def collect(self):
        # logic goes in here
        pass

