#!/usr/bin/env python3

import argparse
import os
import sys

from os import path
from util.base_util import *
from util.file_util import *
from util.system_util import *

CHROME_PACK_SCRIPT = path.join('tools', 'mb', 'mb.py')

CHROME_BUILD_TARGET = [
  'chrome',
  'content_shell',
  'angle_end2end_tests',
  'angle_perftests',
  'dawn_end2end_tests',
  'dawn_perf_tests',
  'gl_tests',
  'gpu_unittests',
  'imagediff',
  'vulkan_tests',
  'telemetry_gpu_integration_test',
]

DAWN_BUILD_TARGET = [
  'dawn_end2end_tests',
  'dawn_perf_tests',
]

ANGLE_BUILD_TARGET = [
  'angle_end2end_tests',
  'angle_perftests',
]

AQUARIUM_BUILD_TARGET = [
  'aquarium',
]

CHROME_EXECUTABLE = [
  'angle_end2end_tests',
  'angle_perftests',
  'chrome',
  'content_shell',
  'crashpad_database_util',
  'crashpad_handler',
  'dawn_end2end_tests',
  'dawn_perf_tests',
  'gl_tests',
  'gpu_unittests',
  'image_diff',
  'trace_processor_shell',
  'vulkan_tests',
]

CHROME_EXECUTABLE_BREAKPAD = [
  'dump_syms',
  'minidump_dump',
  'minidump_stackwalk',
]

CHROME_LIBRARY = [
  'angle_util',
  'blink_deprecated_test_plugin',
  'blink_test_plugin',
  'libGLESv1_CM',
]

CHROME_RESOURCE = [
  'args.gn',
  'content_shell.pak',
  'test_fonts',
]

CHROME_SRC_RESOURCE = [
  path.join('third_party', 'blink', 'tools'),
  path.join('third_party', 'blink', 'web_tests'),
  path.join('third_party', 'pywebsocket3'),
]

PATTERN_COMMIT = r'^commit (\w+)$'
PATTERN_DAWN_REVISION = r'  \'dawn_revision\': \'\w+\''


def parse_arguments():
  parser = argparse.ArgumentParser(
      description='Build project.',
      formatter_class=argparse.RawTextHelpFormatter)
  parser.add_argument('project', nargs='?',
      choices=['chrome', 'dawn', 'angle', 'aquarium', 'mesa'], default='chrome',
      help='The project to build. Default is "chrome".\n\n')
  parser.add_argument('--src-dir', '--dir', '-d', default='.',
      help='The source directory. Default is current directory.\n\n')
  parser.add_argument('--target', '-t', nargs='+', default=['Default'],
      help='The target build directory under "out/", you can specify multiple.\n'\
           'The target name must comply with following formats.\n'\
           'Default is "Default", so the actual build directory would be "out/Default".\n\n'\
           'Release or Release_xx : the release build.\n'\
           'Debug   or Debug_xx   : the debug build.\n'\
           'Default or Default_xx : For Chrome, the build arguments are same as official trybot.\n'\
           '                        For others, it\'s same as release build.\n\n')
  parser.add_argument('--update', '-u', action='store_true',
      help='Fetch from origin and rebase to master, then synchronize the dependencies before building.\n\n')
  parser.add_argument('--prefix', '-p',
      help='Install the binaries to a directory after building.\n\n')
  parser.add_argument('--zip', '-z',
      help='Package the binaries to a zip file after building.\n\n')
  args = parser.parse_args()

  if args.prefix or args.zip:
    if len(args.target) > 1:
      raise Exception('Do not support to package multiple targets')
    if args.project not in ['chrome', 'mesa']:
      raise Exception('Do not support to package ' + args.project)

  for target in args.target:
    if target.split('_')[0] not in ['Default', 'Debug', 'Release']:
      raise Exception('Target iname must start with Default/Debug/Release')

  args.src_dir = path.abspath(args.src_dir)
  if args.prefix:
    args.prefix = path.abspath(args.prefix)
    if args.prefix == args.src_dir:
      raise Exception('Prefix is same as the source directory')
    if path.exists(args.prefix):
      raise Exception('Prefix already exits')
  if args.zip:
    args.zip = path.abspath(args.zip)
    if path.exists(args.zip):
      raise Exception('Zip file already exits')

  if args.prefix:
    args.pack_dir = args.prefix
  elif args.zip:
    args.pack_dir = path.join(args.src_dir, random_string(8))
  else:
    args.pack_dir = None
  return args


def build_gn_project(args, build_args, build_targets):
  env = get_env()
  env.pop('PKG_CONFIG_PATH', None)
  arg_list = ['%s=%s' % (key,value) for key,value in build_args.items()]
  execute_command(['gn', 'gen', args.build_dir, '--args=' + ' '.join(arg_list)],
                  dir=args.src_dir, env=env)
  for target in build_targets:
    execute_command(['autoninja', '-C', args.build_dir, target],
                    dir=args.src_dir, env=env)


def build_chrome(args):
  build_args = {}
  build_args['proprietary_codecs'] = 'true'
  build_args['ffmpeg_branding'] = '"Chrome"'
  build_args['use_dawn'] = 'true'
  build_args['enable_nacl'] = 'false'
  build_args['blink_symbol_level'] = '0'
  if args.build_type == 'debug':
    build_args['is_debug'] = 'true'
    build_args['symbol_level'] = '2'
  elif args.build_type in ['default', 'release']:
    build_args['is_debug'] = 'false'
    build_args['symbol_level'] = '1'
    build_args['dcheck_always_on'] = 'true'
    if args.build_type == 'default':
      build_args['is_component_build'] = 'false'
      build_args['build_angle_gles1_conform_tests'] = 'true'
      build_args['internal_gles2_conform_tests'] = 'true'
    elif args.build_type == 'release':
      build_args['is_component_build'] = 'true'
  build_gn_project(args, build_args, CHROME_BUILD_TARGET)


