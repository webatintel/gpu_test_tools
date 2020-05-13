#!/usr/bin/env python3

import argparse
import os
import sys

from util.base_util import *
from util.file_util import *
from util.system_util import *
from os import path

WEBGL_TEST_SCRIPT  = path.join('content', 'test', 'gpu', 'run_gpu_integration_test.py')
WEBGL2_TEST_OUTPUT = path.join('content', 'test', 'data', 'gpu', 'webgl2_conformance_tests_output.json')

BLINK_TEST_SCRIPT  = path.join('third_party', 'blink', 'tools', 'run_web_tests.py')
WEBGPU_EXPECTATION = path.join('third_party', 'blink', 'web_tests', 'WebGPUExpectations')

GL_TEST_CMD            = get_executable('gl_tests')
VULKAN_TEST_CMD        = get_executable('vulkan_tests')
ANGLE_END2END_TEST_CMD = get_executable('angle_end2end_tests')
ANGLE_PERF_TEST_CMD    = get_executable('angle_perftests')
DAWN_END2END_TEST_CMD  = get_executable('dawn_end2end_tests')
DAWN_PERF_TEST_CMD     = get_executable('dawn_perf_tests')
AQUARIUM_CMD           = get_executable('aquarium')

def parse_arguments():
  config = read_json(TRYJOB_CONFIG)
  test_backend = {}
  backend_set = set()
  for _, test_arg, _, _ in config['tryjob']:
    test_backend.setdefault(test_arg[0], [])
    test_backend[test_arg[0]].append(test_arg[1])
    backend_set.add(test_arg[1])

  parser = argparse.ArgumentParser(
      description='Run single test.\n\n',
      formatter_class=argparse.RawTextHelpFormatter)
  parser.add_argument('test', choices=sorted(list(test_backend.keys())),
      help='The test to run.\n\n')
  parser.add_argument('backend', choices=sorted(list(backend_set)),
      help='The backend of test. Please refer to "tryjob.json" for detailed backends of each test.\n\n')
  parser.add_argument('--src-dir', '--dir', '-d', default='.',
      help='The source directory. Default is current directory.\n\n')
  parser.add_argument('--target', '-t', default='Default',
      help='The target build directory under "out/". Default is "Default".\n\n')
  parser.add_argument('--filter', '-f', nargs='+', default=[],
      help='The keyword to match the test cases. You can specify multiple.\n\n')
  parser.add_argument('--shard', '-s', default=1, type=int,
      help='Total number of shards being used for this test. Default is 1.\n\n')
  parser.add_argument('--index', '-i', default=-1, type=int,
      help='Shard index of this test.\n'\
           'If this argument is not specified, all shards will be run in sequence.\n\n')
  parser.add_argument('--repeat', '-r', default=1, type=int,
      help='The number of times to repeat running this test.\n'\
           'For multiple shards, the running sequence will be shard0 * N times, shard1 * N times ...\n\n')
  parser.add_argument('--print-log', '-p', action='store_true',
      help='Print full test log when test is running.\n\n')
  parser.add_argument('--dry-run', action='store_true',
      help='Go through the process but do not run test actually.\n\n')
  args, extra_args = parser.parse_known_args()

  if args.backend not in test_backend[args.test]:
    raise Exception('The %s backend is not supported by %s test' % (args.backend, args.test))

  if args.filter:
    if args.test in ['blink', 'aquarium']:
      raise Exception('Do not support filter in %s test ' % args.test)
    for i in range(0, len(args.filter)):
      if not args.filter[i].startswith('*'):
        args.filter[i] = '*' + args.filter[i]
      if not args.filter[i].endswith('*'):
        args.filter[i] += '*'

  if args.shard > 1:
    if args.test == 'aquarium':
      raise Exception('Do not support shard in %s test' % args.test)
    if args.filter:
      raise Exception('Can not specify shard and filter together')

  if args.shard < 1:
    raise Exception('Invalid shard number: %d' % args.shard)
  elif args.index >= args.shard:
    raise Exception('Invalid index number: %d' % args.index)

  if args.repeat < 1:
    raise Exception('Invalid repeat number: %d' % args.repeat)

  args.test_args = config['test_args']
  args.browser_args = config['browser_args']
  for test_name, test_arg, _, _ in config['tryjob']:
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


