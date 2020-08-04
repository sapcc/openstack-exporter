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

import click
import logging
import os
import sys
import time

from prometheus_client.core import REGISTRY
from prometheus_client import start_http_server
import yaml

from openstack_exporter.collectors import cinderbackend


def run_prometheus_server(port, openstack_config):
    start_http_server(int(port))
    REGISTRY.register(cinderbackend.CinderBackendCollector(openstack_config))
    while True:
        time.sleep(1)


def get_config(config_file):
    if os.path.exists(config_file):
        try:
            with open(config_file) as f:
                config = yaml.load(f, Loader=yaml.FullLoader)
        except IOError as e:
            logging.error("Couldn't open configuration file: " + str(e))
        return config
    else:
        logging.error("Config file doesn't exist: " + config_file)
        exit(0)


@click.command()
@click.option("--port", metavar="<port>", default=9102,
              help="specify exporter serving port")
@click.option("-c", "--config", metavar="<config>",
              help="path to rest config")
@click.version_option()
@click.help_option()
def main(port, config):
    if not config:
        raise click.ClickException("Missing OpenStack config yaml --config")

    config_obj = get_config(config)
    exporter_config = config_obj['exporter']
    os_config = config_obj['openstack']

    log = logging.getLogger(__name__)
    if exporter_config['log_level']:
        log.setLevel(logging.getLevelName(
            exporter_config['log_level'].upper()))
    else:
        log.setLevel(logging.getLevelName("INFO"))

    format = '[%(asctime)s] [%(levelname)s] %(message)s'
    logging.basicConfig(stream=sys.stdout, format=format)

    log.info("Starting OpenStack Exporter on port={} config={}".format(
        port,
        config
    ))

    run_prometheus_server(port, os_config)


if __name__ == '__main__':
    main()
