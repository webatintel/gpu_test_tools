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
  parser = argparse.ArgumentParser(
      description='Run tryjobs. The tryjob configuration is in "tryjob.json" under source directory.\n'\
                  'Once the tests are finished, the statistics are saved in "tryjob_report.txt".\n\n',
      formatter_class=argparse.RawTextHelpFormatter)
  parser.add_argument('--job', '-j', nargs='*',
      choices=['webgl', 'webgpu', 'dawn', 'angle', 'gpu', 'aquarium'],
      default=['webgl', 'webgpu', 'dawn', 'angle', 'gpu'],
      help='The tryjobs to run, you can specify multiple. Default is all except aquarium.\n'\
           'webgl    :  WebGL conformance tests\n'\
           'webgpu   :  WebGPU conformance tests\n'\
           'dawn     :  Dawn tests\n'\
           'angle    :  ANGLE tests\n'\
           'gpu      :  GPU unit tests\n'\
           'aquarium :  Aquarium performance tests\n\n')
  parser.add_argument('--test-filter', '-f', nargs='*',
      help='Filter the tests that contains the keyword, you can specify multiple.\n\n')
  parser.add_argument('--result-dir', '-d',
      help='Where to run test and to save the result.\n'\
           'If not specified, it will create a directory with timestamp under the tryjob/ subdirectory of this repository\n\n')
  parser.add_argument('--chrome-dir',
      help='Chrome source directory.\n\n')
  parser.add_argument('--dawn-dir',
      help='Dawn source directory.\n\n')
  parser.add_argument('--angle-dir',
      help='ANGLE source directory.\n\n')
  parser.add_argument('--aquarium-dir',
      help='Aquarium source directory.\n\n')
  parser.add_argument('--target', '-t', default='Default',
      help='The target build directory under out/. Default is "Default".\n\n')
  parser.add_argument('--build', '-b', action='store_true',
      help='Rebuild all targets before running tests.\n\n')
  parser.add_argument('--update', '-u', action='store_true',
      help='Fetch from origin and rebase current branch, then synchronize the dependencies before building.\n'\
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
  config = read_json(TRYJOB_CONFIG)
  args.tryjob = []
  for tags in config['tryjob']:
    if get_osname() not in tags:
      continue
    if args.job and tags[1].replace('webgl2', 'webgl') not in args.job:
      continue
    if args.test_filter:
      matched = False
      for keyword in args.test_filter:
        if keyword in tags[0]:
          matched = True
          break
      if not matched:
        continue
    print(tags[0])
    args.tryjob.append((tags[1], tags[2]))

  args.tryjob_shards = config['tryjob_shards']
  args.receiver = config['receiver']
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
      bias = int(float(value - reference_value) * 100 / reference_value)
      lines[i] += ' (%s%d%%)' % ('+' if bias >= 0 else '', bias)
      if abs(bias) > abs(max_bias):
        max_bias = bias

  if max_bias:
    notice = '[Max Bias:%s%d%%]' % ('+' if max_bias >= 0 else '', max_bias)
  else:
    notice = '[No Bias]'
  title = 'Aquarium Report - %s / %s - %s' % (get_osname().title(), get_hostname(), notice)
  return title, '\n'.join(lines)


def build_project(args, project, build_dir):
  build_cmd = [path.join(BIN_DIR, 'build_project'), project, '--target', args.target, '--dir', build_dir]
  if args.update:
    build_cmd.append('--update')
  execute_command(build_cmd, return_log=True)


def notify_command_error(receiver, error):
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
      if args.email:
        notify_command_error(args.receiver['admin'], e)
      raise e

    try:
      if args.aquarium_dir:
        build_project(args, 'aquarium', args.aquarium_dir)
    except CalledProcessError as e:
      if args.email:
        notify_command_error(args.receiver['aquarium'], e)
      aquarium_build_failed = True

  # Run tests
  mkdir(args.result_dir)
  for test_type, backend in args.tryjob:
    if test_type == 'aquarium' and aquarium_build_failed:
      continue

    try:
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
      execute_command(cmd, return_log=True, dir=args.result_dir)
    except CalledProcessError as e:
      if args.email:
        notify_command_error(args.receiver['admin'], e)

  # Parse result
  header = 'Location: %s\n' % os.getcwd()
  gpu, driver = get_gpu_info()
  if gpu:
    header += 'GPU: %s\n' % gpu
  if driver:
    header += 'Driver: %s\n' % driver

  try:
    job_set = set([test_type.replace('webgl2', 'webgl') for test_type, backend in args.tryjob])
    if 'aquarium' in job_set:
      job_set.remove('aquarium')
      report = execute_command([path.join(BIN_DIR, 'parse_result'), '--type', 'aquarium'],
                               return_log=True, dir=args.result_dir)
      if report:
        title, report = update_aquarium_report(args, report)
        report = '%s\n%s' % (header, report)
        write_file(AQUARIUM_REPORT, report)
        if args.email:
          send_email(args.receiver['aquarium'], title, report)
    
    if job_set:
      report = execute_command([path.join(BIN_DIR, 'parse_result'), '--type'] + list(job_set),
                               return_log=True, dir=args.result_dir)
      if report:
        title, report = update_tryjob_report(args, report)
        if args.chrome_dir:
          revision = get_chrome_revision(args.chrome_dir)
          if revision:
            header += 'Chrome: %s\n' % revision
        report = '%s\n%s' % (header, report)
        write_file(TRYJOB_REPORT, report)
        if args.email:
          send_email(args.receiver['tryjob'], title, report)
  except CalledProcessError as e:
    if args.email:
      notify_command_error(args.receiver['admin'], e)

  print('\nTest result     : ' + args.result_dir)
  if path.exists(path.join(args.result_dir, AQUARIUM_REPORT)):
    print('Aquarium report : ' + path.join(args.result_dir, AQUARIUM_REPORT))
  if path.exists(path.join(args.result_dir, TRYJOB_REPORT)):
    print('Tryjob report   : ' + path.join(args.result_dir, TRYJOB_REPORT))
  return 0


if __name__ == '__main__':
  sys.exit(main())
