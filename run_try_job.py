#!/usr/bin/env python

import argparse
import sys

from util.base_util import *
from util.project_util import *
from os import path

FILE_DIR = path.dirname(path.abspath(__file__))
BIN_DIR= path.join(FILE_DIR, 'bin')
TRY_JOB_CONFIG = path.join(FILE_DIR, 'try_job.json')

PATTERN_AQUARIUM_TEST = r'^aquarium_(.+)_test\s+(\d+)$'
PATTERN_FLAKY_PASS = r'^.*\[Flaky Pass:(\d+)\].*$'
PATTERN_NEW_PASS = r'^.*\[New Pass:(\d+)\].*$'
PATTERN_NEW_FAIL = r'^.*\[New Fail:(\d+)\].*$'

def parse_arguments():
  parser = argparse.ArgumentParser(
      description='Run try jobs. The test configuration is defined in try_job.json.\n'\
                  'Once the tests are finished, the results are saved in xx_test_report.txt.\n\n',
      formatter_class=argparse.RawTextHelpFormatter)
  parser.add_argument('jobs', nargs='*',
      choices=['all', 'webgl', 'angle', 'dawn', 'aquarium', 'gtest'], default='',
      help='Specify the try jobs you want to run, it could be multiple.\n'\
           'If no job is specified, the jobs defined in try_job.json will be run.\n'\
           'all      :  All tests\n'\
           'webgl    :  WebGL-related tests\n'\
           'angle    :  ANGLE-related tests\n'\
           'dawn     :  Dawn-related tests\n'\
           'gtest    :  Other gtest-related tests (gl_tests and vulkan_tests)\n'\
           'aquarium :  All Aquarium tests\n\n')
  parser.add_argument('--type', '-t',
      choices=['default', 'release', 'debug'], default='default',
      help='Browser type. Default is \'default\', which gn args are same as official bot.\n'\
           'default/release/debug assume that the binaries are\n'\
           'generated into out/Default or out/Release or out/Debug.\n\n')
  parser.add_argument('--chrome-dir', '-c',
      help='Chrome source directory.\n\n')
  parser.add_argument('--aquarium-dir', '-a',
      help='Aquarium source directory.\n\n')
  parser.add_argument('--build', '-b', action='store_true',
      help='Rebuild all targets before running tests.\n\n')
  parser.add_argument('--update', '-u', action='store_true',
      help='Fetch from origin and rebase current branch, then synchronize the dependencies before building.\n'\
           '--build will be enabled automatically.\n\n')
  parser.add_argument('--email', '-e', action='store_true',
      help='Send the report by email.\n\n')
  args = parser.parse_args()

  if 'all' in args.jobs and len(args.jobs) > 1:
    raise Exception('Invalid job list: ' + ' '.join(args.jobs))

  if args.chrome_dir:
    args.chrome_dir = path.abspath(args.chrome_dir)
    if path.exists(path.join(args.chrome_dir, 'src')):
      args.chrome_dir = path.join(args.chrome_dir, 'src')

  if args.aquarium_dir:
    args.aquarium_dir = path.abspath(args.aquarium_dir)

  # Load configuration
  config = read_json(TRY_JOB_CONFIG)
  args.try_jobs = []
  if args.jobs == ['all']:
    args.jobs = ['aquarium', 'dawn', 'angle', 'gtest', 'webgl']
  for job in args.jobs:
    key = job + '_jobs'
    if isinstance(config[key], list):
      args.try_jobs.extend(config[key])
    elif is_win():
      args.try_jobs.extend(config[key]['win'])
    elif is_linux():
      args.try_jobs.extend(config[key]['linux'])

  args.try_job_target = config['try_job_target']
  args.try_job_shards = config['try_job_shards']

  args.report_receivers = config['report_receivers']
  args.aquarium_average_fps = config['aquarium_average_fps']

  return args


def update_aquarium_report(args, report):
  max_bias = 0
  lines = report.splitlines()
  for i in range(0, len(lines)):
    match = re_match(PATTERN_AQUARIUM_TEST, lines[i])
    if match:
      key, value = match.group(1), int(match.group(2))
      reference_value = args.aquarium_average_fps[get_osname()][key]
      bias = int(float(value - reference_value) * 100 / reference_value)
      lines[i] += ' (%s%d%%)' % ('+' if bias >= 0 else '', bias)
      if abs(bias) > abs(max_bias):
        max_bias = bias

  if max_bias:
    notice = '[Max Bias:%s%d%%]' % ('+' if max_bias >= 0 else '', max_bias)
  else:
    notice = '[No Bias]'
  title = 'Aquarium Test Report - %s / %s - %s' % (get_osname().title(), get_hostname(), notice)

  header = 'Location: %s\n' % os.getcwd()
  if args.aquarium_revision:
    header += 'Revision: %s\n' % args.aquarium_revision
  return title, '%s\n%s' % (header, report)


