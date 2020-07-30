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

import os
import time

from collectors.CinderCollector import CinderCollector
from optparse import OptionParser
from prometheus_client.core import REGISTRY
from prometheus_client import start_http_server


def parse_params():
    parser = OptionParser()
    parser.add_option("-o", "--port",
                      action="store", dest="port",
                      help="specify exporter serving port")
    parser.add_option("-d", "--debug",
                      action="store_true", dest="debug",
                      default=False,
                      help="enable debug")
    parser.add_option("-c", "--config",
                      action="store", dest="config",
                      help="path to rest config")
    parser.add_option("-u", "--user",
                      action="store", dest="user",
                      help="user used with master password")
    parser.add_option("-p", "--password",
                      action="store", dest="password",
                      help="specify password to log in")

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
