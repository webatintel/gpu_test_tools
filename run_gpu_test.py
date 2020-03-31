#!/usr/bin/env python

import argparse
import sys

from util.base_util import *
from os import path

ANGLE_END_TEST_CMD = 'angle_end2end_tests'
ANGLE_PERF_TEST_CMD = 'angle_perftests'
AQUARIUM_TEST_CMD = 'aquarium'

AQUARIUM_TEST_TIME = 30
AQUARIUM_NUM_FISH = 30000

BROWSER_TEST_SCRIPT = path.join('testing', 'scripts',
    'run_gpu_integration_test_as_googletest.py')
GPU_TEST_SCRIPT = path.join('content', 'test', 'gpu',
    'run_gpu_integration_test.py')

WEBGL2_CONFORMANCE_VERSION = '2.0.1'
WEBGL2_ABBREVIATED_RESULT = path.join('content', 'test', 'data', 'gpu',
    'webgl2_conformance_tests_output.json')

TRY_JOB_CONFIG = path.join(path.dirname(path.abspath(__file__)), 'try_job.json')

def parse_arguments():
  parser = argparse.ArgumentParser(
      description='GPU test tools\n\n',
      formatter_class=argparse.RawTextHelpFormatter)
  parser.add_argument('target',
      choices=['webgl', 'webgl2', 'angle', 'fyi', 'aquarium'],
      help='Specify the test you want to run.\n\n'\
           'webgl    :  WebGL conformance tests\n'\
           'webgl2   :  WebGL2 conformance tests\n'\
           'angle    :  ANGLE tests\n'\
           'fyi      :  Miscellaneous less important tests\n'\
           'aquarium :  Aquarium tests\n\n')
  parser.add_argument('--backend', '-b',
      choices=['passthrough', 'validating', 'gl', 'vulkan', 'd3d9',
               'end2end', 'perf',
               'pixel',
               'd3d12', 'dawn_d3d12', 'dawn_vulkan'],
      help='Specify the backend. Not all targets are supporting all backends.\n'\
           'Run default tests if the backend is not specified.\n'\
           '\n[WebGL/WebGL2]\n'\
           'passthrough : passthrough command decoder with default backend (default)\n'\
           'validating  : validating command decoder with default backend\n'\
           'gl          : opengl passthrough\n'\
           'vulkan      : vulkan passthrough\n'\
           'd3d9        : d3d9   passthrough\n'\
           '\n[ANGLE]\n'\
           'end2end : end2end test (default)\n'\
           'perf    : performance test\n'\
           '\n[FYI]\n'\
           'pixel : pixel skia gold test\n'\
           '\n[Aquarium]\n'\
           'dawn_vulkan : dawn vulkan (default)\n'\
           'dawn_d3d12  : dawn d3d12\n'\
           'd3d12       : d3d12\n\n')
  parser.add_argument('--type', '-t',
      choices=['release', 'debug', 'default'], default='release',
      help='Browser type. Default is \'release\'.\n'\
           'release/debug/default assume that the binaries are\n'\
           'generated into out/Release or out/Debug or out/Default.\n\n')
  parser.add_argument('--dir', '-d', default='.',
      help='Chrome/Aquarium directory.\n\n')
  parser.add_argument('--log', '-l', action='store_true',
      help='Print full test logs when test is running.\n\n')
  parser.add_argument('--iris', action='store_true',
      help='Enable Iris driver. (Only available on Ubuntu/Mesa environment)\n\n')
  parser.add_argument('--filter', '-f',
      help='Keywords to match the test cases. Devide with |.\n\n')
  parser.add_argument('--repeat', '-r', default=1, type=int,
      help='The number of times to repeat running this test.\n'\
           'If the number of shards is more than 1, the running sequence\n'\
           'will be shard0 * N times, shard1 * N times ...\n\n')
  parser.add_argument('--shard', '-s', default=1, type=int,
      help='Total number of shards being used for this test. Default is 1.\n\n')
  parser.add_argument('--index', '-i', default=-1, type=int,
      help='Shard index of this test.\n'\
           'If the number of shards is more than 1 and this argument is not\n'\
           'specified, all shards will be ran in sequence.\n\n')
  args, extra_args = parser.parse_known_args()

  if args.target.startswith('webgl'):
    if not args.backend:
      args.backend = 'passthrough'
    if (args.backend != 'passthrough' and args.backend != 'validating'
        and args.backend != 'gl' and args.backend != 'vulkan' and args.backend != 'd3d9'):
      raise Exception('Unsupported backend: ' + args.backend)
  elif args.target == 'angle':
    if not args.backend:
      args.backend = 'end2end'
    if args.backend != 'end2end' and args.backend != 'perf':
      raise Exception('Unsupported backend: ' + args.backend)
  elif args.target == 'fyi':
    if not args.backend:
      args.backend = 'pixel'
    if args.backend != 'pixel':
      raise Exception('Unsupported backend: ' + args.backend)
  elif args.target == 'aquarium':
    if not args.backend:
      args.backend = 'dawn_vulkan'
    if not args.backend.startswith('dawn_') and args.backend != 'd3d12':
      raise Exception('Unsupported backend: ' + args.backend)

  if args.shard > 1 and (not args.target.startswith('webgl') and args.target != 'angle'):
    raise Exception('Do not support shard for ' + args.target)

  if args.filter and (not args.target.startswith('webgl') and args.target != 'angle' and args.target != 'fyi'):
    raise Exception('Do not support filter for ' + args.target)

  if args.shard > 1 and args.filter:
    raise Exception('Can not specify shard and filter together')

  if args.repeat < 1:
    raise Exception('Invalid repeat number: %d' % args.repeat)
  
  if args.shard < 1:
    raise Exception('Invalid shard number: %d' % args.shard)
  elif args.index >= args.shard:
    raise Exception('Invalid index number: %d' % args.index)

  args.dir = path.abspath(args.dir)
  if path.basename(args.dir) == 'chromium':
    args.dir = path.join(args.dir, 'src')
  args.build_dir = path.join('out', args.type.title())
  return args, extra_args


