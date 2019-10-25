#!/usr/bin/env python

import argparse
import sys

from util.gpu_test_util import *
from os import path

PACK_SCRIPT = path.join('tools', 'mb', 'mb.py')

CHROME_REMOTE_NAME = 'origin'
CHROME_REMOTE_BRANCH = 'master'

BUILD_TARGETS = [
  'chrome',
  'angle_end2end_tests',
  'angle_perftests',
]

TARGET_CONTENTS = {
  'win':[
    'angle_end2end_tests.exe',
    'angle_perftests.exe',
    'angle_util.dll',
  ],
  'linux':[
    'angle_end2end_tests',
    'angle_perftests',
    'libangle_util.so',
  ],
  'mac':[
    'angle_end2end_tests',
    'angle_perftests',
    'libangle_util.dylib',
  ],
}

PATTERN_REVISION = r'^Cr-Commit-Position: refs/heads/master@{#(\d+)}$'

def parse_arguments():
  parser = argparse.ArgumentParser(
      description='Chrome build tools',
      formatter_class=argparse.RawTextHelpFormatter)
  parser.add_argument('commands', nargs='*',
      choices=['sync', 'build', 'pack', 'rev'], default='build',
      help='Specify the command. Default is \'build\'.\n\n'\
           'sync   :  fetch latest source code\n'\
           'build  :  build targets\n'\
           'pack   :  package executables that can run independently\n'\
           'rev    :  get Chrome revision\n\n')
  parser.add_argument('--build', '-b',
      choices=['release', 'debug', 'default'], default='release',
      help='Build type. Default is \'release\'.\n'\
           'release/debug/default assume that the binaries are\n'\
           'generated into out/Release or out/Debug or out/Default.\n\n')
  parser.add_argument('--dir', '-d', default='.',
      help='Chrome source directory.\n\n')
  parser.add_argument('--pack-dir', '-p', default='.',
      help='Destnation directory, used by the command \'pack\'.\n\n')
  args = parser.parse_args()

  if not isinstance(args.commands, list):
    args.commands = [args.commands]
  args.dir = path.abspath(args.dir)
  args.pack_dir = path.abspath(args.pack_dir)
  args.build_dir = path.join('out', args.build.title())
  assert not 'pack' in args.commands or args.dir != args.pack_dir
  return args


def sync(args):
  execute_command(['git', 'fetch', CHROME_REMOTE_NAME],
                  dir=args.dir)
  execute_command(['git', 'rebase', CHROME_REMOTE_NAME + '/' + CHROME_REMOTE_BRANCH],
                  dir=args.dir)
  try:
    execute_command(['gclient', 'sync', '-D'],
                    print_log=False, return_log=True,
                    dir=args.dir)
  except CalledProcessError as e:
    print(e.cmd)
    print(e.output)
    raise e


def build(args):
  build_args = ['enable_nacl=false', 'blink_symbol_level=0']
  if args.build == 'debug':
    build_args.extend(['is_debug=true'])
  else:
    build_args.extend(['is_debug=false', 'dcheck_always_on=true'])

  if args.build == 'default':
    build_args.extend(['is_component_build=false'])
  else:
    build_args.extend(['is_component_build=true'])

  if args.build == 'debug':
    build_args.extend(['symbol_level=2'])
  elif args.build == 'release':
    build_args.extend(['symbol_level=1'])
  elif args.build == 'default':
    build_args.extend(['symbol_level=0'])

  env = get_env()
  env.pop('PKG_CONFIG_PATH', None)
  execute_command(['gn', 'gen', args.build_dir, '--args=' + ' '.join(build_args)],
                  dir=args.dir, env=env)

  build_cmd = ['autoninja', '-C', args.build_dir]
  for target in BUILD_TARGETS:
    cmd = build_cmd[:]
    cmd.append(target)
    execute_command(cmd, dir=args.dir, env=env)


def package(args):
  env = get_env()
  env.pop('PKG_CONFIG_PATH', None)
  pack_file = path.join(args.dir, 'tmp.zip')
  execute_command([PYTHON_CMD, PACK_SCRIPT, 'zip', args.build_dir, 'telemetry_gpu_integration_test', pack_file],
                  dir=args.dir, env=env)
  unzip(pack_file, args.pack_dir, remove_src=True)

  for content in TARGET_CONTENTS[get_osname()]:
    copy(path.join(args.dir, args.build_dir, content),
         path.join(args.pack_dir, args.build_dir))

  if is_linux():
    for target in BUILD_TARGETS:
      chmod(path.join(args.pack_dir, args.build_dir, target), 755)


def get_revision(args):
  try:
    for i in range(0, 3):
      log = execute_command(['git', 'log', 'HEAD~%d' % i, '-1'],
                            print_log=False, return_log=True, dir=args.dir)
      log_lines = log.split('\n')
      for j in range(len(log_lines)-1, -1, -1):
        match = re_match(PATTERN_REVISION, log_lines[j])
        if match:
          return match.group(1)
  except CalledProcessError:
    pass
  return ''


def main():
  args = parse_arguments()
  for command in args.commands:
    if command == 'sync':
      sync(args)
    elif command == 'build':
      build(args)
    elif command == 'pack':
      package(args)
    elif command == 'rev':
      print(get_revision(args))

  return 0


if __name__ == '__main__':
  sys.exit(main())
