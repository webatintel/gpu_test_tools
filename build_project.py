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

CHROME_PACK_SCRIPT = path.join('tools', 'mb', 'mb.py')

CHROME_TARGETS = [
  'chrome',
  'content_shell',
  'telemetry_gpu_integration_test',
  'imagediff',
  'gl_tests',
  'vulkan_tests',
  'dawn_end2end_tests',
  'dawn_perf_tests',
  'angle_end2end_tests',
  'angle_perftests',
]

DAWN_TARGETS = [
  'dawn_end2end_tests',
  'dawn_perf_tests',
]

ANGLE_TARGETS = [
  'angle_end2end_tests',
  'angle_perftests',
]

AQUARIUM_TARGETS = [
  'aquarium',
]

CHROME_EXECUTABLES = {
  'chrome',
  'content_shell',
  'image_diff',
  'trace_processor_shell',
  'gl_tests',
  'vulkan_tests',
  'dawn_end2end_tests',
  'dawn_perftests',
  'angle_end2end_tests',
  'angle_perftests',
}

CHROME_LIBRARIES = {
  'angle_util',
}

AQUARIUM_EXECUTABLES = {
  'aquarium',
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
      help='Source directory.\n\n')
  parser.add_argument('--target', '-t', nargs='*', default=['Default'],
      help='The target build directory under out/, you can specify multiple. Default is "Default".\n'\
           'starts with "Default" : For Chrome, the build arguments are same as official trybot.\n'\
           '                        For others, it\'s same as release build.\n'\
           'starts with "Debug"   : the debug build.\n'\
           'starts with "Release" : the release build.\n\n')
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

  if args.project == 'mesa' and args.target != ['Default']:
    raise Exception('Mesa does not support --target')

  for target in args.target:
    if not target.startswith('Default') and not target.startswith('Debug') and not target.startswith('Release'):
      raise Exception('Target must starts with "Default/Debug/Release"')

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
  if args.build_type == 'default':
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
    if args.build_type == 'debug':
      build_args['is_debug'] = 'true'
      build_args['symbol_level'] = '2'
    elif args.build_type == 'release':
      build_args['is_debug'] = 'false'
      build_args['symbol_level'] = '1'
      build_args['dcheck_always_on'] = 'true'

  env = get_env()
  env.pop('PKG_CONFIG_PATH', None)
  arg_list = ['%s=%s' % (key,value) for key,value in build_args.items()]
  execute_command(['gn', 'gen', args.build_dir, '--args=' + ' '.join(arg_list)], dir=args.dir, env=env)

  build_cmd = ['autoninja', '-C', args.build_dir]
  for target in CHROME_TARGETS:
    cmd = build_cmd[:]
    cmd.append(target)
    execute_command(cmd, dir=args.dir, env=env)


def build_dawn(args):
  build_args = {}
  if args.build_type == 'debug':
    build_args['is_debug'] = 'true'
  elif args.build_type == 'default' or args.build_type == 'release':
    build_args['is_debug'] = 'false'

  arg_list = ['%s=%s' % (key,value) for key,value in build_args.items()]
  execute_command(['gn', 'gen', args.build_dir, '--args=' + ' '.join(arg_list)], dir=args.dir)

  build_cmd = ['autoninja', '-C', args.build_dir]
  for target in DAWN_TARGETS:
    cmd = build_cmd[:]
    cmd.append(target)
    execute_command(cmd, dir=args.dir)


def build_angle(args):
  build_args = {}
  if args.build_type == 'debug':
    build_args['is_debug'] = 'true'
  elif args.build_type == 'default' or args.build_type == 'release':
    build_args['is_debug'] = 'false'

  arg_list = ['%s=%s' % (key,value) for key,value in build_args.items()]
  execute_command(['gn', 'gen', args.build_dir, '--args=' + ' '.join(arg_list)], dir=args.dir)

  build_cmd = ['autoninja', '-C', args.build_dir]
  for target in ANGLE_TARGETS:
    cmd = build_cmd[:]
    cmd.append(target)
    execute_command(cmd, dir=args.dir)


def build_aquarium(args):
  build_args = {}
  if args.build_type == 'debug':
    build_args['is_debug'] = 'true'
  elif args.build_type == 'default' or args.build_type == 'release':
    build_args['is_debug'] = 'false'
  if is_linux():
    build_args['dawn_enable_opengl'] = 'false'

  arg_list = ['%s=%s' % (key,value) for key,value in build_args.items()]
  execute_command(['gn', 'gen', args.build_dir, '--args=' + ' '.join(arg_list)], dir=args.dir)

  build_cmd = ['autoninja', '-C', args.build_dir]
  for target in AQUARIUM_TARGETS:
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
  meson_cmd += ['-D%s=%s' % (key,value) for key,value in build_args.items()]
  execute_command(meson_cmd, dir=args.dir)

  build_cmd = ['ninja', '-C', args.build_dir]
  execute_command(build_cmd, dir=args.dir)


def copy_executable(src_dir, dest_dir, executables):
  for executable in executables:
    if is_linux():
      copy(path.join(src_dir, executable), dest_dir)
      chmod(path.join(dest_dir, executable), 755)
    elif is_win():
      copy(path.join(src_dir, executable + '.exe'), dest_dir)
      copy(path.join(src_dir, executable + '.exe.pdb'), dest_dir)


def copy_library(src_dir, dest_dir, libraries):
  for library in libraries:
    if is_linux():
      copy(path.join(src_dir, 'lib' + library + '.so'), dest_dir)
    elif is_win():
      copy(path.join(src_dir, library + '.dll'), dest_dir)


def pack_chrome(args):
  env = get_env()
  env.pop('PKG_CONFIG_PATH', None)
  zip_file = path.join(args.dir, random_string(8) + '.zip')
  execute_command([PYTHON_CMD, CHROME_PACK_SCRIPT, 'zip', args.build_dir,
                  'telemetry_gpu_integration_test', zip_file], dir=args.dir, env=env)

  pack_dir = args.pack if args.pack else path.join(args.dir, random_string(8))
  unzip(zip_file, pack_dir)
  remove(zip_file)

  src_dir = path.join(args.dir, args.build_dir)
  dest_dir = path.join(pack_dir, args.build_dir)
  copy_executable(src_dir, dest_dir, CHROME_EXECUTABLES)
  copy_library(src_dir, dest_dir, CHROME_LIBRARIES)

  if args.zip:
    zip(args.zip, pack_dir)
    if not args.pack:
      remove(pack_dir)


def pack_aquarium(args):
  pack_dir = args.pack if args.pack else path.join(args.dir, random_string(8))
  mkdir(path.join(pack_dir, args.build_dir))

  src_dir = path.join(args.dir, args.build_dir)
  dest_dir = path.join(pack_dir, args.build_dir)
  copy_executable(src_dir, dest_dir, AQUARIUM_EXECUTABLES)
  for content in AQUARIUM_ASSETS:
    copy(path.join(args.dir, content), pack_dir)

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

  for target in args.target:
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
      if target.startswith('Default'):
        args.build_type = 'default'
      elif target.startswith('Debug'):
        args.build_type = 'debug'
      elif target.startswith('Release'):
        args.build_type = 'release'
      args.build_dir = path.join('out', target)

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