def generate_webgl_arguments(args):
  # Common arguments
  common_args = ['--show-stdout', '--passthrough', '-v',
                 '--browser=' + args.type,
                 '--retry-only-retry-on-failure-tests']

  # Browser arguments
  browser_args = ['--disable-backgrounding-occluded-windows']
  if not is_win():
    browser_args.append('--enable-logging=stderr')
  config = read_json(TRY_JOB_CONFIG)
  key = '%s_%s' % (args.target.replace('webgl2', 'webgl'), args.backend)
  browser_args.extend(config['try_job_browser_args'][key])

  # WebGL arguments
  webgl_args = []
  if args.target == 'webgl2':
    webgl_args.append('--webgl-conformance-version=' + WEBGL2_CONFORMANCE_VERSION)
    webgl_args.append('--read-abbreviated-json-results-from=' + path.join(args.dir, WEBGL2_ABBREVIATED_RESULT))

  total_args = []
  total_args.extend(common_args)
  total_args.append('--extra-browser-args=' + ' '.join(browser_args))
  total_args.extend(webgl_args)

  # Filters
  if args.filter:
      filter = args.filter
      if (not filter.startswith('*') and not filter.startswith('deqp')
          and not filter.startswith('conformance')):
        filter = '*' + filter
      if not filter.endswith('*') and not filter.endswith('html'):
        filter = filter + '*'
      total_args.append('--test-filter=' + filter)

  return total_args


def generate_fyi_arguments(args):
  if args.backend == 'pixel':
    common_args = ['--show-stdout',
                   '--browser=' + args.type,
                   '--passthrough', '-v',
                   '--dont-restore-color-profile-after-test']
    browser_args = ['--js-flags=--expose-gc']

  total_args = []
  total_args.extend(common_args)
  total_args.append('--extra-browser-args=' + ' '.join(browser_args))
  if args.filter:
    total_args.append('--test-filter=' + args.filter)
  return total_args


