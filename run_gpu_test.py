#!/usr/bin/env python3

import argparse
import os
import sys

from util.base_util import *
from util.file_util import *
from util.system_util import *
from os import path

ANGLE_END2END_TEST_CMD = 'angle_end2end_tests' + ('.exe' if is_win() else '')
ANGLE_PERF_TEST_CMD    = 'angle_perftests'     + ('.exe' if is_win() else '')
DAWN_END2END_TEST_CMD  = 'dawn_end2end_tests'  + ('.exe' if is_win() else '')
DAWN_PERF_TEST_CMD     = 'dawn_perf_tests'     + ('.exe' if is_win() else '')
GL_TEST_CMD            = 'gl_tests'            + ('.exe' if is_win() else '')
VULKAN_TEST_CMD        = 'vulkan_tests'        + ('.exe' if is_win() else '')
AQUARIUM_CMD           = 'aquarium'            + ('.exe' if is_win() else '')

WEBGL_TEST_SCRIPT         = path.join('content', 'test', 'gpu', 'run_gpu_integration_test.py')
WEBGL2_ABBREVIATED_RESULT = path.join('content', 'test', 'data', 'gpu', 'webgl2_conformance_tests_output.json')

BLINK_TEST_SCRIPT  = path.join('third_party', 'blink', 'tools', 'run_web_tests.py')
WEBGPU_EXPECTATION = path.join('third_party', 'blink', 'web_tests', 'WebGPUExpectations')


def parse_arguments():
  config = read_json(TRYJOB_CONFIG)
  test_backend = {}
  backend_set = set()
  for _, test_arg, _ in config['tryjob']:
    test_backend.setdefault(test_arg[0], [])
    test_backend[test_arg[0]].append(test_arg[1])
    backend_set.add(test_arg[1])

  parser = argparse.ArgumentParser(
      description='Run single test.\n\n',
      formatter_class=argparse.RawTextHelpFormatter)
  parser.add_argument('test', choices=sorted(list(test_backend.keys())),
      help='The test to run.\n\n')
  parser.add_argument('backend', choices=sorted(list(backend_set)),
      help='The backend of the test. Please refer to tryjob.json for detailed backends of each test.\n\n')
  parser.add_argument('--src-dir', '--dir', '-d', default='.',
      help='The source directory. Default is current directory.\n\n')
  parser.add_argument('--target', '-t', default='Default',
      help='The target build directory under "out/". Default is \'Default\'.\n\n')
  parser.add_argument('--filter', '-f', nargs='+', default=[],
      help='The keyword to match the test cases. You can specify multiple.\n\n')
  parser.add_argument('--shard', '-s', default=1, type=int,
      help='Total number of shards being used for this test. Default is 1.\n\n')
  parser.add_argument('--index', '-i', default=-1, type=int,
      help='Shard index of this test.\n'\
           'If the number of shards is more than 1 and this argument is not specified, all shards will be ran in sequence.\n\n')
  parser.add_argument('--repeat', '-r', default=1, type=int,
      help='The number of times to repeat running this test.\n'\
           'If the number of shards is more than 1, the running sequence will be shard0 * N times, shard1 * N times ...\n\n')
  parser.add_argument('--print-log', '-p', action='store_true',
      help='Print full test logs when test is running.\n\n')
  parser.add_argument('--dry-run', action='store_true',
      help='Go through the process but do not run tests actually.\n\n')
  args, extra_args = parser.parse_known_args()

  if args.backend not in test_backend[args.test]:
    raise Exception('The %s backend is not supported by %s test' % (args.backend, args.test))

  if args.filter:
    if args.test in ['blink', 'aquarium']:
      raise Exception('Do not support filter for ' + args.test)
    for i in range(0, len(args.filter)):
      if not args.filter[i].startswith('*'):
        args.filter[i] = '*' + args.filter[i]
      if not args.filter[i].endswith('*'):
        args.filter[i] += '*'

  if args.shard > 1:
    if args.test == 'aquarium':
      raise Exception('Do not support shard for ' + args.test)

  if args.shard > 1 and args.filter:
    raise Exception('Can not specify shard and filter together')

  if args.shard < 1:
    raise Exception('Invalid shard number: %d' % args.shard)
  elif args.index >= args.shard:
    raise Exception('Invalid index number: %d' % args.index)

  if args.repeat < 1:
    raise Exception('Invalid repeat number: %d' % args.repeat)

  for test_name, test_arg, _ in config['tryjob']:
    if args.test == test_arg[0] and args.backend == test_arg[1]:
      pos = test_name.find('(')
      if pos > 0:
        test_name = test_name[0:pos]
      args.log_file = test_name + '.log'
      args.result_file = test_name + '.json'
      break

  args.src_dir = path.abspath(args.src_dir)
  if path.basename(args.src_dir) == 'chromium' and path.exists(path.join(args.src_dir, 'src')):
    args.src_dir = path.join(args.src_dir, 'src')
  args.build_dir = path.join(args.src_dir, 'out', args.target)
  return args, extra_args


