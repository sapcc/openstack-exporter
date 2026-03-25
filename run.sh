#!/bin/bash
# Activate virtual environment and run the OpenStack exporter

source /app/venv/bin/activate
exec openstack_exporter "$@"
