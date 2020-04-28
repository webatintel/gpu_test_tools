#!/usr/bin/env python

import argparse
import os
import sys

from util.base_util import *
from util.file_util import *
from util.system_util import *
from os import path

ANGLE_END2END_TEST_CMD = 'angle_end2end_tests'
ANGLE_PERF_TEST_CMD = 'angle_perftests'
DAWN_END2END_TEST_CMD = 'dawn_end2end_tests'
DAWN_PERF_TEST_CMD = 'dawn_perf_tests'
GL_TEST_CMD = 'gl_tests'
VULKAN_TEST_CMD = 'vulkan_tests'
AQUARIUM_TEST_CMD = 'aquarium'

AQUARIUM_TEST_TIME = 30
AQUARIUM_NUM_FISH = 30000

GPU_TEST_SCRIPT = path.join('content', 'test', 'gpu',
    'run_gpu_integration_test.py')
WEBGL2_ABBREVIATED_RESULT = path.join('content', 'test', 'data', 'gpu',
    'webgl2_conformance_tests_output.json')
BLINK_TEST_SCRIPT = path.join('third_party', 'blink', 'tools', 'run_web_tests.py')
WEBGPU_EXPECTATIONS = path.join('third_party', 'blink', 'web_tests', 'WebGPUExpectations')

TRYJOB_CONFIG = path.join(path.dirname(path.abspath(__file__)), 'tryjob.json')

def parse_arguments():
  parser = argparse.ArgumentParser(
      description='Run single test.\n\n',
      formatter_class=argparse.RawTextHelpFormatter)
  parser.add_argument('test_type',
      choices=['webgl', 'webgl2', 'blink', 'dawn', 'angle', 'gpu', 'aquarium'],
      help='The test to run.\n\n'\
           'webgl    :  WebGL conformance tests\n'\
           'webgl2   :  WebGL2 conformance tests\n'\
           'blink    :  Blink tests\n'\
           'dawn     :  Dawn tests\n'\
           'angle    :  ANGLE tests\n'\
           'gpu      :  GPU tests\n'\
           'aquarium :  Aquarium tests\n\n')
  parser.add_argument('--backend', '-b', required=True,
      choices=['validating', 'gl', 'vulkan', 'd3d9', 'd3d11', 'd3d12', 
               'webgpu', 'end2end', 'end2end_wire', 'end2end_validation', 'perf',
               'dawn_vulkan', 'dawn_d3d12'],
      help='The backend of the test. The combination of test type and backend:\n'\
           '\n[webgl/webgl2]\n'\
           'validating : webgl_conformance_validating_tests\n'\
           'gl         : webgl_conformance_gl_passthrough_tests\n'\
           'vulkan     : webgl_conformance_vulkan_passthrough_tests\n'\
           'd3d9       : webgl_conformance_d3d9_passthrough_tests\n'\
           'd3d11      : webgl_conformance_tests\n'\
           '\n[blink]\n'\
           'webgpu     : webgpu_blink_web_tests\n'\
           '\n[dawn]\n'\
           'end2end            : dawn_end2end_tests\n'\
           'end2end_wire       : dawn_end2end_wire_tests\n'\
           'end2end_validation : dawn_end2end_validation_layers_tests\n'\
           'perf               : dawn_perf_tests\n'\
           '\n[angle]\n'\
           'end2end    : angle_end2end_tests\n'\
           'perf       : angle_perf_tests\n'\
           '\n[gpu]\n'\
           'gl         : gl_tests\n'\
           'vulkan     : vulkan_tests\n'\
           '\n[aquarium]\n'\
           'dawn_vulkan : aquarium_dawn_vulkan_tests\n'\
           'dawn_d3d12  : aquarium_dawn_d3d12_tests\n'\
           'd3d12       : aquarium_d3d12_tests\n\n')
  parser.add_argument('--src-dir', '--dir', '-d', default='.',
      help='The source directory. Default is current directory.\n\n')
  parser.add_argument('--target', '-t', default='Default',
      help='The target build directory under "out/". Default is \'Default\'.\n\n')
  parser.add_argument('--log', '-l', action='store_true',
      help='Print full test logs when test is running.\n\n')
  parser.add_argument('--filter', '-f',
      help='The keyword to match the test cases.\n\n')
  parser.add_argument('--repeat', '-r', default=1, type=int,
      help='The number of times to repeat running this test.\n'\
           'If the number of shards is more than 1, the running sequence will be shard0 * N times, shard1 * N times ...\n\n')
  parser.add_argument('--shard', '-s', default=1, type=int,
      help='Total number of shards being used for this test. Default is 1.\n\n')
  parser.add_argument('--index', '-i', default=-1, type=int,
      help='Shard index of this test.\n'\
           'If the number of shards is more than 1 and this argument is not specified, all shards will be ran in sequence.\n\n')
  parser.add_argument('--dry-run', action='store_true',
      help='Go through the process but do not run tests actually.\n\n')
  args, extra_args = parser.parse_known_args()

  if args.test_type.startswith('webgl'):
    if not args.backend in ['validating', 'gl', 'vulkan', 'd3d9', 'd3d11']:
      raise Exception('Unsupported backend: ' + args.backend)
  elif args.test_type == 'blink':
    if not args.backend in ['webgpu']:
      raise Exception('Unsupported backend: ' + args.backend)
  elif args.test_type == 'dawn':
    if not args.backend in ['end2end', 'end2end_wire', 'end2end_validation', 'perf']:
      raise Exception('Unsupported backend: ' + args.backend)
  elif args.test_type == 'angle':
    if not args.backend in ['end2end', 'perf']:
      raise Exception('Unsupported backend: ' + args.backend)
  elif args.test_type == 'gpu':
    if not args.backend in ['gl', 'vulkan']:
      raise Exception('Unsupported backend: ' + args.backend)
  elif args.test_type == 'aquarium':
    if not args.backend in ['dawn_vulkan', 'dawn_d3d12', 'd3d12']:
      raise Exception('Unsupported backend: ' + args.backend)

  if args.filter:
    if (args.test_type == 'aquarium' or args.test_type == 'blink'
        or (args.test_type == 'angle' and args.backend == 'end2end')):
      raise Exception('Do not support filter for %s/%s' % (args.test_type, args.backend))

  if args.shard > 1:
    if args.test_type == 'aquarium':
      raise Exception('Do not support shard for ' + args.test_type)

  if args.shard > 1 and args.filter:
    raise Exception('Can not specify shard and filter together')

  if args.repeat < 1:
    raise Exception('Invalid repeat number: %d' % args.repeat)
  
  if args.shard < 1:
    raise Exception('Invalid shard number: %d' % args.shard)
  elif args.index >= args.shard:
    raise Exception('Invalid index number: %d' % args.index)

  args.src_dir = path.abspath(args.src_dir)
  if path.basename(args.src_dir) == 'chromium' and path.exists(path.join(args.src_dir, 'src')):
    args.src_dir = path.join(args.src_dir, 'src')
  args.build_dir = path.join(args.src_dir, 'out', args.target)
  return args, extra_args


