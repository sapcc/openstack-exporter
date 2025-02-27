
import logging
import math

from cachetools import cached, TTLCache

from openstack_exporter.utils import filters
from openstack_exporter.utils.filters import capabilities


LOG = logging.getLogger('openstack_exporter.exporter')
SAP_HIDDEN_BACKEND_KEY = '__cinder_internal_backend'


def extract_host(host, level='backend', default_pool_name=False):
    """Extract Host, Backend or Pool information from host string.

    :param host: String for host, which could include host@backend#pool info
    :param level: Indicate which level of information should be extracted
                  from host string. Level can be 'host', 'backend' or 'pool',
                  default value is 'backend'
    :param default_pool_name: this flag specify what to do if level == 'pool'
                              and there is no 'pool' info encoded in host
                              string.  default_pool_name=True will return
                              DEFAULT_POOL_NAME, otherwise we return None.
                              Default value of this parameter is False.
    :return: expected information, string or None
    :raises: exception.InvalidVolume

    For example:
        host = 'HostA@BackendB#PoolC'
        ret = extract_host(host, 'host')
        # ret is 'HostA'
        ret = extract_host(host, 'backend')
        # ret is 'HostA@BackendB'
        ret = extract_host(host, 'pool')
        # ret is 'PoolC'

        host = 'HostX@BackendY'
        ret = extract_host(host, 'pool')
        # ret is None
        ret = extract_host(host, 'pool', True)
        # ret is '_pool0'
    """
    DEFAULT_POOL_NAME = '_pool0'

    if host is None:
        raise Exception("Must specify a host")

    if level == 'host':
        # make sure pool is not included
        hst = host.split('#')[0]
        return hst.split('@')[0]
    elif level == 'backend':
        return host.split('#')[0]
    elif level == 'pool':
        lst = host.split('#')
        if len(lst) == 2:
            return lst[1]
        elif default_pool_name is True:
            return DEFAULT_POOL_NAME
        else:
            return None


def calculate_capacity_factors(total_capacity: float,
                               free_capacity: float,
                               provisioned_capacity: float,
                               thin_provisioning_support: bool,
                               max_over_subscription_ratio: float,
                               reserved_percentage: float,
                               thin: bool) -> dict:
    """Create the various capacity factors of the a particular backend.

    Based off of definition of terms
    cinder-specs/specs/queens/provisioning-improvements.html

    total_capacity - The reported total capacity in the backend.
    free_capacity - The free space/capacity as reported by the backend.
    reserved_capacity - The amount of space reserved from the total_capacity
    as reported by the backend.
    total_reserved_available_capacity - The total capacity minus reserved
    capacity

    max_over_subscription_ratio - as reported by the backend
    total_available_capacity - The total capacity available to cinder
    calculated
    thick: total_reserved_available_capacity
    OR
    thin: total_reserved_available_capacity and max_over_subscription_ratio

    provisioned_capacity - as reported by backend or volume manager
    (allocated_capacity_gb)

    calculated_free_capacity - total_available_capacity - provisioned_capacity
    virtual_free_capacity - The calculated free capacity available to cinder
    to allocate new storage.
    For thin: calculated_free_capacity
    For thick: the reported free_capacity can be less than the calculated
    Capacity, so we use free_capacity - reserved_capacity.

    free_percent - the percentage of the total_available_capacity is left over
    provisioned_ratio - The ratio of provisioned storage to
    total_available_capacity
    """

    total = float(total_capacity)
    reserved = float(reserved_percentage) / 100
    reserved_capacity = math.floor(total * reserved)
    total_reserved_available = total - reserved_capacity

    if thin and thin_provisioning_support:
        total_available_capacity = (
                total_reserved_available * max_over_subscription_ratio
        )
        calculated_free = total_available_capacity - provisioned_capacity
        virtual_free = calculated_free
        provisioned_type = 'thin'
    else:
        # Calculate how much free space is left after taking into
        # account the reserved space.
        total_available_capacity = total_reserved_available
        calculated_free = total_available_capacity - provisioned_capacity
        virtual_free = calculated_free
        if free_capacity < calculated_free:
            virtual_free = free_capacity
        max_over_subscription_ratio = None
        provisioned_type = 'thick'

    if total_available_capacity:
        provisioned_ratio = provisioned_capacity / total_available_capacity
        free_percent = (virtual_free / total_available_capacity) * 100
    else:
        provisioned_ratio = 0
        free_percent = 0

    return {
        "total_capacity": total,
        "free_capacity": free_capacity,
        "reserved_capacity": reserved_capacity,
        "total_reserved_available_capacity": int(total_reserved_available),
        "max_over_subscription_ratio": (
                max_over_subscription_ratio if provisioned_type == 'thin' else None
        ),
        "total_available_capacity": int(total_available_capacity),
        "provisioned_capacity": provisioned_capacity,
        "calculated_free_capacity": int(calculated_free),
        "virtual_free_capacity": int(virtual_free),
        "free_percent": free_percent,
        "provisioned_ratio": provisioned_ratio,
        "provisioned_type": provisioned_type
    }


