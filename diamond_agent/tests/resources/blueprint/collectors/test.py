#########
# Copyright (c) 2014 GigaSpaces Technologies Ltd. All rights reserved
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
#  * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  * See the License for the specific language governing permissions and
#  * limitations under the License.


import diamond.collector


class TestCollector(diamond.collector.Collector):

    def collect(self):
        """
        Overrides the Collector.collect method
        """

        # Set Metric Name
        metric_name = "my.example.metric"
        # Set Metric Value
        metric_value = 43

        # Publish Metric
        self.publish(metric_name, metric_value)