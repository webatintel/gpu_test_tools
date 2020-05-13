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
      description='Check tryjob configurations',
      formatter_class=argparse.RawTextHelpFormatter)
  parser.add_argument('--src-dir', '--dir', '-d', default='.',
      help='Chromium source directory.\n\n')
  parser.add_argument('--print-job', '-j', action='store_true',
      help='Print the details of each job.\n\n')
  parser.add_argument('--print-test', '-t', action='store_true',
      help='Print the details of each test.\n\n')
  parser.add_argument('--email', '-e', action='store_true',
      help='Send the error report by email.\n\n')
  args = parser.parse_args()

  args.src_dir = path.abspath(args.src_dir)
  if path.basename(args.src_dir) == 'chromium' and path.exists(path.join(args.src_dir, 'src')):
    args.src_dir = path.join(args.src_dir, 'src')
  return args


class Test(object):
  def __init__(self, name):
    self.name = name
    self.args = []
    self.browser_args = []
    self.shards = None

  def __eq__(self, other):
    return (self.name == other.name and self.args == other.args and
        self.browser_args == other.browser_args and self.shards == other.shards)

  def __ne__(self, other):
    return (self.name != other.name or self.args != other.args or
        self.browser_args != other.browser_args or self.shards != other.shards)


class TryJob(object):
  def __init__(self, name):
    self.name = name
    self.platform = None
    self.gpu = None
    self.tests = []


def find_gtest_tests(items):
  for item in items:
    name = item['name'] if 'name' in item else item['test']
    if (name in ['gl_tests', 'vulkan_tests'] or 
        ('end2end' in name and 'spvc' not in name
          and (name.startswith('angle') or name.startswith('dawn')))):
      test = Test(name)
      test.args = item['args']
      if 'swarming' in item and 'shards' in item['swarming']:
        test.shards = item['swarming']['shards']
      yield test


def find_isolated_scripts(items):
  for item in items:
    name = item['name']
    if (name.startswith('webgl') or name.startswith('webgpu')
        or 'angle_perf' in name or 'dawn_perf' in name):
      name = name.replace('perftests', 'perf_tests')
      test = Test(name)
      for arg in item['args']:
        if arg.startswith('--extra-browser-args='):
          for browser_arg in arg[len('--extra-browser-args='):].split(' '):
            if not browser_arg.startswith('--enable-logging') and not browser_arg.startswith('--js-flags'):
              test.browser_args.append(browser_arg)
        elif arg.startswith('--additional-driver-flag='):
          test.browser_args.append(arg[len('--additional-driver-flag='):])
        elif arg.startswith('--browser=') or arg.startswith('--target='):
          pass
        else:
          test.args.append(arg)
      if 'swarming' in item and 'shards' in item['swarming']:
        test.shards = item['swarming']['shards']
      yield test


def find_intel_tryjob(config_file):
  for name, value in read_json(config_file).items():
    name = name.lower()
    if 'intel' not in name:
      continue
    if ('mac' in name or 'ozone' in name or 'deqp' in name
        or 'angle' in name or 'skiarenderer' in name):
      continue

    match = re_match(r'^(.*) \((.*)\)$', name)
    if match:
      name = match.group(1)
      gpu = match.group(2)
      if 'linux ' in name:
        platform = 'linux'
      elif 'win10 ' in name:
        platform = 'win_x86' if 'x86' in name else 'win'

      name = name.replace('linux ', '')
      name = name.replace('win10 ', '')
      name = name.replace('x64 ', '')
      name = name.replace('x86 ', '')
      name = name.replace('experimental', 'exp')
      name = name.replace('release', 'rel')
      name = name.replace(' ', '-')

      intel_job = TryJob(name)
      intel_job.platform = platform
      intel_job.gpu = gpu.replace(' ', '-')
      if 'gtest_tests' in value:
        for test in find_gtest_tests(value['gtest_tests']):
          intel_job.tests.append(test)
      if 'isolated_scripts' in value:
        for test in find_isolated_scripts(value['isolated_scripts']):
          intel_job.tests.append(test)
      yield intel_job


def main():
  args = parse_arguments()
  config = read_json(TRYJOB_CONFIG)

  def handle_error(title, body=''):
    print('%s\n%s\n' % (title, body))
    if args.email:
      send_email(config['email']['receiver']['admin'], title, body)

  def print_test(test):
    print(test.name + (' [%d]' % test.shards if test.shards else ''))
    for arg in test.args:
      print('    ' + arg)
    for arg in test.browser_args:
      print('        ' + arg)

  win_tests = {}
  linux_tests = {}
  for config_file in BUILDBOT_CONFIG:
    for job in find_intel_tryjob(path.join(args.src_dir, config_file)):
      if args.print_job:
        print('\n%s %s %s' % (job.name, job.platform, job.gpu))
      for test in job.tests:
        if args.print_job:
          print('    ' + test.name)
        if job.platform == 'win':
          assert test.name not in win_tests or test == win_tests[test.name]
          win_tests[test.name] = test
        elif job.platform == 'linux':
          assert test.name not in linux_tests or test == linux_tests[test.name]
          linux_tests[test.name] = test
  assert win_tests and linux_tests
  
  if args.print_test:
    for name in sorted(list(set(win_tests.keys()) | set(linux_tests.keys()))):
      print()
      if (name in win_tests and name in linux_tests
          and win_tests[name] != linux_tests[name]):
        print('[ Windows ]  ', end='')
        print_test(win_tests[name])
        print('[  Linux  ]  ', end='')
        print_test(linux_tests[name])
      elif name in win_tests:
        print_test(win_tests[name])
      elif name in linux_tests:
        print_test(linux_tests[name])

  for test_name, _, platform, _ in config['tryjob']:
    pos = test_name.find('(')
    if pos > 0:
      test_name = test_name[0:pos]
    if 'win' in platform and test_name in win_tests:
      win_tests.pop(test_name)
    if 'linux' in platform and test_name in linux_tests:
      linux_tests.pop(test_name)

  if win_tests:
    handle_error('Missing tryjob on Windows', ', '.join(win_tests.keys()))
  if linux_tests:
    handle_error('Missing tryjob on Linux', ', '.join(linux_tests.keys()))


if __name__ == '__main__':
  sys.exit(main())
