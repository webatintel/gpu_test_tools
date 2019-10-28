#!/usr/bin/env python

import argparse
import sys

from util.gpu_test_util import *
from os import path

TRY_JOB_CONFIG = path.join(path.dirname(path.abspath(__file__)), 'try_job.json')
AQUARIUM_HISTORY_FILE = 'aquarium_history.json'
MAX_AQUARIUM_HISTORY = 10

def parse_arguments():
  parser = argparse.ArgumentParser(
      description='Run try jobs\n'\
                  'The test configuration is defined in try_job.json.\n\n',
      formatter_class=argparse.RawTextHelpFormatter)
  parser.add_argument('--type', '-t',
      choices=['release', 'debug', 'default'], default='release',
      help='Browser type. Default is \'release\'.\n'\
           'release/debug/default assume that the binaries are\n'\
           'generated into out/Release or out/Debug or out/Default.\n\n')
  parser.add_argument('--chrome-dir', '-c',
      help='Chrome source directory.\n\n')
  parser.add_argument('--aquarium-dir', '-a',
      help='Aquarium source directory.\n\n')
  parser.add_argument('--build', '-b', action='store_true',
      help='Rebuild before running tests.\n\n')
  parser.add_argument('--sync', '-s', action='store_true',
      help='Fetch latest source code and rebuild before running tests.\n\n')
  parser.add_argument('--email', '-e', action='store_true',
      help='Send the report by email.\n\n')
  parser.add_argument('--iris', action='store_true',
      help='Enable Iris driver. (Only available on Ubuntu/Mesa environment)\n\n')
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
  history_file = path.join(os.getcwd(), '..', AQUARIUM_HISTORY_FILE)
  history_data = read_json(history_file)
  max_bias = 0
  lines = report.splitlines()
  for i in range(0, len(lines)):
    match = re_match(r'^aquarium_(.+)_test\s+(\d+)$', lines[i])
    if match:
      key, value = match.group(1), int(match.group(2))
      if history_data.has_key(key):
        baseline = sum(history_data[key]) / len(history_data[key])
        bias = int(float(value - baseline) * 100 / baseline)
        lines[i] += ' (%s%d%%)' % ('+' if bias >= 0 else '', bias)
        if abs(bias) > abs(max_bias):
          max_bias = bias
        history_data[key].append(value)
        while len(history_data[key]) > MAX_AQUARIUM_HISTORY:
          history_data[key].pop(0)
      else:
        history_data[key] = [value]

  if history_data:
    write_json(history_file, history_data)

  if max_bias:
    notice = ' [Max Bias:%s%d%%]' % ('+' if bias >= 0 else '', max_bias)
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
    if args.sync or args.build:
      build_cmd = ['build_chrome']
      if args.sync:
        build_cmd.extend(['sync', 'build'])
      elif args.build:
        build_cmd.extend(['build'])
      build_cmd.extend(['--type', args.type, '--dir', args.chrome_dir])
      try:
        execute_command(build_cmd, return_log=True)
      except CalledProcessError as e:
        notify_command_error(args.report_receivers['admin'], e)

    args.chrome_revision = execute_command(['build_chrome', 'rev', '--dir', args.chrome_dir],
                                           print_log=False, return_log=True)

  # Update Aquarium
  if args.aquarium_dir:
    if args.sync or args.build:
      build_cmd = ['build_aquarium']
      if args.sync:
        build_cmd.extend(['sync', 'build'])
      elif args.build:
        build_cmd.extend(['build'])
      build_cmd.extend(['--type', args.type, '--dir', args.aquarium_dir])
      try:
        execute_command(build_cmd, return_log=True)
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

    cmd = ['run_gpu_test', target, '--type', args.type]
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
    if target.startswith('webgl') and args.iris:
      cmd.append('--iris')

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
        print('\n--------------------------------------------------\n%s\n\n%s' % (title, report))
        write_file('%s_test_report.txt' % target, report)
        if args.email:
          send_email(args.report_receivers[target], title, report)
    except CalledProcessError as e:
      notify_command_error(args.report_receivers['admin'], e)

  return 0


if __name__ == '__main__':
  sys.exit(main())