def generate_webgl_arguments(args):
  if is_linux():
    executable = path.join(args.build_dir, 'chrome')
  elif is_win():
    executable = path.join(args.build_dir, 'chrome.exe')

  total_args = ['--show-stdout', '--passthrough', '-v',
                '--browser=exact', '--browser-executable=' + executable,
                '--retry-only-retry-on-failure-tests']
  if args.test_type == 'webgl2':
    total_args += ['--webgl-conformance-version=2.0.1',
                   '--read-abbreviated-json-results-from=' + path.join(args.src_dir, WEBGL2_ABBREVIATED_RESULT)]

  browser_args = ['--disable-backgrounding-occluded-windows']
  if not is_win():
    browser_args += ['--enable-logging=stderr']
  config = read_json(TRYJOB_CONFIG)
  browser_args += config['tryjob_args']['webgl_'+args.backend]
  total_args.append('--extra-browser-args=' + ' '.join(browser_args))

  if args.filter:
      filter = args.filter
      if (not filter.startswith('*') and not filter.startswith('deqp')
          and not filter.startswith('conformance')):
        filter = '*' + filter
      if not filter.endswith('*') and not filter.endswith('html'):
        filter = filter + '*'
      total_args.append('--test-filter=' + filter)

  return total_args


def generate_blink_arguments(args):
  total_args = ['--seed', '4', '--jobs=1', '--driver-logging',
                '--target=' + args.target,
                '--no-show-results', '--clobber-old-results', '--no-retry-failures',
                '--additional-driver-flag=--enable-unsafe-webgpu',
                '--ignore-default-expectations',
                '--additional-expectations=' + path.join(args.src_dir, WEBGPU_EXPECTATIONS),
                '--isolated-script-test-filter=wpt_internal/webgpu/*']
  if is_win():
    total_args += ['--additional-driver-flag=--disable-gpu-sandbox']
  elif is_linux():
    total_args += ['--additional-driver-flag=--use-vulkan=native',
                   '--no-xvfb']
  return total_args


