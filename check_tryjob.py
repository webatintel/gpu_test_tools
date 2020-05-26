#!/usr/bin/env python3

import argparse

from util.base_util import *
from util.file_util import *

BUILDBOT_CONFIG = [path.join('testing', 'buildbot', 'chromium.gpu.json'),
                   path.join('testing', 'buildbot', 'chromium.gpu.fyi.json'),
                   path.join('testing', 'buildbot', 'chromium.dawn.json')]

def parse_arguments():
  parser = argparse.ArgumentParser(
      description='Check tryjob configuration',
      formatter_class=argparse.RawTextHelpFormatter)
  parser.add_argument('--src-dir', '--dir', '-d', default='.',
      help='Chromium source directory.\n\n')
  parser.add_argument('--print-job', '-j', action='store_true',
      help='Print the details of each job.\n\n')
  parser.add_argument('--print-task', '-t', action='store_true',
      help='Print the details of each task.\n\n')
  parser.add_argument('--email', '-e', action='store_true',
      help='Send the error by email.\n\n')
  args = parser.parse_args()

  config = read_json(TRYJOB_CONFIG)
  args.name_to_type = {}
  for test_name, test_type, _, _ in config['tryjob']:
    args.name_to_type[test_name] = test_type
  args.shards       = config['shards']
  args.test_args    = config['test_args']
  args.browser_args = config['browser_args']
  args.receiver = config['email']['receiver']['admin']

  args.src_dir = path.abspath(args.src_dir)
  if path.exists(path.join(args.src_dir, 'src')):
    args.src_dir = path.join(args.src_dir, 'src')
  return args


class Task(object):
  def __init__(self, name):
    self.name = name
    self.shards = None
    self.test_args = []
    self.browser_args = []

  def __eq__(self, other):
    return ((self.name, self.shards, self.test_args, self.browser_args) ==
            (other.name, other.shards, other.test_args, other.browser_args))

  def __str__(self):
    ret = '    ===== shards: %d =====\n' % self.shards if self.shards else ''
    for arg in self.test_args:
      ret += '    %s\n' % arg
    for arg in self.browser_args:
      ret += '        %s\n' % arg
    return ret


class TryJob(object):
  def __init__(self, name, platform, gpu):
    self.name = name
    self.platform = platform
    self.gpu = gpu
    self.tasks = []

  def __str__(self):
    ret = '    %s %s\n' % (self.platform, self.gpu)
    for task in self.tasks:
      ret += '        %s\n' % task.name
    return ret


def find_gtest_tests(items):
  for item in items:
    name = item['name'] if 'name' in item else item['test']
    if 'spvc' in name:
      continue
    if (name in ['gl_tests', 'vulkan_tests'] or 
        match_any(['angle_end2end', 'dawn_end2end'], lambda x: name.startswith(x))):
      task = Task(name)
      task.test_args = item['args']
      if 'swarming' in item and 'shards' in item['swarming']:
        task.shards = item['swarming']['shards']
      yield task


def find_isolated_scripts(items):
  for item in items:
    name = item['name']
    if match_any(['webgl', 'webgpu', 'angle_perf', 'dawn_perf'], lambda x: name.startswith(x)):
      task = Task(name.replace('perftests', 'perf_tests'))
      for arg in item['args']:
        if arg.startswith('--extra-browser-args='):
          for browser_arg in arg[len('--extra-browser-args='):].split(' '):
            if not match_any(['--enable-logging', '--js-flags'], lambda x: browser_arg.startswith(x)):
              task.browser_args.append(browser_arg)
        elif arg.startswith('--additional-driver-flag='):
          task.browser_args.append(arg[len('--additional-driver-flag='):])
        elif not match_any(['--browser=', '--target=', '--gtest-benchmark-name',
                            '--read-abbreviated-json-results-from'], lambda x: arg.startswith(x)):
          task.test_args.append(arg)
      if 'swarming' in item and 'shards' in item['swarming']:
        task.shards = item['swarming']['shards']
      yield task


def find_tryjob(config_file):
  for name, value in read_json(config_file).items():
    name = name.lower().replace(' ', '-')
    if (not 'intel' in name or
        match_any(['mac', 'x86', 'ozone', 'deqp', 'angle', 'skia'], lambda x: x in name)):
      continue
    match = re_match(r'^(.*)-\((.*)\)$', name)
    name, gpu = match.group(1), match.group(2)
    if 'linux' in name:
      platform = 'linux'
    elif 'win10' in name:
      platform = 'win'
    name = name.replace('linux-', '').replace('win10-', '').replace('x64-', '')
    name = name.replace('experimental', 'exp').replace('release', 'rel')

    tryjob = TryJob(name, platform, gpu)
    if 'gtest_tests' in value:
      for task in find_gtest_tests(value['gtest_tests']):
        tryjob.tasks.append(task)
    if 'isolated_scripts' in value:
      for task in find_isolated_scripts(value['isolated_scripts']):
        tryjob.tasks.append(task)
    if tryjob.tasks:
      yield tryjob


def main():
  args = parse_arguments()

  def handle_error(error):
    print(error)
    if args.email:
      send_email(args.receiver, error)

  total_jobs, total_tasks = defaultdict(list), defaultdict(dict)
  for config_file in BUILDBOT_CONFIG:
    for tryjob in find_tryjob(path.join(args.src_dir, config_file)):
      total_jobs[tryjob.name].append(tryjob)
      for task in tryjob.tasks:
        total_tasks[task.name][tryjob.platform] = task

  if args.print_job:
    for name, tryjobs in total_jobs.items():
      print(name)
      for tryjob in tryjobs:
        print(tryjob)

  if args.print_task:
    for name, tasks in total_tasks.items():
      print(name)
      if 'win' in tasks and 'linux' in tasks and tasks['win'] != tasks['linux']:
        print('    [Win]\n%s' % tasks['win'])
        print('    [Linux]\n%s' % tasks['linux'])
      elif 'win' in tasks:
        print(tasks['win'])
      elif 'linux' in tasks:
        print(tasks['linux'])

  for name, tasks in total_tasks.items():
    if not name in args.name_to_type:
      handle_error('Missing test: ' + name)
      continue
    module, backend = args.name_to_type[name]
    test_keys = [module] + backend.split('_')
    test_keys = ['_'.join(test_keys[0:i]) for i in range(1, len(test_keys)+1)]
    for platform, task in tasks.items():
      if task.shards:
        key = find_match(test_keys, lambda x: x in args.shards)
        if not key or task.shards != args.shards[key]:
          handle_error('Shard number mismatch: %s on %s' % (task.name, platform))

      test_args, browser_args = [], []
      for key in test_keys + ['%s_%s' % (x, platform) for x in test_keys]:
        test_args += args.test_args.get(key, [])
        browser_args += args.browser_args.get(key, [])

      if not set(task.test_args) <= set(test_args):
        handle_error('Test argument mismatch: %s on %s' % (task.name, platform))
      if not set(task.browser_args) <= set(browser_args):
        handle_error('Browser argument mismatch: %s on %s' % (task.name, platform))


if __name__ == '__main__':
  sys.exit(main())
