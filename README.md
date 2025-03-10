# openstack-exporter

exporter to extract custom metrics from OpenStack

This is an exporter using [OpenStack SDK](https://docs.openstack.org/openstacksdk/latest/).
There is only 1 exporter new, which is for cinder to export the volume driver backend stats.

## Running the exporter

The exporter should be installed with
```
pip install .
```

Now run the exporter passing in the config.yaml
```
openstack_exporter --config <path to openstack-config.yaml>
```

In case you want your secrets stored somewhere else, e.g. when they come from a k8s Secret, you can provide them with the extra `--secrets` option
```
openstack_exporter --config <path to openstack-config.yaml> --secrets <path to openstack-secrets.yaml>
```

You can use the given Dockerfile to build and use the docker container for an easy rampup

```
make
docker run -it openstack-exporter:0.1 sh
```

## Adding a collector

You can add a new collector to `openstack_exporter/collectors`.  Then you
must add the call to the collector in openstack_exporter/exporter.py 

```
REGISTRY.register(myexporter.Myexporter(openstack_config))
```
