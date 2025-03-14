
from typing import Callable, Protocol, runtime_checkable



@runtime_checkable
class CinderSchedulerBaseFilter(Protocol):
    """Protocol API for a packet filter class.
    """
    def backend_passes(self, context, backend, volume_type):
        """The Protocol for the backend filter."""
        ...


class CinderSchedulerFilter:

    def __init__(self):
        self.filters = []

    def add_filter(self, filter: Callable):
        if not isinstance(filter, CinderSchedulerBaseFilter):
            raise ValueError("Filter must be a CinderSchedulerBaseFilter")
        self.filters.append(filter)

    def run_filters(self, pool, volume_type):
        """Filter the pool against the volume type."""
        filter_properties = {'resource_type': volume_type}

        for filter in self.filters:
            if not filter.backend_passes(pool, filter_properties):
                return False
        return True
