#!/usr/bin/env python

import argparse
import os
import sys

from util.base_util import *
from util.file_util import *
from os import path

OFFICIAL_TRYJOB_CONFIG = [path.join('testing', 'buildbot', 'chromium.gpu.json'),
                          path.join('testing', 'buildbot', 'chromium.gpu.fyi.json'),
                          path.join('testing', 'buildbot', 'chromium.dawn.json')]
TRYJOB_CONFIG = path.join(path.dirname(path.abspath(__file__)), 'tryjob.json')

def parse_arguments():
  parser = argparse.ArgumentParser(
      description='Find try bot configurations',
      formatter_class=argparse.RawTextHelpFormatter)
  parser.add_argument('--src-dir', '--dir', '-d', default='.',
      help='Chromium source directory.\n\n')
  parser.add_argument('--email', '-e', action='store_true',
      help='Send the report by email.\n\n')
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
  tests = []
  for item in items:
    name = item['test']
    if (name in ['angle_end2end_tests', 'gl_tests', 'vulkan_tests',
                 'dawn_end2end_tests', 'dawn_end2end_wire_tests',
                 'dawn_end2end_validation_layers_tests']):
      test = Test(name)
      test.args = item['args']
      if 'swarming' in item and 'shards' in item['swarming']:
        test.shards = item['swarming']['shards']
      tests.append(test)
  return tests


def find_isolated_scripts(items):
  tests = []
  for item in items:
    name = item['name']
    if (name.startswith('webgl') or name.startswith('webgpu')
        or name in ['angle_perftests', 'dawn_perf_tests']):
      name = name.replace('perftests', 'perf_tests')
      test = Test(name)
      for arg in item['args']:
        if arg.startswith('--extra-browser-args='):
          for browser_arg in arg[len('--extra-browser-args='):].split(' '):
            if not browser_arg.startswith('--enable-logging') and not browser_arg.startswith('--js-flags'):
              test.browser_args.append(browser_arg)
        elif arg.startswith('--browser='):
          pass
        else:
          test.args.append(arg)
      if 'swarming' in item and 'shards' in item['swarming']:
        test.shards = item['swarming']['shards']
      tests.append(test)
  return tests


def find_intel_tryjob(bot_file):
  tryjobs = []
  bot_dict = read_json(bot_file)
  for key,value in bot_dict.items():
    name = key.lower()
    if (name.find('intel') >= 0 and name.find('mac') < 0 and
        name.find('ozone') < 0 and name.find('deqp') < 0 and
        name.find('angle') < 0 and name.find('skiarenderer') < 0):
      match = re_match(r'^(.*) \((.*)\)$', name)
      if match:
        name = match.group(1)
        if name.find('linux') >= 0:
          name = name.replace('linux ', '')
          platform = 'linux'
        elif name.find('win10') >= 0:
          name = name.replace('win10 ', '')
          platform = 'win'

        name = name.replace('experimental', 'exp')
        name = name.replace('x64 ', '')
        name = name.replace('release', 'rel')
        name = name.replace(' ', '-')
        job = TryJob(name)
        job.platform = platform
        job.gpu = match.group(2).replace(' ', '-')
        if 'gtest_tests' in value:
          job.tests += find_gtest_tests(value['gtest_tests'])
        if 'isolated_scripts' in value:
          job.tests += find_isolated_scripts(value['isolated_scripts'])
        tryjobs.append(job)
  return tryjobs


def main():
  args = parse_arguments()
  config = read_json(TRYJOB_CONFIG)

  def handle_error(error):
    print(error)
    if args.email:
      send_email(config['receiver']['admin'], error)

  tryjobs = []
  for bot_file in OFFICIAL_TRYJOB_CONFIG:
    tryjobs += find_intel_tryjob(path.join(args.src_dir, bot_file))
  if not tryjobs:
    handle_error('Failed to find intel try bot')

  win_tests = {}
  linux_tests = {}
  for job in tryjobs:
    for test in job.tests:
      if job.platform == 'win':
        if test.name not in win_tests:
          win_tests[test.name] = test
      elif job.platform == 'linux':
        if test.name not in linux_tests:
          linux_tests[test.name] = test

      if test.browser_args:
        name = test.name.replace('webgl2', 'webgl')
        name = name.replace('_tests', '')
        name = name.replace('_passthrough', '')
        name = name.replace('conformance_', '')
        name = name.replace('_conformance', '_d3d11')
        if name in config['tryjob_args']:
          test.browser_args.sort()
          config['tryjob_args'][name].sort()
          if test.browser_args != config['tryjob_args'][name]:
            handle_error('Tryjob arguments mismatched: ' + test.name)
        else:
          handle_error('Missing try job arguments: ' + name)

  for test_name, platform, _, _ in config['tryjob']:
    pos = test_name.find('(')
    if pos > 0:
      test_name = test_name[0:pos]
    if 'win' in platform and test_name in win_tests:
      win_tests.pop(test_name)
    if 'linux' in platform and test_name in linux_tests:
      linux_tests.pop(test_name)

  if win_tests:
    handle_error('Missing try job on Windows: ' + ', '.join(win_tests.keys()))
  if linux_tests:
    handle_error('Missing try job on Linux: ' + ', '.join(linux_tests.keys()))

  return 0


if __name__ == '__main__':
  sys.exit(main())
