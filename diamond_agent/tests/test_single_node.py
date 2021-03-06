import os
import time
import json
import cPickle
import tempfile
from testtools import TestCase, ExpectedException

import psutil

from cloudify.decorators import operation
from cloudify.workflows import local
from diamond_agent.tasks import CONFIG_NAME

from diamond_agent.tasks import restart_diamond
from diamond_agent.tests import IGNORED_LOCAL_WORKFLOW_MODULES


class TestSingleNode(TestCase):
    def setUp(self):
        super(TestSingleNode, self).setUp()
        os.environ['MANAGEMENT_IP'] = '127.0.0.1'
        self.is_uninstallable = True
        self.env = None

    def tearDown(self):
        super(TestSingleNode, self).tearDown()
        if self.env and self.is_uninstallable:
                self.env.execute('uninstall', task_retries=0)

    # custom handler + custom collector
    def test_custom_collectors(self):
        log_path = tempfile.mktemp()
        inputs = {
            'diamond_config': {
                'prefix': tempfile.mkdtemp(prefix='cloudify-'),
                'interval': 1,
                'handlers': {
                    'test_handler.TestHandler': {
                        'path': 'handlers/test_handler.py',
                        'config': {
                            'log_path': log_path,
                        }
                    }
                }
            },
            'collectors_config': {
                'TestCollector': {
                    'path': 'collectors/test.py',
                    'config': {
                        'name': 'metric',
                        'value': 42,
                    },
                },
            },
        }
        self.env = self._create_env(inputs)
        self.env.execute('install', task_retries=0)
        if not is_created(log_path):
            self.fail('file {0} expected, but not found!'.format(log_path))

        with open(log_path, 'r') as fh:
            metric = cPickle.load(fh)
        metric_path = metric.path.split('.')

        collector_config = \
            inputs['collectors_config']['TestCollector']['config']
        self.assertEqual(collector_config['name'], metric_path[5])
        self.assertEqual(collector_config['value'], metric.value)
        self.assertEqual(self.env.name, metric_path[0])
        self.assertEqual('TestCollector', metric_path[4])

        node_instances = self.env.storage.get_node_instances()
        host_instance_id, node_id, node_instance_id = get_ids(node_instances,
                                                              'node')

        self.assertEqual(host_instance_id, metric_path[1])
        self.assertEqual(node_id, metric_path[2])
        self.assertEqual(node_instance_id, metric_path[3])

    def test_cloudify_handler_format(self):
        log_path = tempfile.mktemp()
        inputs = {
            'diamond_config': {
                'prefix': tempfile.mkdtemp(prefix='cloudify-'),
                'interval': 1,
                'handlers': {
                    'test_handler.TestHandler': {
                        'path': 'handlers/test_handler.py',
                        'config': {
                            'log_path': log_path,
                            'output_cloudify_format': True,
                        }
                    }
                }
            },
            'collectors_config': {
                'TestCollector': {
                    'path': 'collectors/test.py',
                    'config': {
                        'name': 'metric',
                        'value': 42,
                    },
                },
            },
        }
        self.env = self._create_env(inputs)
        self.env.execute('install', task_retries=0)
        if not is_created(log_path):
            self.fail('file {0} expected, but not found!'.format(log_path))

        with open(log_path, 'r') as fh:
            metric = json.loads(cPickle.load(fh))

        collector_config = \
            inputs['collectors_config']['TestCollector']['config']

        node_instances = self.env.storage.get_node_instances()
        expected_host, expected_node_name, expected_node_id = get_ids(
            node_instances, 'node')
        expected_path = collector_config['name']
        expected_metric = collector_config['value']
        expected_deployment_id = self.env.name
        expected_name = 'TestCollector'
        expected_unit = ''
        expected_type = 'GAUGE'
        expected_service = '.'.join([
            expected_deployment_id,
            expected_node_name,
            expected_node_id,
            expected_name,
            expected_path
        ])

        self.assertEqual(expected_path, metric['path'])
        self.assertEqual(expected_metric, metric['metric'])
        self.assertEqual(expected_deployment_id, metric['deployment_id'])
        self.assertEqual(expected_name, metric['name'])
        self.assertEqual(expected_unit, metric['unit'])
        self.assertEqual(expected_type, metric['type'])
        self.assertEqual(expected_host, metric['host'])
        self.assertEqual(expected_node_name, metric['node_name'])
        self.assertEqual(expected_node_id, metric['node_id'])
        self.assertEqual(expected_service, metric['service'])
        self.assertTrue(time.time() - 120 <= metric['time'] <= time.time())

    # custom handler + no collector
    # diamond should run without outputting anything
    def test_no_collectors(self):
        log_path = tempfile.mktemp()
        inputs = {
            'diamond_config': {
                'prefix': tempfile.mkdtemp(prefix='cloudify-'),
                'interval': 1,
                'handlers': {
                    'test_handler.TestHandler': {
                        'path': 'handlers/test_handler.py',
                        'config': {
                            'log_path': log_path,
                        },
                    }
                }
            },
            'collectors_config': {}
        }
        self.env = self._create_env(inputs)
        self.env.execute('install', task_retries=0)

        pid = get_pid(inputs)

        if not psutil.pid_exists(pid):
            self.fail('Diamond failed to start with empty collector list')

    def test_uninstall_workflow(self):
        inputs = {
            'diamond_config': {
                'prefix': tempfile.mkdtemp(prefix='cloudify-'),
                'interval': 1,
                'handlers': {
                    'diamond.handler.archive.ArchiveHandler': {
                        'config': {
                            'log_file': tempfile.mktemp(),
                        }
                    }
                }
            },
            'collectors_config': {},

        }
        prefix = inputs['diamond_config']['prefix']
        self.is_uninstallable = False
        self.env = self._create_env(inputs)
        self.env.execute('install', task_retries=0)
        pid_file = os.path.join(prefix, 'var', 'run', 'diamond.pid')
        with open(pid_file, 'r') as pf:
            pid = int(pf.read())

        # Check if all directories and paths have been created during install
        paths_to_uninstall = self._mock_get_paths(prefix)
        for path in paths_to_uninstall:
            self.assertTrue(os.path.exists(path),
                            msg="Path doesn't exist: {0}".format(path))

        if psutil.pid_exists(pid):
            self.env.execute('uninstall', task_retries=0)
            time.sleep(5)
        else:
            self.fail('diamond process not running')
        self.assertFalse(psutil.pid_exists(pid))

        # Check if uninstall cleans up after diamond
        for path in paths_to_uninstall:
            self.assertFalse(os.path.exists(path),
                             msg="Path exists: {0}".format(path))

    def test_no_handlers(self):
        inputs = {
            'diamond_config': {
                'handlers': {},
            },
            'collectors_config': {},

        }
        self.is_uninstallable = False
        self.env = self._create_env(inputs)
        with ExpectedException(RuntimeError, ".*Empty handlers dict"):
            self.env.execute('install', task_retries=0)

    def test_restart_plugin_script(self):
        """A script that restarts diamond doesn't interfere with the plugin.

        If the add_collectors tasks run in parallel with a script that
        also happens to restart diamond, there's a race condition between them
        looking up the process by the PID, making one of them to break.
        """
        blueprint_yaml = self._get_resource_path('blueprint',
                                                 'restart_diamond_script.yaml')
        self.is_uninstallable = False
        local_env = local.init_env(
            blueprint_yaml, ignored_modules=IGNORED_LOCAL_WORKFLOW_MODULES)
        self.addCleanup(local_env.execute, 'uninstall')
        # this needs a threadpool size >1 so that the add_collectors task
        # can run in parallel with the custom restart task
        local_env.execute('install', task_thread_pool_size=5)

    def _mock_get_paths(self, prefix):
        return [
            os.path.join(prefix, 'etc', CONFIG_NAME),
            os.path.join(prefix, 'etc', 'collectors'),
            os.path.join(prefix, 'collectors'),
            os.path.join(prefix, 'etc', 'handlers'),
            os.path.join(prefix, 'handlers')
        ]

    def _create_env(self, inputs):
        return local.init_env(self._blueprint_path(),
                              inputs=inputs,
                              ignored_modules=IGNORED_LOCAL_WORKFLOW_MODULES)

    def _blueprint_path(self):
        return self._get_resource_path('blueprint', 'single_node.yaml')

    def _get_resource_path(self, *args):
        return os.path.join(os.path.dirname(__file__), 'resources', *args)


def collector_in_log(path, collector):
    with open(path, 'r') as fh:
        try:
            while True:
                metric = cPickle.load(fh)
                if metric.path.split('.')[3] == collector:
                    return True
        except EOFError:
            return False


def is_created(path, timeout=5):
    for _ in range(timeout):
        if os.path.isfile(path):
            return True
        time.sleep(1)
    return False


def get_ids(instances, name):
    for instance in instances:
        if instance['name'] == name:
            return instance['host_id'], instance['node_id'], instance['id']


def get_pid(config):
    pid_file = os.path.join(config['diamond_config']['prefix'],
                            'var', 'run', 'diamond.pid')

    with open(pid_file, 'r') as pf:
        pid = int(pf.read())

    return pid


@operation
def sleep_and_restart_diamond(ctx):
    """Restart diamond 5 times, with 3 second pauses between restarts.

    This is a task used in the TestSingleNode.test_restart_plugin_script test.
    """
    config = ctx.source.instance.runtime_properties['diamond_paths']['config']

    for num in range(5):
        time.sleep(3)
        restart_diamond(config)