def generate_angle_arguments(args):
  if args.backend == 'end2end':
    total_args = ['--use-gpu-in-tests',
                  '--test-launcher-retry-limit=0'
                  '--test-launcher-batch-limit=256']
    if is_linux():
      total_args.append('--no-xvfb')
    if args.filter:
      total_args.append('--gtest_filter=' + args.filter)
  elif args.backend == 'perf':
    total_args = ['-v', '--one-frame-only',
                  '--gtest-benchmark-name=angle_perftests']

  return total_args


def generate_aquarium_arguments(args):
  total_args = ['--enable-msaa',
                '--window-size=1920,1080',
                '--turn-off-vsync',
                '--print-log',
                '--integrated-gpu']
  total_args.extend(['--backend', args.backend])
  total_args.extend(['--test-time', str(AQUARIUM_TEST_TIME)])
  total_args.extend(['--num-fish', str(AQUARIUM_NUM_FISH)])
  return total_args


def execute_shard(cmd, args):
  env = get_env()
  if args.iris:
    env['MESA_LOADER_DRIVER_OVERRIDE'] = 'iris'

  log_name, log_ext = path.splitext(args.log_file)
  result_name, result_ext = path.splitext(args.result_file)
  shard_postfix = ''
  if args.shard > 1:
    shard_postfix = '.shard' + format(args.index, '02d')

  for n in range(1, args.repeat+1):
    postfix = shard_postfix
    if args.repeat > 1:
      postfix += '.' + format(n, '03d')
    log_file = log_name + postfix + log_ext
    result_file = result_name + postfix + result_ext
    print(log_name + postfix)

    new_cmd = cmd[:]
    if args.target.startswith('webgl') or args.target == 'fyi':
      new_cmd.append('--isolated-script-test-output=' + result_file)
    try:
      execute_command(new_cmd, print_log=args.log, return_log=False, save_log=log_file, env=env)
    except CalledProcessError:
      pass


def main():
  args, extra_args = parse_arguments()

  if args.target.startswith('webgl'):
    cmd = [PYTHON_CMD,
           path.join(args.dir, BROWSER_TEST_SCRIPT),
           path.join(args.dir, GPU_TEST_SCRIPT),
           'webgl_conformance']
    cmd.extend(generate_webgl_arguments(args))
    total_shards = '--total-shards'
    shard_index = '--shard-index'
  elif args.target == 'angle':
    if args.backend == 'end2end':
      cmd = [path.join(args.dir, args.build_dir, ANGLE_END_TEST_CMD)]
    elif args.backend == 'perf':
      cmd = [path.join(args.dir, args.build_dir, ANGLE_PERF_TEST_CMD)]
    cmd.extend(generate_angle_arguments(args))
    total_shards = '--test-launcher-total-shards'
    shard_index = '--test-launcher-shard-index'
  elif args.target == 'fyi':
    if args.backend == 'pixel':
      cmd = [PYTHON_CMD,
             path.join(args.dir, BROWSER_TEST_SCRIPT),
             path.join(args.dir, GPU_TEST_SCRIPT),
             'pixel']
    cmd.extend(generate_fyi_arguments(args))
    total_shards = '--total-shards'
    shard_index = '--shard-index'
  elif args.target == 'aquarium':
    cmd = [path.join(args.dir, args.build_dir, AQUARIUM_TEST_CMD)]
    cmd.extend(generate_aquarium_arguments(args))
  cmd.extend(extra_args)

  if args.backend:
    args.log_file = '%s_%s_test.log' % (args.target, args.backend)
    args.result_file = '%s_%s_test.json' % (args.target, args.backend)
  else:
    args.log_file = '%s_test.log' % args.target
    args.result_file = '%s_test.json' % args.target

  if args.shard == 1:
    execute_shard(cmd, args)
  else:
    cmd.append('%s=%d' % (total_shards, args.shard))
    if args.index >= 0:
      cmd.append('%s=%d' % (shard_index, args.index))
      execute_shard(cmd, args)
    else:
      for i in range(0, args.shard):
        args.index = i
        new_cmd = cmd[:]
        new_cmd.append('%s=%d' % (shard_index, args.index))
        execute_shard(new_cmd, args)

  if args.target == 'aquarium':
    remove('imgui.ini')

if __name__ == '__main__':
  sys.exit(main())
