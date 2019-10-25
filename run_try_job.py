#!/usr/bin/env python

import argparse
import sys

from util.gpu_test_util import *
from os import path

TRY_JOB_CONFIG = path.join(path.dirname(path.abspath(__file__)), 'try_job.json')
AQUARIUM_HISTORY_FILE = 'aquarium_history.json'

def parse_arguments():
  parser = argparse.ArgumentParser(
      description='Run try jobs\n'\
                  'The test configuration is defined in try_job.json.\n\n',
      formatter_class=argparse.RawTextHelpFormatter)
  parser.add_argument('--build', '-b',
      choices=['release', 'debug', 'default'], default='release',
      help='Build type. Default is \'release\'.\n'\
           'release/debug/default assume that the binaries are\n'\
           'generated into out/Release or out/Debug or out/Default.\n\n')
  parser.add_argument('--chrome-dir', '-c',
      help='Chrome source directory.\n\n')
  parser.add_argument('--aquarium-dir', '-a',
      help='Aquarium source directory.\n\n')
  parser.add_argument('--sync', '-s', action='store_true',
      help='Fetch latest source code and rebuild before running tests.\n\n')
  parser.add_argument('--email', '-e', action='store_true',
      help='Send the report by email.\n\n')
  args = parser.parse_args()

  if args.chrome_dir:
    args.chrome_dir = path.abspath(args.chrome_dir)
    if path.exists(path.join(args.chrome_dir, 'src')):
      args.chrome_dir = path.join(args.chrome_dir, 'src')

  if args.aquarium_dir:
    args.aquarium_dir = path.abspath(args.aquarium_dir)

  # Load configuration
  config = read_json(TRY_JOB_CONFIG)
  args.report_receivers = config['report_receivers']

  if is_win():
    args.try_jobs = config['win_jobs']
  elif is_linux():
    args.try_jobs = config['linux_jobs']
  elif is_mac():
    args.try_jobs = config['mac_jobs']

  args.try_job_args = config['try_job_args']
  args.try_job_shards = config['try_job_shards']

  return args


def notify_command_error(receivers, error):
  send_email(receivers,
             '%s failed on %s' % (error.cmd[0], get_hostname()),
             '%s\n\n%s' % (' '.join(error.cmd), error.output))


def update_aquarium_report(args, report):
  current_data = {}
  previous_data = read_json(path.join(os.getcwd(), '..', AQUARIUM_HISTORY_FILE))
  max_bias = 0
  lines = report.splitlines()
  for i in range(0, len(lines)):
    match = re_match(r'^aquarium_(.+)_test\s+(\d+)$', lines[i])
    if match:
      key = match.group(1)
      value = int(match.group(2))
      current_data[key] = value
      if previous_data.has_key(key):
        bias = value - previous_data[key]
        if abs(bias) > abs(max_bias):
          max_bias = bias
        lines[i] = 'aquarium_%s_test    %d -> %d' % (key, previous_data[key], value)

  if current_data:
    write_json(path.join(os.getcwd(), '..', AQUARIUM_HISTORY_FILE), current_data)

  if max_bias:
    notice = ' [Max Bias:%d]' % max_bias
  else:
    notice = ' No Bias'
  title = 'Aquarium Test Report - %s / %s -%s' % (get_osname().title(), get_hostname(), notice)

  header = 'Location: %s\n' % os.getcwd()
  if args.aquarium_revision:
    header += 'Revision: %s\n' % args.aquarium_revision
  return title, header + '\n'.join(lines)


def update_test_report(args, target, report):
  flaky_pass = 0
  new_pass = 0
  new_fail = 0
  for line in report.splitlines():
    match = re_match(r'^.*\[Falky Pass:(\d+)\].*$', line)
    if match:
      flaky_pass += int(match.group(1))
    match = re_match(r'^.*\[New Pass:(\d+)\].*$', line)
    if match:
      new_pass += int(match.group(1))
    match = re_match(r'^.*\[New Fail:(\d+)\].*$', line)
    if match:
      new_fail += int(match.group(1))

  notice = ''
  if new_fail:
    notice += ' [New Fail:%d]' % new_fail
  if new_pass and target == 'webgl':
    notice += ' [New Pass:%d]' % new_pass
  if flaky_pass and target == 'webgl':
    notice += ' [Flaky Pass:%d]' % flaky_pass
  if not notice:
    notice = ' All Clear'

  if target == 'webgl':
    target = 'WebGL'
  elif target == 'angle':
    target = 'ANGLE'
  title = '%s Test Report - %s / %s -%s' % (target, get_osname().title(), get_hostname(), notice)

  header = 'Location: %s\n' % os.getcwd()
  if args.chrome_revision:
    header += 'Revision: %s\n' % args.chrome_revision
  return title, header + report


def main():
  args = parse_arguments()

  # Update Chrome
  if args.chrome_dir:
    if args.sync:
      try:
        execute_command(['build_chrome', 'sync', 'build', '--build', args.build, '--dir', args.chrome_dir],
                        return_log=True)
      except CalledProcessError as e:
        notify_command_error(args.report_receivers['admin'], e)
        raise e

    args.chrome_revision = execute_command(['build_chrome', 'rev', '--dir', args.chrome_dir],
                                           print_log=False, return_log=True)

  # Update Aquarium
  if args.aquarium_dir:
    if args.sync:
      try:
        execute_command(['build_aquarium', 'sync', 'build', '--build', args.build, '--dir', args.aquarium_dir],
                        return_log=True)
      except CalledProcessError as e:
        notify_command_error(args.report_receivers['aquarium'], e)

    args.aquarium_revision = execute_command(['build_aquarium', 'rev', '--dir', args.aquarium_dir],
                                             print_log=False, return_log=True)

  # Run tests
  target_set = set()
  for job in args.try_jobs:
    target = args.try_job_args[job][0]
    backend = args.try_job_args[job][1]
    shard = 1
    for key in ['%s_%s' % (target, backend), target]:
      if args.try_job_shards.has_key(key):
        shard = args.try_job_shards[key]
        break

    cmd = ['run_gpu_test', target, '--build', args.build]
    if backend:
      cmd.extend(['--backend', backend])
    if shard > 1:
      cmd.extend(['--shard', str(shard)])
    if target == 'aquarium':
      assert args.aquarium_dir
      cmd.extend(['--dir', args.aquarium_dir])
    else:
      assert args.chrome_dir
      cmd.extend(['--dir', args.chrome_dir])

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
      report = execute_command(['parse_result', target], print_log=False, return_log=True)
      if report:
        if target == 'aquarium':
          title, report = update_aquarium_report(args, report)
        else:
          title, report = update_test_report(args, target, report)
        print('\n--------------------------------------------------\n' + report)
        write_file('%s_test_report.txt' % target, report)
        if args.email:
          send_email(args.report_receivers[target], title, report)
    except CalledProcessError as e:
      notify_command_error(args.report_receivers['admin'], e)

  return 0


if __name__ == '__main__':
  sys.exit(main())
