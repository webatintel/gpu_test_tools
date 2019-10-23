#!/usr/bin/env python

import argparse
import sys

from gpu_test_util import *
from os import path

AQUARIUM_REMOTE_NAME = 'origin'
AQUARIUM_REMOTE_BRANCH = 'master'

DAWN_REMOTE_NAME = 'origin'
DAWN_REMOTE_BRANCH = 'master'

BUILD_TARGETS = [
  'aquarium',
]

ASSET_CONTENTS = [
  'assets',
  'shaders'
]

TARGET_CONTENTS = {
  'win':[
    'aquarium.exe',
  ],
  'linux':[
    'aquarium',
  ],
  'mac':[
    'aquarium',
  ],
}

def parse_arguments():
  parser = argparse.ArgumentParser(
      description='Aquarium build tools',
      formatter_class=argparse.RawTextHelpFormatter)
  parser.add_argument('commands', nargs='*',
      choices=['sync', 'gen', 'build', 'pack', 'rev'], default='build',
      help='Specify the command. Default is \'build\'.\n\n'\
           'sync   :  fetch latest source code\n'\
           'gen    :  generate ninja files\n'\
           'build  :  build targets\n'\
           'pack   :  package executables that can run independently\n'\
           'rev    :  get the commit ID of Aquarium and Dawn\n\n')
  parser.add_argument('--build', '-b',
      choices=['release', 'debug', 'default'], default='release',
      help='Build type. Default is \'release\'.\n'\
           'release/debug/default assume that the binaries are\n'\
           'generated into out/Release or out/Debug or out/Default.\n\n')
  parser.add_argument('--dir', '-d', default='.',
      help='Aquarium source directory.\n\n')
  parser.add_argument('--pack-dir', '-p', default='.',
      help='Destnation directory, used by the command \'pack\'.\n\n')
  args = parser.parse_args()

  if not isinstance(args.commands, list):
    args.commands = [args.commands]
  args.dir = path.abspath(args.dir)
  args.dawn_dir = path.join(args.dir, 'third_party', 'dawn')
  args.pack_dir = path.abspath(args.pack_dir)
  args.build_dir = path.join('out', args.build.title())
  assert not 'pack' in args.commands or args.dir != args.pack_dir
  return args


def sync(args):
  execute_command(['git', 'fetch', AQUARIUM_REMOTE_NAME],
                  dir=args.dir)
  execute_command(['git', 'rebase', AQUARIUM_REMOTE_NAME + '/' + AQUARIUM_REMOTE_BRANCH],
                  dir=args.dir)
  execute_command(['git', 'checkout', 'master'],
                  dir=args.dawn_dir)
  try:
    execute_command(['gclient', 'sync', '-D'],
                    print_log=False, return_log=True,
                    dir=args.dir)
  except CalledProcessError as e:
    print(e.cmd)
    print(e.output)
    raise e
  execute_command(['git', 'fetch', DAWN_REMOTE_NAME],
                  dir=args.dawn_dir)
  execute_command(['git', 'checkout', 'upstream'],
                  dir=args.dawn_dir)
  execute_command(['git', 'rebase', DAWN_REMOTE_NAME + '/' + DAWN_REMOTE_BRANCH],
                  dir=args.dawn_dir)


def generate(args):
  build_args = []
  if args.build == 'debug':
    build_args.extend(['is_debug=true'])
  else:
    build_args.extend(['is_debug=false'])

  execute_command(['gn', 'gen', args.build_dir, '--args=' + ' '.join(build_args)],
                  dir=args.dir)


def build(args):
  build_cmd = ['autoninja', '-C', args.build_dir]
  for target in BUILD_TARGETS:
    cmd = build_cmd[:]
    cmd.append(target)
    execute_command(cmd, dir=args.dir)


def package(args):
  mkdir(path.join(args.pack_dir, args.build_dir))

  for content in ASSET_CONTENTS:
    copy(path.join(args.dir, content),
         path.join(args.pack_dir))

  for content in TARGET_CONTENTS[get_osname()]:
    copy(path.join(args.dir, args.build_dir, content),
         path.join(args.pack_dir, args.build_dir))

  if is_linux():
    for target in BUILD_TARGETS:
      chmod(path.join(args.pack_dir, args.build_dir, target), 755)


def get_revision(args):
  try:
    aquarium_revision = execute_command(['git', 'rev-parse', 'HEAD'],
                                        print_log=False, return_log=True, dir=args.dir)
    dawn_revision = execute_command(['git', 'rev-parse', 'HEAD'],
                                    print_log=False, return_log=True, dir=args.dawn_dir)
    if aquarium_revision and dawn_revision:
      return '%s_%s' % (aquarium_revision[0:6], dawn_revision[0:6])
  except CalledProcessError:
    pass
  return ''


def main():
  args = parse_arguments()
  for command in args.commands:
    if command == 'sync':
      sync(args)
    elif command == 'gen':
      generate(args)
    elif command == 'build':
      build(args)
    elif command == 'pack':
      package(args)
    elif command == 'rev':
      print(get_revision(args))

  return 0


if __name__ == '__main__':
  sys.exit(main())
