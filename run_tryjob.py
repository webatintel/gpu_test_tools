#!/usr/bin/env python3

import argparse

from util.base_util import *
from util.file_util import *

BIN_DIR    = path.join(REPOSITORY_DIR, 'bin')
TRYJOB_DIR = path.join(REPOSITORY_DIR, 'tryjob')

TRYJOB_REPORT   = 'tryjob_report.txt'
AQUARIUM_REPORT = 'aquarium_report.txt'

PATTERN_AQUARIUM_TEST = r'^aquarium_(\w+)_tests\s+(\d+)$'

PATTERN_FLAKY_PASS = r'^.*\[Flaky Pass:(\d+)\].*$'
PATTERN_NEW_PASS   = r'^.*\[New Pass:(\d+)\].*$'
PATTERN_NEW_FAIL   = r'^.*\[New Fail:(\d+)\].*$'

def parse_arguments():
  config = read_json(TRYJOB_CONFIG)
  job_set = set()
  for _, _, test_platform, job_type in config['tryjob']:
    if get_platform() in test_platform:
      job_set |= set(job_type)

  parser = argparse.ArgumentParser(
      description='Run selected tests with your local build.\n'\
                  'Once the tests are finished, the statistics are output to the screen and the file "tryjob_report.txt".\n'\
                  'The tryjob configuration is in "tryjob.json".\n\n',
      formatter_class=argparse.RawTextHelpFormatter)
  parser.add_argument('--job-type', '--job', '-j', nargs='+', choices=sorted(list(job_set)),
      help='You can select one or more jobs from the candidates. By default, all available jobs will be run.\n\n')
  parser.add_argument('--test-filter', '--filter', '-f', nargs='+',
      help='You can specify one or more keywords (the logic is OR), the test that contains the keyword will be run.\n\n')
  parser.add_argument('--result-dir', '-r',
      help='Where to save test logs and test results. The final report "tryjob_report.txt" is generated here as well.\n'\
           'If not specified, it will create a directory with timestamp YEAR_DATE_TIME under the tryjob/ subdirectory of this repository\n\n')
  parser.add_argument('--chrome-dir', '-c',
      help='Chrome source directory.\n\n')
  parser.add_argument('--angle-dir', '-a',
      help='ANGLE source directory.\n\n')
  parser.add_argument('--dawn-dir', '-d',
      help='Dawn source directory.\n\n')
  parser.add_argument('--aquarium-dir', '-q',
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
  parser.add_argument('--dry-run', nargs='?', const=get_platform(), choices=['win', 'linux'],
      help='Go through the process but do not run test actually.\n'\
           'You can specify the platform (win|linux) or leave it empty to use current platform.\n\n')
  args = parser.parse_args()

  if args.dry_run:
    args.result_dir = args.result_dir or '.'
    args.chrome_dir = args.chrome_dir or '.'
    args.aquarium_dir = args.aquarium_dir or '.'

  print('\nRun Tests:')
  args.test_types = []
  platform = args.dry_run if args.dry_run else get_platform()
  for test_name, test_type, test_platform, job_type in config['tryjob']:
    if not platform in test_platform:
      continue
    if args.job_type and not set(args.job_type) & set(job_type):
      continue
    if args.test_filter and not match_any(args.test_filter, lambda x: x in test_name):
      continue
    print(test_name)
    args.test_types.append(test_type)
  if not args.test_types:
    raise Exception('No available test for specified condition')

  for module, backend in args.test_types:
    if module == 'aquarium':
      if not args.aquarium_dir:
        raise Exception('Please specify --aquarium-dir')
    elif module == 'angle':
      if not args.chrome_dir and not args.angle_dir:
        raise Exception('Please specify --chrome-dir or --angle-dir')
    elif module == 'dawn':
      if not args.chrome_dir and not args.dawn_dir:
        raise Exception('Please specify --chrome-dir or --dawn-dir')
    elif not args.chrome_dir:
      raise Exception('Please specify --chrome-dir')

  args.receiver_admin    = config['email']['receiver']['admin']
  args.receiver_tryjob   = config['email']['receiver']['tryjob']
  args.receiver_aquarium = config['email']['receiver']['aquarium']
  args.aquarium_average_fps = config['aquarium']['average_fps'][get_platform()]

  if args.result_dir:
    args.result_dir = path.abspath(args.result_dir)
  else:
    args.result_dir = path.join(TRYJOB_DIR, get_currenttime('%Y_%m%d_%H%M'))

  if args.chrome_dir:
    args.chrome_dir = path.abspath(args.chrome_dir)
    if path.exists(path.join(args.chrome_dir, 'src')):
      args.chrome_dir = path.join(args.chrome_dir, 'src')
  args.angle_dir = path.abspath(args.angle_dir) if args.angle_dir else None
  args.dawn_dir = path.abspath(args.dawn_dir) if args.dawn_dir else None
  args.aquarium_dir = path.abspath(args.aquarium_dir) if args.aquarium_dir else None
  return args


def update_tryjob_report(args, report):
  new_fail, new_pass, flaky_pass = 0, 0, 0
  for line in report.splitlines():
    match = re_match(PATTERN_NEW_FAIL, line)
    new_fail += int(match.group(1)) if match else 0
    if not line.startswith('webgpu'):
      match = re_match(PATTERN_NEW_PASS, line)
      new_pass += int(match.group(1)) if match else 0
    match = re_match(PATTERN_FLAKY_PASS, line)
    flaky_pass += int(match.group(1)) if match else 0

  notice  = ' [New Fail:%d]' % new_fail if new_fail else ''
  notice += ' [New Pass:%d]' % new_pass if new_pass else ''
  notice += ' [Flaky Pass:%d]' % flaky_pass if flaky_pass else ''
  notice = notice or ' [All Clear]'
  title = 'Tryjob Report - %s / %s -%s' % (get_platform().title(), get_hostname(), notice)
  return title, report


def update_aquarium_report(args, report):
  max_bias = 0
  lines = report.splitlines()
  for i in range(len(lines)):
    match = re_match(PATTERN_AQUARIUM_TEST, lines[i])
    if match:
      ref_value = args.aquarium_average_fps[match.group(1)]
      bias = (int(match.group(2)) - ref_value) * 100 // ref_value
      lines[i] += ' (%s%d%%)' % ('+' if bias >= 0 else '', bias)
      max_bias = bias if abs(bias) > abs(max_bias) else max_bias

  notice = '[Max Bias:%s%d%%]' % ('+' if max_bias >= 0 else '', max_bias) if max_bias else '[No Bias]'
  title = 'Aquarium Report - %s / %s - %s' % (get_platform().title(), get_hostname(), notice)
  return title, '\n'.join(lines)


def build_project(project, dir, target, update):
  build_cmd = [path.join(BIN_DIR, 'build_project'), project, '--dir', dir, '--target', target]
  build_cmd += ['--update'] if update else []
  try:
    execute(build_cmd)
  except CalledProcessError as e:
    e.output = execute_return(build_cmd)
    raise e

def notify_error(receiver, error):
  send_email(receiver,
             '%s %s failed on %s' % (path.basename(error.cmd[0]), error.cmd[1], get_hostname()),
             '%s\n\n%s' % (' '.join(error.cmd), error.output))

def main():
  args = parse_arguments()

  # Build project
  if args.build or args.update:
    try:
      if args.chrome_dir:
        build_project('chrome', args.chrome_dir, args.target, args.update)
      if args.angle_dir:
        build_project('angle', args.angle_dir, args.target, args.update)
      if args.dawn_dir:
        build_project('dawn', args.dawn_dir, args.target, args.update)
    except CalledProcessError as e:
      if args.email:
        notify_error(args.receiver_admin, e)
      raise e

    try:
      if args.aquarium_dir:
        build_project('aquarium', args.aquarium_dir, args.target, args.update)
    except CalledProcessError as e:
      if args.email:
        notify_error(args.receiver_aquarium, e)
      args.aquarium_dir = None

  # Run tests
  print('\nTest log: ' + args.result_dir)
  mkdir(args.result_dir)
  for module, backend in args.test_types:
    if module == 'aquarium' and not args.aquarium_dir:
      continue
    cmd = [path.join(BIN_DIR, 'run_gpu_test'), module, backend, '--target', args.target]
    cmd += ['--dry-run', args.dry_run] if args.dry_run else []
    if module == 'aquarium':
      cmd += ['--dir', args.aquarium_dir]
    elif module == 'angle' and args.angle_dir:
      cmd += ['--dir', args.angle_dir]
    elif module == 'dawn' and args.dawn_dir:
      cmd += ['--dir', args.dawn_dir]
    else:
      cmd += ['--dir', args.chrome_dir]
    execute(cmd, dir=args.result_dir)

  # Parse result
  header = 'Location: %s\n' % args.result_dir
  gpu, driver = get_gpu_info()
  header += 'GPU: %s\n' % gpu if gpu else ''
  header += 'Driver: %s\n' % driver if driver else ''

  aquarium_report = execute_return([path.join(BIN_DIR, 'parse_result'),
                                    '--type', 'aquarium', '--dir', args.result_dir])
  if aquarium_report:
    title, aquarium_report = update_aquarium_report(args, aquarium_report)
    aquarium_report = header + '\n' + aquarium_report
    write_file(path.join(args.result_dir, AQUARIUM_REPORT), aquarium_report)
    if args.email:
      send_email(args.receiver_aquarium, title, aquarium_report)
    print('\n--------------------------------------------------\n')
    print(title + '\n\n' + aquarium_report)

  tryjob_report = execute_return([path.join(BIN_DIR, 'parse_result'),
                                  '--dir', args.result_dir])
  if tryjob_report:
    title, tryjob_report = update_tryjob_report(args, tryjob_report)
    if args.chrome_dir:
      revision = get_chrome_revision(args.chrome_dir)
      header += 'Chrome: %s\n' % revision if revision else ''
    tryjob_report = header + '\n' + tryjob_report
    write_file(path.join(args.result_dir, TRYJOB_REPORT), tryjob_report)
    if args.email:
      send_email(args.receiver_tryjob, title, tryjob_report)
    print('\n--------------------------------------------------\n')
    print(title + '\n\n' + tryjob_report)

  print('\n--------------------------------------------------\n')
  print('Test result     : ' + args.result_dir)
  if path.exists(path.join(args.result_dir, AQUARIUM_REPORT)):
    print('Aquarium report : ' + path.join(args.result_dir, AQUARIUM_REPORT))
  if path.exists(path.join(args.result_dir, TRYJOB_REPORT)):
    print('Tryjob report   : ' + path.join(args.result_dir, TRYJOB_REPORT))


if __name__ == '__main__':
  sys.exit(main())
