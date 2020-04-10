#!/usr/bin/env python

from base_util import *
from os import path
try:
  from _winreg import *
except ImportError:
  pass

PATTERN_REVISION = r'^Cr-Commit-Position: refs/heads/master@{#(\d+)}$'
PATTERN_GL_VERSION = r'^OpenGL core profile version string: \d\.\d \(Core Profile\) Mesa ([\d\.]+).*$'
PATTERN_GL_RENDER = r'^OpenGL renderer string: Mesa (.+) \(.+\)$'
SYSTEM_CLASS_KEY_ROOT = 'SYSTEM\CurrentControlSet\Control\Class'

def get_chrome_revision(chrome_dir, back_level=0):
  try:
    log = execute_command(['git', 'log', '-1', 'HEAD~%d' % back_level],
                          print_log=False, return_log=True, dir=chrome_dir)
    log_lines = log.split('\n')
    for i in range(len(log_lines)-1, -1, -1):
      match = re_match(PATTERN_REVISION, log_lines[i])
      if match:
        return match.group(1)
  except CalledProcessError:
    pass
  return ''


def get_aquarium_revision(aquarium_dir):
  try:
    aquarium_revision = execute_command(['git', 'rev-parse', 'HEAD'],
                                        print_log=False, return_log=True,
                                        dir=aquarium_dir)
    dawn_revision = execute_command(['git', 'rev-parse', 'HEAD'],
                                    print_log=False, return_log=True,
                                    dir=path.join(aquarium_dir, 'third_party', 'dawn'))
    if aquarium_revision and dawn_revision:
      return '%s_%s' % (aquarium_revision[0:6], dawn_revision[0:6])
  except CalledProcessError:
    pass
  return ''


def get_gpu_info():
  if is_win():
    with OpenKey(HKEY_LOCAL_MACHINE, SYSTEM_CLASS_KEY_ROOT) as class_key_root:
      for i in range(0, QueryInfoKey(class_key_root)[0]):
        with OpenKey(class_key_root, EnumKey(class_key_root, i)) as class_key:
          for j in range(0, QueryInfoKey(class_key)[0]):
            try:
              with OpenKey(class_key, EnumKey(class_key, j)) as sub_key:
                driver_desc, _ = QueryValueEx(sub_key, 'DriverDesc')
                if ('Intel(R)' in driver_desc and 'Graphics' in driver_desc
                    and not 'Control Panel' in driver_desc
                    and not 'Command Center' in driver_desc):
                  driver_version, _ = QueryValueEx(sub_key, 'DriverVersion')
                  return driver_desc, driver_version
            except WindowsError:
              pass
  elif is_linux():
    gpu = None
    ret = execute_command(['glxinfo'], print_log=False, return_log=True)
    for line in ret.splitlines():
      line = line.strip()
      match = re_match(PATTERN_GL_RENDER, line)
      if match:
        gpu = match.group(1)
        continue

      match = re_match(PATTERN_GL_VERSION, line)
      if match:
        return gpu, match.group(1)

  return None, None