def execute_shard(cmd, args):
  env = get_env()
  if is_win():
    for var in ['http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY']:
      env.pop(var, None)

  log_name, log_ext = path.splitext(args.log_file)
  result_name, result_ext = path.splitext(args.result_file)
  shard_ext = '.shard' + format(args.index, '02d') if args.shard > 1 else ''

  for n in range(0, args.repeat):
    repeat_ext = '.' + format(n, '03d') if args.repeat > 1 else ''
    log_file = log_name + shard_ext + repeat_ext + log_ext
    result_file = result_name + shard_ext + repeat_ext + result_ext
    result_arg = []
    if args.test in ['webgl', 'webgl2', 'blink']:
      result_arg = ['--write-full-results-to=' + result_file]

    if args.dry_run:
      print(' '.join(cmd + result_arg))
      continue
    try:
      print(log_name + shard_ext + repeat_ext)
      execute_command(cmd + result_arg, print_log=args.print_log,
                      return_log=False, save_log=log_file, env=env)
    except CalledProcessError:
      pass


def main():
  args, extra_args = parse_arguments()

  if args.test in ['webgl', 'webgl2']:
    cmd = [PYTHON_CMD, path.join(args.src_dir, WEBGL_TEST_SCRIPT)]
  elif args.test == 'blink':
    cmd = [PYTHON_CMD, path.join(args.src_dir, BLINK_TEST_SCRIPT)]
  elif args.test == 'gpu' and args.backend == 'gl':
    cmd = [path.join(args.build_dir, GL_TEST_CMD)]
  elif args.test == 'gpu' and args.backend == 'vulkan':
    cmd = [path.join(args.build_dir, VULKAN_TEST_CMD)]
  elif args.test == 'angle' and args.backend == 'end2end':
    cmd = [path.join(args.build_dir, ANGLE_END2END_TEST_CMD)]
  elif args.test == 'angle' and args.backend == 'perf':
    cmd = [path.join(args.build_dir, ANGLE_PERF_TEST_CMD)]
  elif args.test == 'dawn' and args.backend.startswith('end2end'):
    cmd = [path.join(args.build_dir, DAWN_END2END_TEST_CMD)]
  elif args.test == 'dawn' and args.backend == 'perf':
    cmd = [path.join(args.build_dir, DAWN_PERF_TEST_CMD)]
  elif args.test == 'aquarium':
    cmd = [path.join(args.build_dir, AQUARIUM_CMD)]

  test_args = []
  browser_args = []
  for key in [args.test, args.test + '_' + args.backend]:
    test_args += args.test_args.get(key, [])
    browser_args += args.browser_args.get(key, [])

  if args.test in ['webgl', 'webgl2']:
    browser_executable = get_executable(path.join(args.build_dir, 'chrome'))
    test_args += ['--browser=exact', '--browser-executable=' + browser_executable]
    if args.test == 'webgl2':
      test_args += ['--read-abbreviated-json-results-from=' + path.join(args.src_dir, WEBGL2_TEST_OUTPUT)]
    if args.filter:
      test_args += ['--test-filter=' + '::'.join(args.filter)]
    if is_linux():
      browser_args += ['--enable-logging=stderr']
    if args.dry_run:
      test_args += ['"--extra-browser-args=%s"' % ' '.join(browser_args)]
    else:
      test_args += ['--extra-browser-args=' + ' '.join(browser_args)]
  elif args.test == 'blink':
    test_args += ['--target=' + args.target]
    if args.backend.startswith('webgpu'):
      test_args += ['--additional-expectations=' + path.join(args.src_dir, WEBGPU_EXPECTATION)]
      if is_linux():
        test_args += ['--no-xvfb']
        browser_args += ['--use-vulkan=native']
      elif is_win():
        browser_args += ['--disable-gpu-sandbox']
    test_args += ['--additional-driver-flag=' + arg for arg in browser_args]
  elif args.test in ['gpu', 'angle', 'dawn']:
    if args.test == 'angle' and args.backend == 'end2end':
      args.filter += ['-*Vulkan_SwiftShader*']
      if is_linux():
        tests_args += ['--no-xvfb']
    if args.filter:
      test_args += ['--gtest_filter=' + ':'.join(args.filter)]

  cmd += test_args + extra_args
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
