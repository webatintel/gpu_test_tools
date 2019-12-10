#!/usr/bin/env python

import argparse
import sys

from util.base_util import *
from os import path

CHROME_PACK_SCRIPT = path.join('tools', 'mb', 'mb.py')

CHROME_REMOTE_NAME = 'origin'
CHROME_REMOTE_BRANCH = 'master'

AQUARIUM_REMOTE_NAME = 'origin'
AQUARIUM_REMOTE_BRANCH = 'master'

DAWN_REMOTE_NAME = 'origin'
DAWN_REMOTE_BRANCH = 'master'

CHROME_BUILD_TARGETS = [
  'chrome',
  'angle_end2end_tests',
  'angle_perftests',
]

AQUARIUM_BUILD_TARGETS = [
  'aquarium',
]

CHROME_TARGET_DEPENDENCIES = {
  'win': [
    'angle_end2end_tests.exe',
    'angle_end2end_tests.exe.pdb',
    'angle_perftests.exe',
    'angle_perftests.exe.pdb',
    'angle_util.dll',
  ],
  'linux': [
    'angle_end2end_tests',
    'angle_perftests',
    'libangle_util.so',
  ],
  'mac': [
    'angle_end2end_tests',
    'angle_perftests',
    'libangle_util.dylib',
  ],
}

AQUARIUM_TARGET_DEPENDENCIES = {
  'win':[
    'aquarium.exe',
    'aquarium.exe.pdb',
  ],
  'linux':[
    'aquarium',
  ],
  'mac':[
    'aquarium',
  ],
}

AQUARIUM_ASSETS = [
  'assets',
  'shaders',
]

def parse_arguments():
  parser = argparse.ArgumentParser(
      description='Build tools',
      formatter_class=argparse.RawTextHelpFormatter)
  parser.add_argument('project', nargs='?',
      choices=['chrome', 'aquarium', 'mesa'], default='chrome',
      help='Specify the project. Default is \'chrome\'.\n\n')
  parser.add_argument('--dir', '-d', default='.',
      help='Project source directory.\n\n')
  parser.add_argument('--type', '-t', nargs='*',
      choices=['release', 'debug', 'default', 'official'], default='release',
      help='Build type. Default is \'release\'.\n'\
           'release/debug/default assume that the binaries are\n'\
           'generated into out/Release or out/Debug or out/Default.\n\n')
  parser.add_argument('--update', '-u', action='store_true',
      help='Fetch from origin and rebase current branch,\n'\
           'then synchronize the dependencies before building.\n\n')
  parser.add_argument('--sync', '-s', action='store_true',
      help='Synchronize the dependencies before building.\n\n')
  parser.add_argument('--install', '-i', action='store_true',
      help='Install the package after building.\n\n')
  parser.add_argument('--pack', '-p',
      help='Package the binaries to a directory after building.\n\n')
  parser.add_argument('--zip', '-z',
      help='Package the binaries to a zip file after building.\n\n')
  parser.add_argument('--prefix',
      help='Where the package to be installed\n\n')
  parser.add_argument('--iris', action='store_true',
      help='Build Iris driver.\n\n')
  args = parser.parse_args()

  if not isinstance(args.type, list):
    args.type = [args.type]

  if (args.pack or args.zip) and len(args.type) > 1:
    raise Exception('packaging do not support multiple build types')

  args.dir = path.abspath(args.dir)
  if args.pack:
    args.pack = path.abspath(args.pack)
  if args.zip:
    args.zip = path.abspath(args.zip)
  if args.project == 'aquarium':
    args.dawn_dir = path.join(args.dir, 'third_party', 'dawn')
  if args.project == 'mesa':
    if not args.prefix:
      args.prefix = '/home/work/workspace/env/mesa'
  return args


def update_chrome(args):
  execute_command(['git', 'fetch', CHROME_REMOTE_NAME],
                  dir=args.dir)
  execute_command(['git', 'rebase', CHROME_REMOTE_NAME + '/' + CHROME_REMOTE_BRANCH],
                  dir=args.dir)


def sync_chrome(args):
  execute_command(['gclient', 'sync', '-D'],
                  dir=args.dir)


def build_chrome(args):
  build_args = ['proprietary_codecs=true',
                'ffmpeg_branding="Chrome"']

  if args.build_type == 'official':
    build_args.extend(['is_official_build=true'])
  elif args.build_type == 'default':
    build_args.extend(['is_debug=false',
                       'is_component_build=false',
                       'symbol_level=1',
                       'dcheck_always_on=true',
                       'build_angle_gles1_conform_tests=true',
                       'internal_gles2_conform_tests=true'])
  else:
    build_args.extend(['is_component_build=true',
                       'enable_nacl=false',
                       'blink_symbol_level=0'])
    if args.build_type == 'debug':
      build_args.extend(['is_debug=true',
                         'symbol_level=2'])
    else:
      build_args.extend(['is_debug=false',
                         'symbol_level=1',
                         'dcheck_always_on=true'])

  env = get_env()
  env.pop('PKG_CONFIG_PATH', None)
  execute_command(['gn', 'gen', args.build_dir, '--args=' + ' '.join(build_args)],
                  dir=args.dir, env=env)

  build_cmd = ['autoninja', '-C', args.build_dir]
  for target in CHROME_BUILD_TARGETS:
    cmd = build_cmd[:]
    cmd.append(target)
    execute_command(cmd, dir=args.dir, env=env)