def generate_webgl_arguments(args):
  total_args = ['webgl_conformance','--show-stdout', '--passthrough', '-v', '--browser=exact',
                '--browser-executable=' + path.join(args.build_dir, 'chrome') + ('.exe' if is_win() else ''),
                '--retry-only-retry-on-failure-tests']
  if args.test == 'webgl2':
    total_args += ['--webgl-conformance-version=2.0.1',
                   '--read-abbreviated-json-results-from=' + path.join(args.src_dir, WEBGL2_ABBREVIATED_RESULT)]
  if args.filter:
    total_args += ['--test-filter=' + '::'.join(args.filter)]

  browser_args = ['--disable-backgrounding-occluded-windows',
                  '--force_high_performance_gpu']
  if args.backend == 'valid':
    browser_args += ['--use-cmd-decoder=validating']
  elif args.backend in ['d3d9', 'gl', 'vulkan']:
    browser_args += ['--use-cmd-decoder=passthrough',
                     '--use-angle=' + args.backend]
  if not is_win():
    browser_args += ['--enable-logging=stderr']
  return total_args + ['--extra-browser-args=' + ' '.join(browser_args)]


def generate_blink_arguments(args):
  total_args = ['--seed', '4', '--jobs=1', '--driver-logging', '--target=' + args.target,
                '--no-show-results', '--clobber-old-results', '--no-retry-failures']
  if args.backend == 'webgpu':
    total_args += ['--isolated-script-test-filter=wpt_internal/webgpu/*',
                   '--ignore-default-expectations',
                   '--additional-expectations=' + path.join(args.src_dir, WEBGPU_EXPECTATION)]
  if is_linux():
    total_args += ['--no-xvfb']

  driver_flags = ['--enable-unsafe-webgpu']
  if is_win():
    driver_flags += ['--disable-gpu-sandbox']
  elif is_linux():
    driver_flags += ['--use-vulkan=native']
  if args.backend == 'webgpu_valid':
    driver_flags += ['--enable-dawn-backend-validation']
  return total_args + ['--additional-driver-flag=' + flag for flag in driver_flags]


def generate_unittest_arguments(args):
  if args.backend == 'perf':
    total_args = ['--verbose', '-v',
                  '--test-launcher-print-test-stdio=always',
                  '--test-launcher-jobs=1',
                  '--test-launcher-retry-limit=0']
    if args.test == 'angle':
      total_args += ['--one-frame-only']
    elif args.test == 'dawn':
      total_args += ['--override-steps=1']
  elif args.backend.startswith('end2end'):
    total_args = ['--use-gpu-in-tests',
                  '--test-launcher-retry-limit=0']
    if args.test == 'angle':
      total_args += ['--test-launcher-batch-limit=256',
                     '--test-launcher-bot-mode',
                     '--cfi-diag=0']
      if is_linux():
        total_args += ['--no-xvfb']
    elif args.backend == 'end2end_wire':
      total_args += ['--use-wire']
    elif args.backend == 'end2end_valid':
      total_args += ['--enable-backend-validation']
    elif args.backend == 'end2end_skip':
      total_args += ['--skip-validation']
  elif args.test == 'gpu':
    total_args = ['--use-gpu-in-tests',
                  '--test-launcher-bot-mode',
                  '--cfi-diag=0']

  if args.test == 'angle' and args.backend == 'end2end':
    args.filter += ['-*Vulkan_SwiftShader*']
  if args.filter:
    total_args += ['--gtest_filter=' + ':'.join(args.filter)]
  return total_args


