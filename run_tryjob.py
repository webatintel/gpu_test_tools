#!/usr/bin/env python

import argparse
import sys

from util.base_util import *
from util.file_util import *
from util.system_util import *
from os import path

FILE_DIR = path.dirname(path.abspath(__file__))
BIN_DIR= path.join(FILE_DIR, 'bin')
TRYJOB_CONFIG = path.join(FILE_DIR, 'tryjob.json')

PATTERN_AQUARIUM_TEST = r'^aquarium_(.+)_test\s+(\d+)$'
PATTERN_FLAKY_PASS = r'^.*\[Flaky Pass:(\d+)\].*$'
PATTERN_NEW_PASS = r'^.*\[New Pass:(\d+)\].*$'
PATTERN_NEW_FAIL = r'^.*\[New Fail:(\d+)\].*$'

def parse_arguments():
  parser = argparse.ArgumentParser(
      description='Run try jobs. The test configuration is defined in tryjob.json.\n'\
                  'Once the tests are finished, the results are saved in xx_test_report.txt.\n\n',
      formatter_class=argparse.RawTextHelpFormatter)
  parser.add_argument('job', nargs='*',
      choices=['all', 'webgl', 'dawn', 'angle', 'gpu', 'aquarium'], default='all',
      help='Specify the try jobs you want to run, you can specify multiple jobs.\n'\
           'webgl    :  WebGL conformance tests\n'\
           'dawn     :  Dawn tests\n'\
           'angle    :  ANGLE tests\n'\
           'gpu      :  GPU unit tests\n'\
           'aquarium :  Aquarium tests\n\n')
  parser.add_argument('--type', '-t',
      choices=['default', 'release', 'debug'], default='default',
      help='Browser type. Default is \'default\', which gn args are same as official bot.\n'\
           'default/release/debug assume that the binaries are\n'\
           'generated into out/Default or out/Release or out/Debug.\n\n')
  parser.add_argument('--chrome-dir',
      help='Chrome source directory.\n\n')
  parser.add_argument('--dawn-dir',
      help='Dawn source directory.\n\n')
  parser.add_argument('--angle-dir',
      help='ANGLE source directory.\n\n')
  parser.add_argument('--aquarium-dir',
      help='Aquarium source directory.\n\n')
  parser.add_argument('--build', '-b', action='store_true',
      help='Rebuild all targets before running tests.\n\n')
  parser.add_argument('--update', '-u', action='store_true',
      help='Fetch from origin and rebase current branch, then synchronize the dependencies before building.\n'\
           '--build will be enabled automatically.\n\n')
  parser.add_argument('--email', '-e', action='store_true',
      help='Send the report by email.\n\n')
  args = parser.parse_args()

  if not isinstance(args.job, list):
    args.job = [args.job]
  if 'all' in args.job:
    if len(args.job) > 1:
      raise Exception('Invalid job list: ' + ' '.join(args.job))
    args.job = ['webgl', 'dawn', 'angle', 'gpu', 'aquarium']

  if args.chrome_dir:
    args.chrome_dir = path.abspath(args.chrome_dir)
    if path.exists(path.join(args.chrome_dir, 'src')):
      args.chrome_dir = path.join(args.chrome_dir, 'src')
  if args.dawn_dir:
    args.dawn_dir = path.abspath(args.dawn_dir)
  if args.angle_dir:
    args.angle_dir = path.abspath(args.angle_dir)
  if args.aquarium_dir:
    args.aquarium_dir = path.abspath(args.aquarium_dir)

  # Load configuration
  config = read_json(TRYJOB_CONFIG)
  args.tryjobs = []
  for job in args.job:
    for key,value in config['tryjob'].items():
      new_value = [item.replace('webgl2', 'webgl') for item in value]
      if job == new_value[0] and get_osname() in value:
        args.tryjobs.append((value[0], value[1]))

  args.tryjob_shards = config['tryjob_shards']
  args.receiver = config['receiver']
  args.aquarium_average_fps = config['aquarium_average_fps']

  return args


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

  title = 'GPU Test Report - %s / %s -%s' % (get_osname().title(), get_hostname(), notice)
  return title, report


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
  return title, report


