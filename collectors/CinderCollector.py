from prometheus_client.core import GaugeMetricFamily
from BaseCollector import BaseCollector
from modules.Connection import Connection


class CinderCollector(BaseCollector):
    def __init__(self):
        pass

    def describe(self):
        # all your metrics go in here, without a label
        # yield GaugeMetricFamily('vcsa_service_status', 'Health Status of vCSA Services')

    def collect(self):
        # logic goes in here
        pass