def build_dawn(args):
  build_args = {}
  if args.build_type == 'debug':
    build_args['is_debug'] = 'true'
  elif args.build_type in ['default', 'release']:
    build_args['is_debug'] = 'false'
    build_args['dcheck_always_on'] = 'true'
  build_gn_project(args, build_args, DAWN_BUILD_TARGET)


def build_angle(args):
  build_args = {}
  if args.build_type == 'debug':
    build_args['is_debug'] = 'true'
  elif args.build_type in ['default', 'release']:
    build_args['is_debug'] = 'false'
    build_args['dcheck_always_on'] = 'true'
  build_gn_project(args, build_args, ANGLE_BUILD_TARGET)


def build_aquarium(args):
  build_args = {}
  if args.build_type == 'debug':
    build_args['is_debug'] = 'true'
  elif args.build_type in ['default', 'release']:
    build_args['is_debug'] = 'false'
  if is_linux():
    build_args['dawn_enable_opengl'] = 'false'
  build_gn_project(args, build_args, AQUARIUM_BUILD_TARGET)


def build_mesa(args):
  build_args = {}
  if args.pack_dir:
    build_args['prefix'] = args.pack_dir
  build_args['platforms'] = 'x11,drm'
  build_args['dri-drivers'] = 'i915,i965'
  build_args['vulkan-drivers'] = 'intel'
  build_args['gallium-drivers'] = 'iris'
  build_args['dri3'] = 'true'
  build_args['gles1'] = 'true'
  build_args['gles2'] = 'true'
  build_args['gbm'] = 'true'
  build_args['shared-glapi'] = 'true'
  if args.build_type == 'debug':
    build_args['buildtype'] = 'debugoptimized'
  elif args.build_type in ['default', 'release']:
    build_args['buildtype'] = 'release'

  meson_cmd = ['meson', args.build_dir] + ['-D%s=%s' % (key,value) for key,value in build_args.items()]
  execute_command(meson_cmd, dir=args.src_dir)
  execute_command(['ninja', '-C', args.build_dir], dir=args.src_dir)


def pack_chrome(args):
  zip_file = path.join(args.src_dir, random_string(8) + '.zip')
  execute_command([PYTHON_CMD, CHROME_PACK_SCRIPT, 'zip', args.build_dir,
                  'telemetry_gpu_integration_test', zip_file], dir=args.src_dir)
  unzip(zip_file, args.pack_dir)
  remove(zip_file)

  src_build = path.join(args.src_dir, args.build_dir)
  dest_build = path.join(args.pack_dir, args.build_dir)
  copy_executable(src_build, dest_build, CHROME_EXECUTABLE)
  if is_linux():
    copy_executable(src_build, dest_build, CHROME_EXECUTABLE_BREAKPAD)
  copy_library(src_build, dest_build, CHROME_LIBRARY)
  copy_resource(src_build, dest_build, CHROME_RESOURCE)
  copy_resource(args.src_dir, args.pack_dir, CHROME_SRC_RESOURCE)


def update_aquarium_deps(args):
  dawn_dir = path.join(args.src_dir, 'third_party', 'dawn')
  execute_command(['git', 'fetch', 'origin'], dir=dawn_dir)
  execute_command(['git', 'rebase', 'origin/master'], dir=dawn_dir)
  dawn_revision = None
  log = execute_command(['git', 'log', '-1'], print_log=False, return_log=True, dir=dawn_dir)
  for line in log.splitlines():
    match = re_match(PATTERN_COMMIT, line)
    if match:
      dawn_revision = match.group(1)
      break
  assert dawn_revision

  deps_file = path.join(args.src_dir, 'DEPS')
  deps_lines = read_file(deps_file).splitlines()
  for i in range(0, len(deps_lines)):
    match = re_match(PATTERN_DAWN_REVISION, deps_lines[i])
    if match:
      deps_lines[i] = '  \'dawn_revision\': \'' + dawn_revision + '\','
      print('Changed dependent Dawn revision to its latest master branch')
      break
  write_line(deps_file, deps_lines)


def main():
  args = parse_arguments()

  if args.update:
    execute_command(['git', 'checkout', '.'], dir=args.src_dir)
    execute_command(['git', 'fetch', 'origin'], dir=args.src_dir)
    execute_command(['git', 'rebase', 'origin/master'], dir=args.src_dir)
    if args.project == 'aquarium':
      update_aquarium_deps(args)
    if args.project != 'mesa':
      execute_command(['gclient', 'sync', '-D'], dir=args.src_dir)

  for target in args.target:
    args.build_type = target.split('_')[0].lower()
    args.build_dir = path.join('out', target)
    if args.project == 'chrome':
      build_chrome(args)
    elif args.project == 'dawn':
      build_dawn(args)
    elif args.project == 'angle':
      build_angle(args)
    elif args.project == 'aquarium':
      build_aquarium(args)
    elif args.project == 'mesa':
      build_mesa(args)
  
  if args.pack_dir:
    if args.project == 'chrome':
      pack_chrome(args)
    elif args.project == 'mesa':
      execute_command(['ninja', '-C', args.build_dir, 'install'], dir=args.src_dir)

    if args.zip:
      zip(args.zip, args.pack_dir)
      if not args.prefix:
        remove(args.pack_dir)

  return 0


if __name__ == '__main__':
  sys.exit(main())