def generate_gtest_arguments(args):
  total_args = []
  if args.backend == 'perf':
    total_args += ['--verbose', '-v',
                   '--test-launcher-print-test-stdio=always',
                   '--test-launcher-jobs=1',
                   '--test-launcher-retry-limit=0']
    if args.test_type == 'angle':
      total_args += ['--one-frame-only']
    elif args.test_type == 'dawn':
      total_args += ['--override-steps=1']
  elif args.backend.startswith('end2end'):
    total_args += ['--use-gpu-in-tests',
                   '--test-launcher-retry-limit=0']
    if args.backend == 'end2end_wire':
      total_args += ['--use-wire']
    elif args.backend == 'end2end_validation':
      total_args += ['--enable-backend-validation']
    elif args.test_type == 'angle':
      total_args += ['--test-launcher-bot-mode',
                     '--cfi-diag=0',
                     '--test-launcher-batch-limit=256',
                     '--gtest_filter=-*Vulkan_SwiftShader*']
  elif args.test_type == 'gpu':
    total_args += ['--use-gpu-in-tests',
                   '--test-launcher-bot-mode',
                   '--cfi-diag=0']

  if args.filter:
    total_args.append('--gtest_filter=' + args.filter)
  return total_args


def generate_aquarium_arguments(args):
  total_args = ['--enable-msaa',
                '--window-size=1920,1080',
                '--turn-off-vsync',
                '--print-log',
                '--integrated-gpu']
  total_args += ['--backend', args.backend]
  total_args += ['--test-time', str(AQUARIUM_TEST_TIME)]
  total_args += ['--num-fish', str(AQUARIUM_NUM_FISH)]
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
    if args.test_type.startswith('webgl') or args.test_type == 'blink':
      new_cmd.append('--write-full-results-to=' + result_file)
    if args.dry_run:
      print(' '.join(new_cmd))
      continue
    try:
      execute_command(new_cmd, print_log=args.log, return_log=False, save_log=log_file, env=env)
    except CalledProcessError:
      pass


def main():
  args, extra_args = parse_arguments()

  if args.test_type.startswith('webgl'):
    cmd = [PYTHON_CMD, path.join(args.src_dir, GPU_TEST_SCRIPT), 'webgl_conformance']
    cmd += generate_webgl_arguments(args)
    total_shards = '--total-shards'
    shard_index = '--shard-index'
  elif args.test_type == 'blink':
    cmd = [PYTHON_CMD, path.join(args.src_dir, BLINK_TEST_SCRIPT)]
    cmd += generate_blink_arguments(args)
    total_shards = '--total-shards'
    shard_index = '--shard-index'
  elif args.test_type == 'aquarium':
    cmd = [path.join(args.build_dir, AQUARIUM_TEST_CMD)]
    cmd += generate_aquarium_arguments(args)
  else:
    if args.test_type == 'dawn':
      if args.backend.startswith('end2end'):
        cmd = [path.join(args.build_dir, DAWN_END2END_TEST_CMD)]
      elif args.backend == 'perf':
        cmd = [path.join(args.build_dir, DAWN_PERF_TEST_CMD)]
    elif args.test_type == 'angle':
      if args.backend == 'end2end':
        cmd = [path.join(args.build_dir, ANGLE_END2END_TEST_CMD)]
      elif args.backend == 'perf':
        cmd = [path.join(args.build_dir, ANGLE_PERF_TEST_CMD)]
    elif args.test_type == 'gpu':
      if args.backend == 'gl':
        cmd = [path.join(args.build_dir, GL_TEST_CMD)]
      elif args.backend == 'vulkan':
        cmd = [path.join(args.build_dir, VULKAN_TEST_CMD)]
    cmd += generate_gtest_arguments(args)
    total_shards = '--test-launcher-total-shards'
    shard_index = '--test-launcher-shard-index'
  cmd += extra_args

  args.log_file = '%s_%s.log' % (args.test_type, args.backend)
  args.result_file = '%s_%s.json' % (args.test_type, args.backend)

  if args.shard == 1:
    execute_shard(cmd, args)
  else:
    cmd.append('%s=%d' % (total_shards, args.shard))
    if args.index >= 0:
      cmd.append('%s=%d' % (shard_index, args.index))
      execute_shard(cmd, args)
      print(' '.join(cmd))
    else:
      for i in range(0, args.shard):
        args.index = i
        new_cmd = cmd[:]
        new_cmd.append('%s=%d' % (shard_index, args.index))
        execute_shard(new_cmd, args)

if __name__ == '__main__':
  sys.exit(main())
