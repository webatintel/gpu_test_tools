#!/usr/bin/env python

import argparse
import sys

from util.base_util import *
from util.file_util import *
from util.system_util import *
from os import path

FILE_DIR = path.dirname(path.abspath(__file__))
BIN_DIR= path.join(FILE_DIR, 'bin')
TRYJOB_DIR = path.join(FILE_DIR, 'tryjob')
TRYJOB_CONFIG = path.join(FILE_DIR, 'tryjob.json')

TRYJOB_REPORT = 'tryjob_report.txt'
AQUARIUM_REPORT = 'aquarium_report.txt'

PATTERN_AQUARIUM_TEST = r'^aquarium_(\w+)\s+(\d+)$'
PATTERN_FLAKY_PASS = r'^.*\[Flaky Pass:(\d+)\].*$'
PATTERN_NEW_PASS = r'^.*\[New Pass:(\d+)\].*$'
PATTERN_NEW_FAIL = r'^.*\[New Fail:(\d+)\].*$'

def parse_arguments():
  config = read_json(TRYJOB_CONFIG)
  job_choice = set()
  for _, platform, _, job_type in config['tryjob']:
    if get_osname() in platform:
      job_choice |= set(job_type)

  parser = argparse.ArgumentParser(
      description='Run selected tests with your local build.\n'\
                  'Once the tests are finished, the statistics are output to the screen and the file "tryjob_report.txt".\n'\
                  'The tryjob configuration is in "tryjob.json".\n\n',
      formatter_class=argparse.RawTextHelpFormatter)
  parser.add_argument('--job-type', '--job', '-j', nargs='+', choices=list(job_choice), required=True,
      help='You can select one or more job types from the candidates.\n\n')
  parser.add_argument('--test-filter', '-f', nargs='+',
      help='You can specify one or more keywords (the logic is OR), the test that contains the keyword will be run.\n\n')
  parser.add_argument('--result-dir', '-r',
      help='Where to hold test logs and test results. The final report "tryjob_report.txt" is generated here as well.\n'\
           'If not specified, the test will create a directory with timestamp YEAR_DATE_TIME under the tryjob/ subdirectory of this repository\n\n')
  parser.add_argument('--chrome-dir', '-c',
      help='Chrome source directory.\n\n')
  parser.add_argument('--dawn-dir', '-d',
      help='Dawn source directory.\n\n')
  parser.add_argument('--angle-dir', '-a',
      help='ANGLE source directory.\n\n')
  parser.add_argument('--aquarium-dir',
      help='Aquarium source directory.\n\n')
  parser.add_argument('--target', '-t', default='Default',
      help='The target build directory under "out/". Default is "Default".\n\n')
  parser.add_argument('--build', '-b', action='store_true',
      help='Rebuild all targets before running tests.\n\n')
  parser.add_argument('--update', '-u', action='store_true',
      help='Fetch from origin and rebase to master, then synchronize the dependencies before building.\n'\
           '--build will be enabled automatically.\n\n')
  parser.add_argument('--email', '-e', action='store_true',
      help='Send the report by email.\n\n')
  parser.add_argument('--dry-run', action='store_true',
      help='Go through the process but do not run tests actually.\n\n')
  args = parser.parse_args()

  if args.result_dir:
    args.result_dir = path.abspath(args.result_dir)
  else:
    args.result_dir = path.join(TRYJOB_DIR, get_currenttime('%Y_%m%d_%H%M'))

  if args.chrome_dir:
    args.chrome_dir = path.abspath(args.chrome_dir)
    if path.basename(args.chrome_dir) == 'chromium' and path.exists(path.join(args.chrome_dir, 'src')):
      args.chrome_dir = path.join(args.chrome_dir, 'src')
  if args.dawn_dir:
    args.dawn_dir = path.abspath(args.dawn_dir)
  if args.angle_dir:
    args.angle_dir = path.abspath(args.angle_dir)
  if args.aquarium_dir:
    args.aquarium_dir = path.abspath(args.aquarium_dir)

  print('\nTests to run:')
  args.tryjob = []
  for test_name, platform, test_arg, job_type in config['tryjob']:
    if get_osname() not in platform:
      continue
    if args.job_type and not (set(args.job_type) & set(job_type)):
      continue
    if args.test_filter:
      matched = False
      for keyword in args.test_filter:
        if keyword in test_name:
          matched = True
          break
      if not matched:
        continue
    print(test_name)
    args.tryjob.append(test_arg)

  args.tryjob_shards = config['tryjob_shards']
  args.receiver_admin = config['email']['receiver']['admin']
  args.receiver_tryjob = config['email']['receiver']['tryjob']
  args.receiver_aquarium = config['email']['receiver']['aquarium']
  args.aquarium_average_fps = config['aquarium_average_fps']

  return args


def update_tryjob_report(args, report):
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

  title = 'Tryjob Report - %s / %s -%s' % (get_osname().title(), get_hostname(), notice)
  return title, report


