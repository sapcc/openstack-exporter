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
import importlib
import logging
import os
import sys
import time

from prometheus_client.core import REGISTRY
from prometheus_client import start_http_server
import yaml

LOG = logging.getLogger(__name__)


def factory(module_class_string, super_cls: type = None, **kwargs):
    """
    :param module_class_string: full name of the class to create an object of
    :param super_cls: expected super class for validity, None if bypass
    :param kwargs: parameters to pass
    :return:
    """
    module_name, class_name = module_class_string.rsplit(".", 1)
    module = importlib.import_module(module_name)
    assert hasattr(module, class_name), (
        "class {} is not in {}".format(class_name, module_name))
    # click.echo('reading class {} from module {}'.format(
    #     class_name, module_name))
    cls = getattr(module, class_name)
    if super_cls is not None:
        assert issubclass(cls, super_cls), (
            "class {} should inherit from {}".format(
                class_name, super_cls.__name__))
    # click.echo('initialising {} with params {}'.format(class_name, kwargs))
    obj = cls(**kwargs)
    return obj


def load_and_register_collectors(collector_config, openstack_config):
    """Load all enabled collectors from config."""
    for collector in collector_config:
        cfg = collector_config[collector]
        if cfg['enabled']:
            LOG.info("Loading collector '{}'".format(cfg['collector']))
            cls = factory(cfg['collector'], openstack_config=openstack_config)
            REGISTRY.register(cls)


def run_prometheus_server(port, collector_config, openstack_config):
    start_http_server(int(port))
    load_and_register_collectors(collector_config, openstack_config)
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
    collector_config = config_obj['collectors']

    if exporter_config['log_level']:
        LOG.setLevel(logging.getLevelName(
            exporter_config['log_level'].upper()))
    else:
        LOG.setLevel(logging.getLevelName("INFO"))

    format = '[%(asctime)s] [%(levelname)s] %(message)s'
    logging.basicConfig(stream=sys.stdout, format=format)

    LOG.info("Starting OpenStack Exporter on port={} config={}".format(
        port,
        config
    ))

    run_prometheus_server(port, collector_config, os_config)


if __name__ == '__main__':
    main()
