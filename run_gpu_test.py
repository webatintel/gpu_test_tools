#!/usr/bin/env python3

import argparse

from util.base_util import *
from util.file_util import *

CONTENT_TEST_SCRIPT = path.join('content', 'test', 'gpu', 'run_gpu_integration_test.py')
WEBGL_TEST_OUTPUT   = path.join('content', 'test', 'data', 'gpu', 'webgl_conformance_tests_output.json')
WEBGL2_TEST_OUTPUT  = path.join('content', 'test', 'data', 'gpu', 'webgl2_conformance_tests_output.json')

BLINK_TEST_SCRIPT  = path.join('third_party', 'blink', 'tools', 'run_web_tests.py')
WEBGPU_EXPECTATION = path.join('third_party', 'blink', 'web_tests', 'WebGPUExpectations')

def parse_arguments():
  config = load_tryjob_config()
  module_to_backend, backend_set = defaultdict(list), set()
  for _, test_type, _, _ in config['tryjob']:
    module_to_backend[test_type[0]].append(test_type[1])
    backend_set.add(test_type[1])

  backend_help = ''
  for module in module_to_backend.keys():
    backend_help += '%s: %s\n' % ('{:<10}'.format(module), ', '.join(module_to_backend[module]))

  parser = argparse.ArgumentParser(
      description='Run single test.\n\n',
      formatter_class=argparse.RawTextHelpFormatter)
  parser.add_argument('module', choices=sorted(list(module_to_backend.keys())),
      help='The test to run.\n\n')
  parser.add_argument('backend', choices=sorted(list(backend_set)),
      help='The backend of test. The backends that are supported by each test are:\n\n' + backend_help)
  parser.add_argument('--src-dir', '--dir', '-d', default='.',
      help='The source directory. Default is current directory.\n\n')
  parser.add_argument('--target', '-t', default='Default',
      help='The target build directory under "out/". Default is "Default".\n\n')
  parser.add_argument('--filter', '-f', nargs='+',
      help='The keyword to match the test cases. You can specify multiple.\n\n')
  parser.add_argument('--shard', '-s', type=int,
      help='Total number of shards being used for this test.\n'\
           'Default shard number is the same as official trybot.\n\n')
  parser.add_argument('--index', '-i', type=int,
      help='Shard index of this test.\n'\
           'By default, all shards will be run in sequence.\n\n')
  parser.add_argument('--repeat', '-r', default=1, type=int,
      help='The number of times to repeat running this test.\n'\
           'For multiple shards, the running sequence will be shard0 * N times, shard1 * N times ...\n\n')
  parser.add_argument('--print-log', '-p', action='store_true',
      help='Print full test log when test is running.\n\n')
  parser.add_argument('--dry-run', nargs='?', const=get_platform(), choices=['win', 'linux'],
      help='Go through the process but do not run test actually.\n'\
           'You can specify the platform (win|linux) or leave it empty to use current platform.\n\n')
  args, extra_args = parser.parse_known_args()

  if not args.backend in module_to_backend[args.module]:
    raise Exception('The backends that are supported by %s test are %s' %
                    (args.module, ', '.join(module_to_backend[args.module])))

  # ['content', 'webgl_d3d11'] => ['content', 'content_webgl', 'content_webgl_d3d11']
  test_keys = [args.module] + args.backend.split('_')
  args.test_keys = ['_'.join(test_keys[0:i]) for i in range(1, len(test_keys)+1)]

  if args.shard is None:
    if args.filter:
      args.shard = 1
    else:
      key = find_match(args.test_keys, lambda x: x in config['shards'])
      args.shard = config['shards'][key] if key else 1

  if args.filter and args.module in ['blink', 'aquarium']:
    raise Exception('Do not support filter in %s test' % args.module)
  if args.shard > 1 and args.module in ['aquarium']:
    raise Exception('Do not support shard in %s test' % args.module)
  if args.shard <= 0:
    raise Exception('Invalid shard number: ' + args.shard)
  if args.index and (args.index < 0 or args.index >= args.shard):
    raise Exception('Invalid index number: ' + args.index)
  if args.repeat < 1:
    raise Exception('Invalid repeat number: ' + args.repeat)

  index = index_match(config['tryjob'], lambda x: x[1] == [args.module, args.backend])
  args.log_file    = config['tryjob'][index][0] + '.log'
  args.result_file = config['tryjob'][index][0] + '.json'

  args.test_command = config['test_command']
  args.test_args    = config['test_args']
  args.browser_args = config['browser_args']

  if args.filter:
    for i in range(len(args.filter)):
      args.filter[i] = ('' if args.filter[i].startswith('*') else '*') + args.filter[i]
      args.filter[i] += ('' if args.filter[i].endswith('*') else '*')

  args.src_dir = path.abspath(args.src_dir)
  if path.basename(args.src_dir) == 'chromium' and path.exists(path.join(args.src_dir, 'src')):
    args.src_dir = path.join(args.src_dir, 'src')
  args.target_dir = path.join(args.src_dir, 'out', args.target)
  return args, extra_args


