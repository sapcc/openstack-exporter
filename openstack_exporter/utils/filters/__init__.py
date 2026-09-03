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