def update_test_report(args, target, report):
  flaky_pass = 0
  new_pass = 0
  new_fail = 0
  for line in report.splitlines():
    match = re_match(PATTERN_FLAKY_PASS, line)
    if match:
      flaky_pass += int(match.group(1))
    match = re_match(PATTERN_NEW_PASS, line)
    if match:
      new_pass += int(match.group(1))
    match = re_match(PATTERN_NEW_FAIL, line)
    if match:
      new_fail += int(match.group(1))

  notice = ''
  if new_fail:
    notice += ' [New Fail:%d]' % new_fail
  if new_pass:
    notice += ' [New Pass:%d]' % new_pass
  if flaky_pass:
    notice += ' [Flaky Pass:%d]' % flaky_pass
  if not notice:
    notice = ' [All Clear]'

  if target == 'webgl':
    title = 'WebGL Test'
  elif target == 'gtest':
    title = 'GTest'
  title += ' Report - %s / %s -%s' % (get_osname().title(), get_hostname(), notice)

  header = 'Location: %s\n' % os.getcwd()
  if args.chrome_revision:
    header += 'Revision: %s\n' % args.chrome_revision
  gpu, driver_version = get_gpu_info()
  if gpu:
    header += 'GPU: %s\n' % gpu
  if driver_version:
    header += 'Driver: %s\n' % driver_version
  return title, '%s\n%s' % (header, report)


def notify_command_error(receivers, error):
  send_email(receivers,
             '%s %s failed on %s' % (error.cmd[0], error.cmd[1], get_hostname()),
             '%s\n\n%s' % (' '.join(error.cmd), error.output))


def main():
  args = parse_arguments()
  aquarium_build_failed = False

  if args.chrome_dir:
    if args.build or args.update:
      build_cmd = [path.join(BIN_DIR, 'build_project'), 'chrome',
                   '--type', args.type, '--dir', args.chrome_dir]
      if args.update:
        build_cmd.append('--update')

      try:
        execute_command(build_cmd, return_log=True)
      except CalledProcessError as e:
        notify_command_error(args.report_receivers['admin'], e)
        raise e

    args.chrome_revision = get_chrome_revision(args.chrome_dir)

  if args.aquarium_dir:
    if args.build or args.update:
      build_cmd = [path.join(BIN_DIR, 'build_project'), 'aquarium',
                   '--type', args.type, '--dir', args.aquarium_dir]
      if args.update:
        build_cmd.append('--update')

      try:
        execute_command(build_cmd, return_log=True)
      except CalledProcessError as e:
        notify_command_error(args.report_receivers['aquarium'], e)
        aquarium_build_failed = True

    args.aquarium_revision = get_aquarium_revision(args.aquarium_dir)

  # Run tests
  target_set = set()
  for job in args.try_jobs:
    target = args.try_job_target[job][0]
    backend = args.try_job_target[job][1]
    if target == 'aquarium' and aquarium_build_failed:
      continue

    cmd = [path.join(BIN_DIR, 'run_gpu_test'), target, '--backend', backend, '--type', args.type]
    if target == 'aquarium':
      assert args.aquarium_dir
      cmd.extend(['--dir', args.aquarium_dir])
    else:
      assert args.chrome_dir
      cmd.extend(['--dir', args.chrome_dir])

    for key in ['%s_%s' % (target, backend), target]:
      if args.try_job_shards.has_key(key):
        cmd.extend(['--shard', str(args.try_job_shards[key])])
        break

    try:
      execute_command(cmd, return_log=True)
      if target.startswith('webgl'):
        target_set.add('webgl')
      else:
        target_set.add(target)
    except CalledProcessError as e:
      notify_command_error(args.report_receivers['admin'], e)

  # Dump test results
  for target in target_set:
    try:
      report = execute_command([path.join(BIN_DIR, 'parse_result'), target],
                               print_log=False, return_log=True)
      if report:
        if target == 'aquarium':
          title, report = update_aquarium_report(args, report)
        else:
          title, report = update_test_report(args, target, report)
        print('\n--------------------------------------------------\n\n%s\n\n%s' % (title, report))
        write_file(target + '_report.txt', report)
        if args.email:
          send_email(args.report_receivers[target], title, report)
    except CalledProcessError as e:
      notify_command_error(args.report_receivers['admin'], e)

  return 0


if __name__ == '__main__':
  sys.exit(main())