def parse_pool_data(pool, volume_type):
    """Construct the data from the pool information from the scheduler."""
    caps = pool['capabilities']
    shard_name = caps.get('vcenter-shard')

    data = {"backend": caps["volume_backend_name"],
            "pool": pool['name'].split('#')[1],
            "shard": shard_name}
    can_overcommit = False

    # Only allow overcommit if the volume type that matches
    # The backend is thin provisioned.
    # A missing key of provisioning:type means thin provisioning.
    if volume_type and volume_type['extra_specs'].get('provisioning:type') != 'thick':
        can_overcommit = True
    elif "thin_provisioning_support" in caps:
        can_overcommit = caps['thin_provisioning_support']

    total_capacity_gb = caps.get('total_capacity_gb', 0)
    allocated_capacity_gb = caps.get('allocated_capacity_gb', 0)
    reserved_percentage = caps.get('reserved_percentage', 0)
    max_over_subscription_ratio = float(
        caps.get('max_over_subscription_ratio', 1)
    )
    free_capacity_gb = caps.get('free_capacity_gb', 0)

    capacity_factors = calculate_capacity_factors(
        total_capacity_gb,
        free_capacity_gb,
        allocated_capacity_gb,
        caps.get('thin_provisioning_support', False),
        max_over_subscription_ratio,
        reserved_percentage,
        can_overcommit,
    )
    available_capacity_gb = capacity_factors["total_available_capacity"]
    virtual_free_gb = capacity_factors["virtual_free_capacity"]
    percent_left = capacity_factors["free_percent"]
    overcommit_ratio = capacity_factors["provisioned_ratio"]

    data["can_overcommit"] = can_overcommit
    data['total_capacity_gb'] = total_capacity_gb
    data['max_over_subscription_ratio'] = max_over_subscription_ratio
    data['provisioned_capacity_gb'] = caps.get('provisioned_capacity_gb', 0)
    data['overcommit_ratio'] = overcommit_ratio

    data['available_capacity_gb'] = available_capacity_gb
    data['allocated_capacity_gb'] = allocated_capacity_gb
    # What the backend is reporting
    data['free_capacity_gb'] = free_capacity_gb
    # What cinder can use
    data['virtual_free_capacity_gb'] = virtual_free_gb
    data['percent_left'] = percent_left
    data['reserved_percentage'] = reserved_percentage

    if can_overcommit:
        data['provisioning_type'] = 'thin'
    else:
        data['provisioning_type'] = 'thick'

    if 'aggregate_id' in caps:
        data['aggregate_id'] = caps['aggregate_id']

    data['driver_version'] = caps['driver_version']
    return data


def get_cinder_pools(client):
    """Fetch the pool stats from the current shard.

    Pass in a pool name if you only want the stats for 1 pool

    if raw is True, return the raw data from the scheduler.
    """
    volume_api = client.volume
    return volume_api.backend_pools()


@cached(TTLCache(ttl=3600, maxsize=1024))
def get_volume_types(client):
    """Get the list of volume types."""
    volume_api = client.volume
    return volume_api.types()


def get_volume_types_by_name(client):
    """Get the list of volume types by name."""
    v_types = get_volume_types(client)
    return {vt['name']: vt for vt in v_types}


def get_scheduler_hints_from_volume(volume):
    filter_properties = {}
    if "scheduler_hint_same_host" in volume.metadata:
        hint = volume.metadata["scheduler_hint_same_host"]
        filter_properties["same_host"] = hint.split(',')

    if "scheduler_hint_different_host" in volume.metadata:
        hint = volume.metadata["scheduler_hint_different_host"]
        filter_properties["different_host"] = hint.split(',')
    return filter_properties


