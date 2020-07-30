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

from abc import ABC, abstractmethod
import yaml


class BaseCollector(ABC):
    @abstractmethod
    def describe(self):
        pass

    @abstractmethod
    def collect(self):
        pass

    def read_rest_yaml(self):
        with open('./rest.yaml') as yaml_file:
            rest_yaml = yaml.safe_load(yaml_file)
        return rest_yaml
