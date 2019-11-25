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
  parser.add_argument('command', nargs='*',
      choices=['update', 'sync', 'build', 'pack', 'rev'], default='build',
      help='Specify the command. Default is \'build\'.\n'\
           'Can specify multiple commands at the same time.\n\n'\
           'update :  update the Chrome source and rebase current branch\n'\
           'sync   :  run gclient sync\n'\
           'build  :  build all targets\n'\
           'pack   :  package executables that can run independently\n'\
           'rev    :  get Chrome revision\n\n')
  parser.add_argument('--type', '-t', nargs='*',
      choices=['release', 'debug', 'default', 'official'], default='release',
      help='Browser type. Default is \'release\'.\n'\
           'release/debug/default assume that the binaries are\n'\
           'generated into out/Release or out/Debug or out/Default.\n\n')
  parser.add_argument('--dir', '-d', default='.',
      help='Chrome source directory.\n\n')
  parser.add_argument('--pack-dir', '-p',
      help='Package the binaries to a directory.\n\n')
  parser.add_argument('--zip-file', '-z',
      help='Package the binaries to a zip file.\n\n')
  args = parser.parse_args()

  if not isinstance(args.command, list):
    args.command = [args.command]
  if not isinstance(args.type, list):
    args.type = [args.type]

  args.dir = path.abspath(args.dir)
  return args


def update(args):
  execute_command(['git', 'fetch', CHROME_REMOTE_NAME],
                  dir=args.dir)
  execute_command(['git', 'rebase', CHROME_REMOTE_NAME + '/' + CHROME_REMOTE_BRANCH],
                  dir=args.dir)


def sync(args):
  execute_command(['gclient', 'sync', '-D'],
                  dir=args.dir)


def build(args):
  build_args = ['proprietary_codecs=true',
                'ffmpeg_branding="Chrome"']

  if args.build_type == 'official':
    build_args.extend(['is_official_build=true'])
  else:
    build_args.extend(['strip_absolute_paths_from_debug_symbols=true',
                       'build_angle_gles1_conform_tests=true',
                       'internal_gles2_conform_tests=true'])

    if args.build_type == 'debug':
      build_args.extend(['is_debug=true',
                         'symbol_level=2'])
    else:
      build_args.extend(['is_debug=false',
                         'symbol_level=1',
                         'dcheck_always_on=true'])

    if args.build_type == 'debug' or args.build_type == 'release':
      build_args.extend(['is_component_build=true'])
    else:
      build_args.extend(['is_component_build=false'])

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
  if args.zip_file:
    zip_file = args.zip_file
  else:
    zip_file = path.join(args.dir, 'tmp.zip')
  execute_command([PYTHON_CMD, PACK_SCRIPT, 'zip', args.build_dir, 'telemetry_gpu_integration_test', zip_file],
                  dir=args.dir, env=env)
  if not args.pack_dir:
    return

  unzip(zip_file, args.pack_dir, remove_src=(not args.zip_file))

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
  for command in args.command:
    if command == 'update':
      update(args)
    elif command == 'sync':
      sync(args)
    elif command == 'build':
      for build_type in args.type:
        args.build_type = build_type
        args.build_dir = path.join('out', build_type.title())
        build(args)
    elif command == 'pack':
      assert len(args.type) == 1
      args.build_dir = path.join('out', args.type[0].title())

      assert args.pack_dir or args.zip_file
      if args.pack_dir:
        args.pack_dir = path.abspath(args.pack_dir)
        assert args.dir != args.pack_dir
      if args.zip_file:
        args.zip_file = path.abspath(args.zip_file)
      package(args)
    elif command == 'rev':
      print(get_revision(args))

  return 0


if __name__ == '__main__':
  sys.exit(main())