def generate_aquarium_arguments(args):
  config = read_json(TRYJOB_CONFIG)
  total_args = ['--enable-msaa', '--turn-off-vsync', '--integrated-gpu',
                '--window-size=1920,1080', '--print-log',
                '--backend', args.backend,
                '--test-time', str(config['aquarium']['test_time']),
                '--num-fish', str(config['aquarium']['num_fish'])]
  return total_args


def execute_shard(cmd, args):
  env = get_env()
  if is_win():
    env.pop('http_proxy', None)
    env.pop('https_proxy', None)
    env.pop('HTTP_PROXY', None)
    env.pop('HTTPS_PROXY', None)

  log_name, log_ext = path.splitext(args.log_file)
  result_name, result_ext = path.splitext(args.result_file)
  shard_ext = ''
  if args.shard > 1:
    shard_ext = '.shard' + format(args.index, '02d')

  for n in range(0, args.repeat):
    repeat_ext = ''
    if args.repeat > 1:
      repeat_ext = '.' + format(n, '03d')
    log_file = log_name + shard_ext + repeat_ext + log_ext
    print(log_name + shard_ext + repeat_ext)

    result_arg = []
    if args.test in ['webgl', 'webgl2', 'blink']:
      result_arg = ['--write-full-results-to=' + result_name + shard_ext + repeat_ext + result_ext]
    if args.dry_run:
      print(' '.join(['"'+arg+'"' if arg.startswith('--extra-browser-args') else arg for arg in (cmd + result_arg)]))
    else:
      try:
        execute_command(cmd + result_arg, print_log=args.print_log, return_log=False, save_log=log_file, env=env)
      except CalledProcessError:
        pass


def main():
  args, extra_args = parse_arguments()

  if args.test in ['webgl', 'webgl2']:
    cmd = [PYTHON_CMD, path.join(args.src_dir, WEBGL_TEST_SCRIPT)]
    cmd += generate_webgl_arguments(args)
  elif args.test == 'blink':
    cmd = [PYTHON_CMD, path.join(args.src_dir, BLINK_TEST_SCRIPT)]
    cmd += generate_blink_arguments(args)
  elif args.test == 'dawn' and args.backend.startswith('end2end'):
    cmd = [path.join(args.build_dir, DAWN_END2END_TEST_CMD)]
    cmd += generate_unittest_arguments(args)
  elif args.test == 'dawn' and args.backend == 'perf':
    cmd = [path.join(args.build_dir, DAWN_PERF_TEST_CMD)]
    cmd += generate_unittest_arguments(args)
  elif args.test == 'angle' and args.backend == 'end2end':
    cmd = [path.join(args.build_dir, ANGLE_END2END_TEST_CMD)]
    cmd += generate_unittest_arguments(args)
  elif args.test == 'angle' and args.backend == 'perf':
    cmd = [path.join(args.build_dir, ANGLE_PERF_TEST_CMD)]
    cmd += generate_unittest_arguments(args)
  elif args.test == 'gpu' and args.backend == 'gl':
    cmd = [path.join(args.build_dir, GL_TEST_CMD)]
    cmd += generate_unittest_arguments(args)
  elif args.test == 'gpu' and args.backend == 'vulkan':
    cmd = [path.join(args.build_dir, VULKAN_TEST_CMD)]
    cmd += generate_unittest_arguments(args)
  elif args.test == 'aquarium':
    cmd = [path.join(args.build_dir, AQUARIUM_CMD)]
    cmd += generate_aquarium_arguments(args)
  cmd += extra_args

  if args.shard == 1:
    execute_shard(cmd, args)
  else:
    if args.test in ['webgl', 'webgl2', 'blink']:
      total_shards = '--total-shards'
      shard_index = '--shard-index'
    elif args.test in ['dawn', 'angle', 'gpu']:
      total_shards = '--test-launcher-total-shards'
      shard_index = '--test-launcher-shard-index'

    cmd += ['%s=%d' % (total_shards, args.shard)]
    if args.index >= 0:
      execute_shard(cmd + ['%s=%d' % (shard_index, args.index)], args)
    else:
      for i in range(0, args.shard):
        args.index = i
        execute_shard(cmd + ['%s=%d' % (shard_index, args.index)], args)


if __name__ == '__main__':
  sys.exit(main())