def set_scheduler_hints_to_volume_metadata(scheduler_hints,
                                           metadata):
    if scheduler_hints:
        if 'same_host' in scheduler_hints:
            if isinstance(scheduler_hints['same_host'], str):
                hint = scheduler_hints['same_host']
            else:
                hint = ','.join(scheduler_hints["same_host"])
            metadata["scheduler_hint_same_host"] = hint
        if "different_host" in scheduler_hints:
            if isinstance(scheduler_hints['different_host'], str):
                hint = scheduler_hints["different_host"]
            else:
                hint = ','.join(scheduler_hints["different_host"])
            metadata["scheduler_hint_different_host"] = hint
    return metadata


def extract_shard_from_host(host):
    """Extract the shard name from a cinder backend host entry."""
    return host[host.find('vc-'):]


def filter_pools(client, pools):
    """Run the capabilities filter on the pools.
    
    This is used to assign pools to a volume type.

    This uses the same capabilities filter as the cinder scheduler
    to ensure the matching for volume types to pools is exactly the
    same.
    """
    v_types = get_volume_types(client)
    volume_types = []
    for v_type in v_types:
        volume_types.append(v_type)

    scheduler_filter = filters.CinderSchedulerFilter()
    scheduler_filter.add_filter(capabilities.CapabilitiesFilter())

    pool_list = {'Unknown': []}

    # now for each volume type we have filter the pool through it
    # to see if it matches, not unlike the cinder scheduler.
    for pool in pools:
        found = False
        for v_type in volume_types:
            if scheduler_filter.run_filters(pool, v_type):
                if v_type['name'] not in pool_list:
                    pool_list[v_type['name']] = []
                pool_list[v_type['name']].append(pool)
                found = True
        if not found:
            pool_list['Unknown'].append(pool)

    return pool_list


def aggregate_pools(pools):
    """Create aggregated stats for pools.

    Some pools are reported by multiple drivers (shards). This will
    aggregate the stats for those pools.

    If a pool has an aggregate_id, it is an aggregate pool, meaning
    that the same pool is reported by multiple drivers (shards).

    """
    def calc_virtual_free(available_capacity, allocated_capacity):
        return available_capacity - allocated_capacity

    def calc_free_percent(virtual_free, total_available_capacity):
        if total_available_capacity == 0:
            return 0
        return math.floor((virtual_free / total_available_capacity) * 100)
    
    def calc_available_capacity(total_capacity, reserved_percentage):
        reserved = float(reserved_percentage) / 100
        reserved_capacity = math.floor(total_capacity * reserved)
        return total_capacity - reserved_capacity

    agg_pools = {}
    for shard in pools:
        for pool in pools[shard]:
            if  "aggregate_id" in pool['capabilities']:
                caps = pool['capabilities']
                pool_name = extract_host(pool['name'], 'pool')
                available_cap = calc_available_capacity(
                    caps['total_capacity_gb'],
                    caps['reserved_percentage']
                )

                if pool_name not in agg_pools:
                    virtual_free = calc_virtual_free(
                        available_cap,
                        caps['allocated_capacity_gb']
                    )
                    agg_pools[pool_name] = {
                        'name': pool_name,
                        'aggregate_id': caps['aggregate_id'],
                        'allocated_capacity_gb': caps['allocated_capacity_gb'],
                        'free_capacity_gb': caps['free_capacity_gb'],
                        'total_capacity_gb': caps['total_capacity_gb'],
                        'reserved_percentage': caps['reserved_percentage'],
                        'max_over_subscription_ratio': caps['max_over_subscription_ratio'],
                        'thin_provisioning_support': caps['thin_provisioning_support'],
                        'aggregate_id': caps['aggregate_id'],
                        'virtual_free_capacity_gb': virtual_free,
                    }
                    if 'netapp_fqdn' in caps['custom_attributes']:
                        agg_pools[pool_name]['netapp_fqdn'] = caps['custom_attributes']['netapp_fqdn']
                    else:
                        agg_pools[pool_name]['netapp_fqdn'] = "N/A"
                else:
                    agg_pools[pool_name]['allocated_capacity_gb'] += caps['allocated_capacity_gb']
                    agg_pools[pool_name]['virtual_free_capacity_gb'] += virtual_free
                    virtual_free = calc_virtual_free(
                        available_cap,
                        agg_pools[pool_name]['allocated_capacity_gb']
                    )
                    agg_pools[pool_name]['free_percent'] = calc_free_percent(
                        virtual_free, available_cap
                    )

    return agg_pools