def pack_chrome(args):
  env = get_env()
  env.pop('PKG_CONFIG_PATH', None)
  zip_file = path.join(args.dir, random_string(8) + '.zip')
  execute_command([PYTHON_CMD, CHROME_PACK_SCRIPT, 'zip', args.build_dir, 'telemetry_gpu_integration_test', zip_file],
                  dir=args.dir, env=env)

  if args.pack:
    pack_dir = args.pack
  else:
    pack_dir = path.join(args.dir, random_string(8))
  unzip(zip_file, pack_dir)
  remove(zip_file)

  for content in CHROME_TARGET_DEPENDENCIES[get_osname()]:
    copy(path.join(args.dir, args.build_dir, content),
         path.join(pack_dir, args.build_dir))

  if is_linux():
    for target in CHROME_BUILD_TARGETS:
      chmod(path.join(pack_dir, args.build_dir, target), 755)

  if args.zip:
    zip(args.zip, pack_dir)
  if not args.pack:
    remove(pack_dir)


def update_aquarium(args):
  execute_command(['git', 'fetch', AQUARIUM_REMOTE_NAME],
                  dir=args.dir)
  execute_command(['git', 'rebase', AQUARIUM_REMOTE_NAME + '/' + AQUARIUM_REMOTE_BRANCH],
                  dir=args.dir)


def sync_aquarium(args):
  execute_command(['git', 'checkout', 'master'],
                  dir=args.dawn_dir)
  execute_command(['gclient', 'sync', '-D'],
                  dir=args.dir)
  execute_command(['git', 'checkout', 'upstream'],
                  dir=args.dawn_dir)
  execute_command(['git', 'fetch', DAWN_REMOTE_NAME],
                  dir=args.dawn_dir)
  execute_command(['git', 'rebase', DAWN_REMOTE_NAME + '/' + DAWN_REMOTE_BRANCH],
                  dir=args.dawn_dir)


def build_aquarium(args):
  build_args = []
  if args.build_type == 'debug':
    build_args.extend(['is_debug=true'])
  else:
    build_args.extend(['is_debug=false'])
  execute_command(['gn', 'gen', args.build_dir, '--args=' + ' '.join(build_args)],
                  dir=args.dir)

  build_cmd = ['autoninja', '-C', args.build_dir]
  for target in AQUARIUM_BUILD_TARGETS:
    cmd = build_cmd[:]
    cmd.append(target)
    execute_command(cmd, dir=args.dir)


def pack_aquarium(args):
  if args.pack:
    pack_dir = args.pack
  else:
    pack_dir = path.join(args.dir, random_string(8))
  mkdir(path.join(pack_dir, args.build_dir))

  for content in AQUARIUM_ASSETS:
    copy(path.join(args.dir, content),
         path.join(pack_dir))

  for content in AQUARIUM_TARGET_DEPENDENCIES[get_osname()]:
    copy(path.join(args.dir, args.build_dir, content),
         path.join(pack_dir, args.build_dir))

  if is_linux():
    for target in AQUARIUM_BUILD_TARGETS:
      chmod(path.join(pack_dir, args.build_dir, target), 755)

  if args.zip:
    zip(args.pack, pack_dir)
  if not args.pack:
    remove(pack_dir)

def build_mesa(args):
  build_args = ['-Dprefix=' + args.prefix,
                '-Dplatforms=x11,drm',
                '-Ddri-drivers=i915,i965',
                '-Dvulkan-drivers=intel',
                '-Dgallium-drivers=' + ('iris' if args.iris else ''),
                '-Ddri3=true',
                '-Dgles1=true',
                '-Dgles2=true',
                '-Dgbm=true',
                '-Dshared-glapi=true']

  meson_cmd = ['meson', args.build_dir]
  meson_cmd.extend(build_args)
  execute_command(meson_cmd, dir=args.dir)

  build_cmd = ['ninja', '-C', args.build_dir]
  if args.install:
    build_cmd.append('install')
  execute_command(build_cmd, dir=args.dir)


def main():
  args = parse_arguments()
  if args.project == 'mesa':
    args.build_dir = 'out'
    build_mesa(args)
    return 0

  if args.update:
    if args.project == 'chrome':
      update_chrome(args)
    elif args.project == 'aquarium':
      update_aquarium(args)

  if args.update or args.sync:
    if args.project == 'chrome':
      sync_chrome(args)
    elif args.project == 'aquarium':
      sync_aquarium(args)

  for build_type in args.type:
    args.build_type = build_type
    args.build_dir = path.join('out', build_type.title())
    if args.project == 'chrome':
      build_chrome(args)
    elif args.project == 'aquarium':
      build_aquarium(args)
  
  if args.pack or args.zip:
    if args.project == 'chrome':
      pack_chrome(args)
    elif args.project == 'aquarium':
      pack_aquarium(args)

  return 0


if __name__ == '__main__':
  sys.exit(main())
