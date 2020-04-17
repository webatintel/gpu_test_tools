#!/usr/bin/env python

import argparse
import sys

from util.base_util import *
from os import path

OFFICIAL_TRY_BOTS = [ path.join('testing', 'buildbot', 'chromium.gpu.json'),
                      path.join('testing', 'buildbot', 'chromium.gpu.fyi.json') ]
TRY_JOB_CONFIG = path.join(path.dirname(path.abspath(__file__)), 'try_job.json')

def parse_arguments():
  parser = argparse.ArgumentParser(
      description='Find try bot configurations',
      formatter_class=argparse.RawTextHelpFormatter)
  parser.add_argument('--dir', '-d', default='.',
      help='The Chromium source directory.\n\n')
  parser.add_argument('--email', '-e', action='store_true',
      help='Send the report by email.\n\n')
  args = parser.parse_args()

  args.dir = path.abspath(args.dir)
  if path.exists(path.join(args.dir, 'src')):
    args.dir = path.join(args.dir, 'src')
  return args


class TryJob(object):
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


class TryBot(object):
  def __init__(self, name):
    self.name = name
    self.platform = None
    self.gpu = None
    self.try_jobs = []


def find_gtest_tests(test_list):
  job_list = []
  for test in test_list:
    name = test['test']
    if name in ['angle_end2end_tests', 'gl_tests', 'vulkan_tests']:
      job = TryJob(name)
      job.args = test['args']
      if test.has_key('swarming') and test['swarming'].has_key('shards'):
        job.shards = test['swarming']['shards']
      job_list.append(job)
  return job_list


def find_telemetry_tests(test_list):
  job_list = []
  for test in test_list:
    name = test['name']
    if name.startswith('webgl') or name == 'angle_perftests':
      name = name.replace('perftests', 'perf_tests')
      job = TryJob(name)
      for arg in test['args']:
        if arg.startswith('--extra-browser-args='):
          for browser_arg in arg[len('--extra-browser-args='):].split(' '):
            if not browser_arg.startswith('--enable-logging') and not browser_arg.startswith('--js-flags'):
              job.browser_args.append(browser_arg)
        elif arg.startswith('--browser='):
          pass
        else:
          job.args.append(arg)
      if test.has_key('swarming') and test['swarming'].has_key('shards'):
        job.shards = test['swarming']['shards']
      job_list.append(job)
  return job_list


def find_intel_bot(bot_file):
  bot_list = []
  bot_dict = read_json(bot_file)
  for key,value in bot_dict.iteritems():
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
        else:
          raise Exception('Invalid platform: ' + name)

        name = name.replace('experimental', 'exp')
        name = name.replace('x64 ', '')
        name = name.replace('release', 'rel')
        name = name.replace(' ', '-')
        bot = TryBot(name)
        bot.platform = platform
        bot.gpu = match.group(2).replace(' ', '-')
        if value.has_key('gtest_tests'):
          bot.try_jobs.extend(find_gtest_tests(value['gtest_tests']))
        if value.has_key('isolated_scripts'):
          bot.try_jobs.extend(find_telemetry_tests(value['isolated_scripts']))
        bot_list.append(bot)
  return bot_list


def main():
  args = parse_arguments()
  config = read_json(TRY_JOB_CONFIG)

  def handle_error(error):
    print(error)
    if args.email:
      send_email(config['report_receivers']['admin'], error)

  bot_list = []
  for try_bot in OFFICIAL_TRY_BOTS:
    bot_list.extend(find_intel_bot(os.path.join(args.dir, try_bot)))
  if not bot_list:
    handle_error('Failed to find intel try bot')

  win_jobs = {}
  linux_jobs = {}
  for bot in bot_list:
    for job in bot.try_jobs:
      if bot.platform == 'win':
        if not win_jobs.has_key(job.name):
          win_jobs[job.name] = job
      elif bot.platform == 'linux':
        if not linux_jobs.has_key(job.name):
          linux_jobs[job.name] = job

      if job.browser_args:
        name = job.name.replace('webgl2', 'webgl')
        name = name.replace('_tests', '')
        name = name.replace('_passthrough', '')
        name = name.replace('conformance_', '')
        name = name.replace('_conformance', '_d3d11')
        if config['try_job_browser_args'].has_key(name):
          job.browser_args.sort()
          config['try_job_browser_args'][name].sort()
          if job.browser_args != config['try_job_browser_args'][name]:
            handle_error('Try job arguments mismatched: ' + job.name)
        else:
          handle_error('Missing try job arguments: ' + name)

  for key, value in win_jobs.items():
    if not key in config['win_jobs']:
      handle_error('Missing try job on Windows: ' + key)

  for key, value in linux_jobs.items():
    if not key in config['linux_jobs']:
      handle_error('Missing try job on Linux: ' + key)

  return 0


if __name__ == '__main__':
  sys.exit(main())