def execute_shard(args, cmd):
  env = get_env()
  if is_win():
    for var in ['http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY']:
      env.pop(var, None)

  log_name, log_ext = path.splitext(args.log_file)
  result_name, result_ext = path.splitext(args.result_file)
  shard_ext = '.shard' + format(args.index, '02d') if args.shard > 1 else ''

  for n in range(args.repeat):
    repeat_ext = '.' + format(n, '03d') if args.repeat > 1 else ''
    log_file = log_name + shard_ext + repeat_ext + log_ext
    if args.module in ['content', 'blink']:
      result_file = result_name + shard_ext + repeat_ext + result_ext
      result_arg = ['--write-full-results-to=' + result_file]
    else:
      result_arg = []

    if args.dry_run:
      print('\n' + ' '.join(cmd + result_arg))
      continue
    try:
      execute_log(cmd + result_arg, log_file, print_log=args.print_log, env=env)
    except CalledProcessError:
      pass


def main():
  def get_executable(file_path):
    return file_path + ('.exe' if sys.platform == 'win32' else '')

  args, extra_args = parse_arguments()

  # Generate command
  if args.module == 'content':
    cmd = ['vpython', path.join(args.src_dir, CONTENT_TEST_SCRIPT)]
  elif args.module == 'blink':
    cmd = ['vpython', path.join(args.src_dir, BLINK_TEST_SCRIPT)]
  else:
    key = find_match(args.test_keys, lambda x: x in args.test_command)
    cmd = [path.join(args.target_dir, get_executable(args.test_command[key]))]

  # Read default arguments from the configuration file
  test_args, browser_args = [], []
  platform = args.dry_run if args.dry_run else get_platform()
  for key in args.test_keys + ['%s_%s' % (x, platform) for x in args.test_keys]:
    test_args += args.test_args.get(key, [])
    browser_args += args.browser_args.get(key, [])

  # Add variable arguments
  if args.module == 'content':
    browser_executable = get_executable(path.join(args.target_dir, 'chrome'))
    test_args += ['--browser=exact', '--browser-executable=' + browser_executable]
    if args.backend.startswith('webgl'):
      index = index_match(test_args, lambda x: x.startswith('--read-abbreviated-json-results-from='))
      assert index > 0
      if args.backend.startswith('webgl2'):
        test_args[index] += path.join(args.src_dir, WEBGL2_TEST_OUTPUT)
      else:
        test_args[index] += path.join(args.src_dir, WEBGL_TEST_OUTPUT)
    elif args.backend == 'info':
      index = index_match(test_args, lambda x: x.startswith('--expected-device-id'))
      assert index > 0
      gpu_info = get_gpu_info()
      test_args[index+1] = gpu_info.device_id
  elif args.module == 'blink':
    test_args += ['--target=' + args.target]
    if args.backend.startswith('webgpu'):
      index = index_match(test_args, lambda x: x.startswith('--additional-expectations='))
      assert index > 0
      test_args[index] += path.join(args.src_dir, WEBGPU_EXPECTATION)

  # Add filter
  if args.filter:
    if args.module == 'content':
      test_args += ['--test-filter=' + '::'.join(args.filter)]
    elif args.module in ['gpu', 'angle', 'dawn']:
      index = index_match(test_args, lambda x: x.startswith('--gtest_filter='))
      if index < 0:
        test_args += ['--gtest_filter=' + ':'.join(args.filter)]
      else:
        test_args[index] = '--gtest_filter=' + ':'.join(args.filter)

  # Integrate browser arguments
  if args.module == 'content':
    test_args += ['--extra-browser-args=' + ' '.join(browser_args)]
  elif args.module == 'blink':
    test_args += ['--additional-driver-flag=' + arg for arg in browser_args]
  else:
    assert not browser_args

  cmd += test_args + extra_args
  if args.shard == 1:
    execute_shard(args, cmd)
  else:
    if args.module in ['content', 'blink']:
      cmd += ['--total-shards=%d' % args.shard]
      shard_index_flag = '--shard-index'
    elif args.module in ['gpu', 'angle', 'dawn']:
      cmd += ['--test-launcher-total-shards=%d' % args.shard]
      shard_index_flag = '--test-launcher-shard-index'

    if args.index is None:
      for i in range(args.shard):
        args.index = i
        execute_shard(args, cmd + ['%s=%d' % (shard_index_flag, args.index)])
    else:
      execute_shard(args, cmd + ['%s=%d' % (shard_index_flag, args.index)])


if __name__ == '__main__':
  sys.exit(main())
