#!/usr/bin/python3
import time
from optparse import OptionParser
from prometheus_client import start_http_server
from prometheus_client.core import REGISTRY
from collectors.CinderCollector import CinderCollector
import os

def parse_params():
    parser = OptionParser()
    parser.add_option("-o", "--port", help="specify exporter serving port",
                      action="store", dest="port")
    parser.add_option("-d", "--debug", help="enable debug", action="store_true", dest="debug", default=False)
    parser.add_option("-c", "--config", help="path to rest config", action="store", dest="config")
    parser.add_option("-u", "--user", help="user used with master password", action="store", dest="user")
    parser.add_option("-p", "--password", help="specify password to log in", action="store", dest="password")

    (options, args) = parser.parse_args()
    if options.debug:
        print('DEBUG enabled')
        os.environ['DEBUG'] = "1"
    else:
        os.environ['DEBUG'] = "0"
    return options


def run_prometheus_server(port):
    start_http_server(int(port))
    REGISTRY.register(CinderCollector())
    while True:
        time.sleep(1)

if __name__ == '__main__':
    options = parse_params()
    run_prometheus_server(options.port)
