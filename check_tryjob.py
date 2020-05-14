#!/usr/bin/env python3

import argparse
import os
import sys

from util.base_util import *
from util.file_util import *
from os import path

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
  parser.add_argument('--print-test', '-t', action='store_true',
      help='Print the details of each test.\n\n')
  parser.add_argument('--email', '-e', action='store_true',
      help='Send the error by email.\n\n')
  args = parser.parse_args()

  config = read_json(TRYJOB_CONFIG)
  args.test_backend = {}
  for test_name, test_arg, _, _ in config['tryjob']:
    args.test_backend[test_name] = test_arg
  args.test_shards   = config['test_shards']
  args.test_args     = config['test_args']
  args.browser_args  = config['browser_args']
  args.variable_args = config['variable_args']
  args.receiver = config['email']['receiver']['admin']

  args.src_dir = path.abspath(args.src_dir)
  if path.basename(args.src_dir) == 'chromium' and path.exists(path.join(args.src_dir, 'src')):
    args.src_dir = path.join(args.src_dir, 'src')
  return args


class Test(object):
  def __init__(self, name):
    self.name = name
    self.shards = None
    self.args = []
    self.browser_args = []

  def __eq__(self, other):
    return (self.name == other.name and self.shards == other.shards and
            self.args == other.args and self.browser_args == other.browser_args)

  def __str__(self):
    ret = '    ===== shards: %d =====\n' % self.shards if self.shards else ''
    for arg in self.args:
      ret += '    %s\n' % arg
    for arg in self.browser_args:
      ret += '        %s\n' % arg
    return ret


class TryJob(object):
  def __init__(self, name, platform, gpu):
    self.name = name
    self.platform = platform
    self.gpu = gpu
    self.tests = []

  def __str__(self):
    ret = '    %s %s\n' % (self.platform, self.gpu)
    for test in self.tests:
      ret += '        %s\n' % test.name
    return ret


def find_gtest_tests(items):
  for item in items:
    name = item['name'] if 'name' in item else item['test']
    if 'spvc' in name:
      continue
    if (name in ['gl_tests', 'vulkan_tests'] or 
        match_any(['angle_end2end', 'dawn_end2end'], lambda x: name.startswith(x))):
      test = Test(name)
      test.args = item['args']
      if 'swarming' in item and 'shards' in item['swarming']:
        test.shards = item['swarming']['shards']
      yield test


def find_isolated_scripts(items):
  for item in items:
    name = item['name']
    if match_any(['webgl', 'webgpu', 'angle_perf', 'dawn_perf'], lambda x: name.startswith(x)):
      test = Test(name.replace('perftests', 'perf_tests'))
      for arg in item['args']:
        if arg.startswith('--extra-browser-args='):
          for browser_arg in arg[len('--extra-browser-args='):].split(' '):
            if not match_any(['--enable-logging', '--js-flags'], lambda x: browser_arg.startswith(x)):
              test.browser_args.append(browser_arg)
        elif arg.startswith('--additional-driver-flag='):
          test.browser_args.append(arg[len('--additional-driver-flag='):])
        elif not match_any(['--browser=', '--target=', '--gtest-benchmark-name'], lambda x: arg.startswith(x)):
          test.args.append(arg)
      if 'swarming' in item and 'shards' in item['swarming']:
        test.shards = item['swarming']['shards']
      yield test


def find_tryjob(config_file):
  for name, value in read_json(config_file).items():
    name = name.lower().replace(' ', '-')
    if (not 'intel' in name or
        match_any(['mac', 'x86', 'ozone', 'deqp', 'angle', 'skia'], lambda x: x in name)):
      continue
    match = re_match(r'^(.*)-\((.*)\)$', name)
    if match:
      name, gpu = match.group(1), match.group(2)
      if 'linux-' in name:
        platform = 'linux'
      elif 'win10-' in name:
        platform = 'win'
      name = name.replace('linux-', '').replace('win10-', '').replace('x64-', '')
      name = name.replace('experimental', 'exp').replace('release', 'rel')

      tryjob = TryJob(name, platform, gpu)
      if 'gtest_tests' in value:
        for test in find_gtest_tests(value['gtest_tests']):
          tryjob.tests.append(test)
      if 'isolated_scripts' in value:
        for test in find_isolated_scripts(value['isolated_scripts']):
          tryjob.tests.append(test)
      if tryjob.tests:
        yield tryjob


def main():
  args = parse_arguments()

  def handle_error(error):
    print(error)
    if args.email:
      send_email(args.receiver, error)

  total_jobs, total_tests = {}, {}
  for config_file in BUILDBOT_CONFIG:
    for tryjob in find_tryjob(path.join(args.src_dir, config_file)):
      total_jobs.setdefault(tryjob.name, [])
      total_jobs[tryjob.name].append(tryjob)
      for test in tryjob.tests:
        total_tests.setdefault(test.name, {'win': None, 'linux': None})
        total_tests[test.name][tryjob.platform] = test

  if args.print_job:
    for name, tryjobs in total_jobs.items():
      print(name)
      for tryjob in tryjobs:
        print(tryjob)

  if args.print_test:
    for name, tests in total_tests.items():
      print(name)
      if tests['win'] and tests['linux'] and tests['win'] != tests['linux']:
        print('    [Win]\n' + str(tests['win']))
        print('    [Linux]\n' + str(tests['linux']))
      elif tests['win']:
        print(tests['win'])
      elif tests['linux']:
        print(tests['linux'])

  for name, tests in total_tests.items():
    if not name in args.test_backend:
      handle_error('Missing test: ' + name)
      continue
    test_type, backend = args.test_backend[name]
    for platform, test in tests.items():
      if not test:
        continue
      if test.shards:
        ref_shards = None
        for key in [test_type + '_' + backend, test_type]:
          if key in args.test_shards:
            ref_shards = args.test_shards[key]
            break
        if not ref_shards or test.shards != ref_shards:
          handle_error('Shard number mismatch: %s %s' % (test.name, platform))

      test_args, browser_args = [], []
      for arg in test.args:
        if not match_any(args.variable_args, lambda x: arg.startswith(x)):
          test_args.append(arg)
      for arg in test.browser_args:
        if not match_any(args.variable_args, lambda x: arg.startswith(x)):
          browser_args.append(arg)
      
      ref_test_args, ref_browser_args = [], []
      for key in [test_type, test_type + '_' + backend]:
        ref_test_args += args.test_args.get(key, [])
        ref_browser_args += args.browser_args.get(key, [])

      if not set(test_args) <= set(ref_test_args):
        handle_error('Test argument mismatch: %s %s' % (test.name, platform))
      if not set(browser_args) <= set(ref_browser_args):
        handle_error('Browser argument mismatch: %s %s' % (test.name, platform))


if __name__ == '__main__':
  sys.exit(main())