def handle_command_error(args, error):
  if args.email:
    if 'build_project' in error.cmd[0] and error.cmd[1] == 'aquarium':
      receiver = args.receiver['aquarium']
    else:
      receiver = args.receiver['admin']
    send_email(receiver,
              '%s %s failed on %s' % (path.basename(error.cmd[0]), error.cmd[1], get_hostname()),
              '%s\n\n%s' % (' '.join(error.cmd), error.output))
  raise error


def build_project(project, args):
  if not args.build and not args.update:
    return

  build_cmd = [path.join(BIN_DIR, 'build_project'), project, '--type', args.type]
  if project == 'chrome':
    build_cmd.extend(['--dir', args.chrome_dir])
  elif project == 'angle':
    build_cmd.extend(['--dir', args.angle_dir])
  elif project == 'dawn':
    build_cmd.extend(['--dir', args.dawn_dir])

  if args.update:
    build_cmd.append('--update')

  try:
    execute_command(build_cmd, return_log=True)
  except CalledProcessError as e:
    handle_command_error(args, e)


def main():
  args = parse_arguments()

  if args.chrome_dir:
    build_project('chrome', args)
    args.chrome_revision = get_chrome_revision(args.chrome_dir)
  else:
    args.chrome_revision = None

  if args.dawn_dir:
    build_project('dawn', args)

  if args.angle_dir:
    build_project('angle', args)

  aquarium_build_failed = False
  if args.aquarium_dir:
    try:
      build_project('aquarium', args)
    except CalledProcessError:
      aquarium_build_failed = True

  # Run tests
  target_set = set()
  for job in args.tryjobs:
    target, backend = job
    if target == 'aquarium' and aquarium_build_failed:
      continue

    cmd = [path.join(BIN_DIR, 'run_gpu_test'), target, '--backend', backend, '--type', args.type]
    if target == 'aquarium':
      assert args.aquarium_dir
      cmd.extend(['--dir', args.aquarium_dir])
    elif target == 'angle' and args.angle_dir:
      cmd.extend(['--dir', args.angle_dir])
    elif target == 'dawn' and backend != 'blink' and args.dawn_dir:
      cmd.extend(['--dir', args.dawn_dir])
    else:
      assert args.chrome_dir
      cmd.extend(['--dir', args.chrome_dir])

    for key in ['%s_%s' % (target, backend), target]:
      if key in args.tryjob_shards:
        cmd.extend(['--shard', str(args.tryjob_shards[key])])
        break

    try:
      execute_command(cmd, return_log=True)
      target_set.add(target.replace('webgl2', 'webgl'))
    except CalledProcessError as e:
      handle_command_error(args, e)

  # Dump test results
  header = 'Location: %s\n' % os.getcwd()
  gpu, driver = get_gpu_info()
  if gpu:
    header += 'GPU: %s\n' % gpu
  if driver:
    header += 'Driver: %s\n' % driver

  if 'aquarium' in target_set:
    target_set.remove('aquarium')
    report = execute_command([path.join(BIN_DIR, 'parse_result'), 'aquarium'],
                              print_log=False, return_log=True)
    title, report = update_aquarium_report(args, report)
    report = '%s\n%s' % (header, report)
    print('\n--------------------------------------------------\n\n%s\n\n%s' % (title, report))
    write_file('aquarium_test_report.txt', report)
    if args.email:
      send_email(args.receiver['aquarium'], title, report)

  cmd = [path.join(BIN_DIR, 'parse_result')]
  cmd.extend(list(target_set))
  report = execute_command(cmd, print_log=False, return_log=True)
  title, report = update_test_report(args, target, report)
  if args.chrome_revision:
    header += 'Chrome: %s\n' % args.chrome_revision
  report = '%s\n%s' % (header, report)
  print('\n--------------------------------------------------\n\n%s\n\n%s' % (title, report))
  write_file('gpu_test_report.txt', report)
  if args.email:
    send_email(args.receiver['report'], title, report)

  return 0


if __name__ == '__main__':
  sys.exit(main())
