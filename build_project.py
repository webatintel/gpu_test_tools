#!/usr/bin/env python

import argparse
import os
import random
import string
import sys

from os import path
from util.base_util import *
from util.file_util import *
from util.system_util import *

PYTHON_CMD = 'python'
CHROME_PACK_SCRIPT = path.join('tools', 'mb', 'mb.py')

CHROME_BUILD_TARGETS = [
  'chrome',
  'dawn_end2end_tests',
  'dawn_perf_tests',
  'angle_end2end_tests',
  'angle_perftests',
  'gl_tests',
  'vulkan_tests',
  'imagediff',
  'content_shell',
  'trace_processor_shell',
]

CHROME_BUILD_TARGETS_LINUX = [
  'minidump_stackwalk',
]

DAWN_BUILD_TARGETS = [
  'dawn_end2end_tests',
  'dawn_perf_tests',
]

ANGLE_BUILD_TARGETS = [
  'angle_end2end_tests',
  'angle_perftests',
]

AQUARIUM_BUILD_TARGETS = [
  'aquarium',
]

CHROME_TARGET_DEPENDENCIES = {
  'win': [
    'dawn_end2end_tests.exe',
    'dawn_perftests.exe',
    'angle_end2end_tests.exe',
    'angle_perftests.exe',
    'gl_tests.exe',
    'vulkan_tests.exe',
    'image_diff.exe',
    'content_shell.exe',
    'trace_processor_shell.exe',
    'angle_util.dll',
    'dawn_end2end_tests.exe.pdb',
    'dawn_perftests.exe.pdb',
    'angle_end2end_tests.exe.pdb',
    'angle_perftests.exe.pdb',
    'gl_tests.exe.pdb',
    'vulkan_tests.exe.pdb',
    'image_diff.exe.pdb',
    'content_shell.exe.pdb',
    'trace_processor_shell.exe.pdb',
  ],
  'linux': [
    'dawn_end2end_tests',
    'dawn_perftests',
    'angle_end2end_tests',
    'angle_perftests',
    'gl_tests',
    'vulkan_tests',
    'image_diff',
    'content_shell',
    'trace_processor_shell',
    'minidump_dump',
    'minidump_stackwalk',
    'libangle_util.so',
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
}

AQUARIUM_ASSETS = [
  'assets',
  'shaders',
]

PATTERN_COMMIT = r'^commit (\w+)$'
PATTERN_DAWN_REVISION = r'  \'dawn_revision\': \'\w+\''

def random_string(size):
  return ''.join(random.choice(string.ascii_lowercase) for i in range(size))

def parse_arguments():
  parser = argparse.ArgumentParser(
      description='Build project',
      formatter_class=argparse.RawTextHelpFormatter)
  parser.add_argument('project', nargs='?',
      choices=['chrome', 'dawn', 'angle', 'aquarium', 'mesa'], default='chrome',
      help='The project to build. Default is "chrome".\n\n')
  parser.add_argument('--dir', '-d', default='.',
      help='Project source directory.\n\n')
  parser.add_argument('--target', '-t', nargs='*',
      choices=['Default', 'Release', 'Debug'], default=['Default'],
      help='The target build directory under out/, you can specify multiple. Default is "Default".\n'\
           'Default(any suffix) : For Chrome, the build arguments are same as official trybot.\n'\
           '                      For others, it\'s same as release build.\n'\
           'Debug(any suffix)   : the debug build.\n'\
           'any other targets   : the release build.\n\n')
  parser.add_argument('--update', '-u', action='store_true',
      help='Fetch from origin and rebase to master, then synchronize the dependencies before building.\n\n')
  parser.add_argument('--pack', '-p',
      help='Package the binaries to a directory after building.\n'\
           'For mesa, it equals to --prefix.\n\n')
  parser.add_argument('--zip', '-z',
      help='Package the binaries to a zip file after building.\n\n')
  args = parser.parse_args()

  if args.pack or args.zip:
    if len(args.target) > 1:
      raise Exception('Do not support to package multiple targets')
    if not args.project in ['chrome', 'aquarium', 'mesa']:
      raise Exception('Do not support to package ' + args.project)

  args.dir = path.abspath(args.dir)
  if args.pack:
    args.pack = path.abspath(args.pack)
  if args.zip:
    args.zip = path.abspath(args.zip)
  return args


def sync_aquarium(args):
  dawn_dir = path.join(args.dir, 'third_party', 'dawn')
  execute_command(['git', 'fetch', 'origin'], dir=dawn_dir)
  execute_command(['git', 'rebase', 'origin/master'], dir=dawn_dir)
  log = execute_command(['git', 'log', '-1'], print_log=False, return_log=True, dir=dawn_dir)
  dawn_revision = None
  for line in log.splitlines():
    match = re_match(PATTERN_COMMIT, line)
    if match:
      dawn_revision = match.group(1)
      break
  if not dawn_revision:
    raise Exception('Dawn revision not found')

  deps_file = path.join(args.dir, 'DEPS')
  deps_contents = []
  for line in read_line(deps_file):
    line = line.rstrip()
    match = re_match(PATTERN_DAWN_REVISION, line)
    if match:
      deps_contents.append('  \'dawn_revision\': \'' + dawn_revision + '\',')
    else:
      deps_contents.append(line)
  write_line(deps_file, deps_contents)
  execute_command(['gclient', 'sync', '-D'], dir=args.dir)


def build_chrome(args):
  build_args = {}
  build_args['proprietary_codecs'] = 'true'
  build_args['ffmpeg_branding'] = '"Chrome"'
  if args.build_type.startswith('default'):
    build_args['is_debug'] = 'false'
    build_args['is_component_build'] = 'false'
    build_args['symbol_level'] = '1'
    build_args['dcheck_always_on'] = 'true'
    build_args['build_angle_gles1_conform_tests'] = 'true'
    build_args['internal_gles2_conform_tests'] = 'true'
  else:
    build_args['is_component_build'] = 'true'
    build_args['enable_nacl'] = 'false'
    build_args['blink_symbol_level'] = '0'
    if args.build_type.startswith('debug'):
      build_args['is_debug'] = 'true'
      build_args['symbol_level'] = '2'
    else:
      build_args['is_debug'] = 'false'
      build_args['symbol_level'] = '1'
      build_args['dcheck_always_on'] = 'true'

  env = get_env()
  env.pop('PKG_CONFIG_PATH', None)
  arg_list = ['%s=%s' % (key,value) for key,value in build_args.iteritems()]
  execute_command(['gn', 'gen', args.build_dir, '--args=' + ' '.join(arg_list)], dir=args.dir, env=env)

  build_cmd = ['autoninja', '-C', args.build_dir]
  targets = CHROME_BUILD_TARGETS
  if is_linux():
    targets += CHROME_BUILD_TARGETS_LINUX
  for target in targets:
    cmd = build_cmd[:]
    cmd.append(target)
    execute_command(cmd, dir=args.dir, env=env)


def build_dawn(args):
  build_args = {}
  if args.build_type.startswith('debug'):
    build_args['is_debug'] = 'true'
  else:
    build_args['is_debug'] = 'false'

  arg_list = ['%s=%s' % (key,value) for key,value in build_args.iteritems()]
  execute_command(['gn', 'gen', args.build_dir, '--args=' + ' '.join(arg_list)], dir=args.dir)

  build_cmd = ['autoninja', '-C', args.build_dir]
  for target in DAWN_BUILD_TARGETS:
    cmd = build_cmd[:]
    cmd.append(target)
    execute_command(cmd, dir=args.dir)


def build_angle(args):
  build_args = {}
  if args.build_type.startswith('debug'):
    build_args['is_debug'] = 'true'
  else:
    build_args['is_debug'] = 'false'

  arg_list = ['%s=%s' % (key,value) for key,value in build_args.iteritems()]
  execute_command(['gn', 'gen', args.build_dir, '--args=' + ' '.join(arg_list)], dir=args.dir)

  build_cmd = ['autoninja', '-C', args.build_dir]
  for target in ANGLE_BUILD_TARGETS:
    cmd = build_cmd[:]
    cmd.append(target)
    execute_command(cmd, dir=args.dir)


def build_aquarium(args):
  build_args = {}
  if args.build_type.startswith('debug'):
    build_args['is_debug'] = 'true'
  else:
    build_args['is_debug'] = 'false'
  if is_linux():
    build_args['dawn_enable_opengl'] = 'false'

  arg_list = ['%s=%s' % (key,value) for key,value in build_args.iteritems()]
  execute_command(['gn', 'gen', args.build_dir, '--args=' + ' '.join(arg_list)], dir=args.dir)

  build_cmd = ['autoninja', '-C', args.build_dir]
  for target in AQUARIUM_BUILD_TARGETS:
    cmd = build_cmd[:]
    cmd.append(target)
    execute_command(cmd, dir=args.dir)


def build_mesa(args):
  build_args = {}
  if args.prefix:
    build_args['prefix'] = args.prefix
  build_args['platforms'] = 'x11,drm'
  build_args['dri-drivers'] = 'i915,i965'
  build_args['vulkan-drivers'] = 'intel'
  build_args['gallium-drivers'] = 'iris'
  build_args['dri3'] = 'true'
  build_args['gles1'] = 'true'
  build_args['gles2'] = 'true'
  build_args['gbm'] = 'true'
  build_args['shared-glapi'] = 'true'

  meson_cmd = ['meson', args.build_dir]
  meson_cmd += ['-D%s=%s' % (key,value) for key,value in build_args.iteritems()]
  execute_command(meson_cmd, dir=args.dir)

  build_cmd = ['ninja', '-C', args.build_dir]
  execute_command(build_cmd, dir=args.dir)


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
    zip(args.zip, pack_dir)
    if not args.pack:
      remove(pack_dir)


def pack_mesa(args):
  pack_cmd = ['ninja', '-C', args.build_dir, 'install']
  execute_command(pack_cmd, dir=args.dir)

  if args.zip:
    zip(args.zip, args.prefix)
    if not args.pack:
      remove(args.prefix)


def main():
  args = parse_arguments()

  if args.update:
    execute_command(['git', 'checkout', '.'], dir=args.dir)
    execute_command(['git', 'fetch', 'origin'], dir=args.dir)
    execute_command(['git', 'rebase', 'origin/master'], dir=args.dir)

    if args.project == 'aquarium':
      sync_aquarium(args)
    elif args.project != 'mesa':
      execute_command(['gclient', 'sync', '-D'], dir=args.dir)

  for build_type in args.target:
    if args.project == 'mesa':
      args.build_dir = 'out'
      build_dir = path.join(args.dir, args.build_dir)
      if path.exists(build_dir):
        remove(build_dir)
      if args.pack:
        args.prefix = args.pack
      elif args.zip:
        args.prefix = path.join(args.dir, random_string(8))
      else:
        args.prefix = ''
    else:
      args.build_type = build_type.lower()
      args.build_dir = path.join('out', build_type)

    if args.project == 'chrome':
      build_chrome(args)
    elif args.project == 'angle':
      build_angle(args)
    elif args.project == 'dawn':
      build_dawn(args)
    elif args.project == 'aquarium':
      build_aquarium(args)
    elif args.project == 'mesa':
      build_mesa(args)
  
  if args.pack or args.zip:
    if args.project == 'chrome':
      pack_chrome(args)
    elif args.project == 'aquarium':
      pack_aquarium(args)
    elif args.project == 'mesa':
      pack_mesa(args)

  return 0


if __name__ == '__main__':
  sys.exit(main())