def update_aquarium_report(args, report):
  max_bias = 0
  lines = report.splitlines()
  for i in range(0, len(lines)):
    match = re_match(PATTERN_AQUARIUM_TEST, lines[i])
    if match:
      key, value = match.group(1), int(match.group(2))
      reference_value = args.aquarium_average_fps[get_osname()][key]
      bias = (value - reference_value) * 100 // reference_value
      lines[i] += ' (%s%d%%)' % ('+' if bias >= 0 else '', bias)
      if abs(bias) > abs(max_bias):
        max_bias = bias

  if max_bias:
    notice = '[Max Bias:%s%d%%]' % ('+' if max_bias >= 0 else '', max_bias)
  else:
    notice = '[No Bias]'
  title = 'Aquarium Report - %s / %s - %s' % (get_osname().title(), get_hostname(), notice)
  return title, '\n'.join(lines)


def build_project(args, project, source_dir):
  build_cmd = [path.join(BIN_DIR, 'build_project'), project, '--target', args.target, '--dir', source_dir]
  if args.update:
    build_cmd.append('--update')
  try:
    execute_command_passthrough(build_cmd)
  except CalledProcessError:
    execute_command(build_cmd, return_log=True)


def notify_command_error(args, receiver, error):
  if not args.email:
    return
  send_email(receiver,
             '%s %s failed on %s' % (path.basename(error.cmd[0]), error.cmd[1], get_hostname()),
             '%s\n\n%s' % (' '.join(error.cmd), error.output))


def main():
  args = parse_arguments()

  # Build project
  aquarium_build_failed = False
  if args.build or args.update:
    try:
      if args.chrome_dir:
        build_project(args, 'chrome', args.chrome_dir)
      if args.dawn_dir:
        build_project(args, 'dawn', args.dawn_dir)
      if args.angle_dir:
        build_project(args, 'angle', args.angle_dir)
    except CalledProcessError as e:
      notify_command_error(args, args.receiver_admin, e)
      raise e

    try:
      if args.aquarium_dir:
        build_project(args, 'aquarium', args.aquarium_dir)
    except CalledProcessError as e:
      notify_command_error(args, args.receiver_aquarium, e)
      aquarium_build_failed = True

  # Run tests
  mkdir(args.result_dir)
  for test_type, backend in args.tryjob:
    if test_type == 'aquarium' and aquarium_build_failed:
      continue

    cmd = [path.join(BIN_DIR, 'run_gpu_test'), test_type, '--backend', backend, '--target', args.target]
    if test_type == 'aquarium':
      assert args.aquarium_dir
      cmd += ['--dir', args.aquarium_dir]
    elif test_type == 'angle' and args.angle_dir:
      cmd += ['--dir', args.angle_dir]
    elif test_type == 'dawn' and args.dawn_dir:
      cmd += ['--dir', args.dawn_dir]
    else:
      assert args.chrome_dir
      cmd += ['--dir', args.chrome_dir]

    for key in ['%s_%s' % (test_type, backend), test_type]:
      if key in args.tryjob_shards:
        cmd += ['--shard', str(args.tryjob_shards[key])]
        break
    if args.dry_run:
      cmd += ['--dry-run']

    try:
      execute_command(cmd, return_log=True, dir=args.result_dir)
    except CalledProcessError as e:
      notify_command_error(args, args.receiver_admin, e)

  # Parse result
  try:
    aquarium_report = execute_command([path.join(BIN_DIR, 'parse_result'), '--type', 'aquarium'],
                                      return_log=True, dir=args.result_dir)
    tryjob_report = execute_command([path.join(BIN_DIR, 'parse_result')],
                                    return_log=True, dir=args.result_dir)
  except CalledProcessError as e:
    notify_command_error(args, args.receiver_admin, e)

  header = 'Location: %s\n' % args.result_dir
  gpu, driver = get_gpu_info()
  if gpu:
    header += 'GPU: %s\n' % gpu
  if driver:
    header += 'Driver: %s\n' % driver

  if aquarium_report:
    title, aquarium_report = update_aquarium_report(args, aquarium_report)
    aquarium_report = '%s\n%s' % (header, aquarium_report)
    write_file(path.join(args.result_dir, AQUARIUM_REPORT), aquarium_report)
    if args.email:
      send_email(args.receiver_aquarium, title, aquarium_report)

  if tryjob_report:
    title, tryjob_report = update_tryjob_report(args, tryjob_report)
    if args.chrome_dir and not args.dry_run:
      revision = get_chrome_revision(args.chrome_dir)
      if revision:
        header += 'Chrome: %s\n' % revision
    tryjob_report = '%s\n%s' % (header, tryjob_report)
    write_file(path.join(args.result_dir, TRYJOB_REPORT), tryjob_report)
    if args.email:
      send_email(args.receiver_tryjob, title, tryjob_report)

  print('\nTest result     : ' + args.result_dir)
  if path.exists(path.join(args.result_dir, TRYJOB_REPORT)):
    print('Tryjob report   : ' + path.join(args.result_dir, TRYJOB_REPORT))
  if path.exists(path.join(args.result_dir, AQUARIUM_REPORT)):
    print('Aquarium report : ' + path.join(args.result_dir, AQUARIUM_REPORT))
  return 0


if __name__ == '__main__':
  sys.exit(main())
