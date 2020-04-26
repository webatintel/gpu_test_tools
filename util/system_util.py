#!/usr/bin/env python

import os
import socket
import sys

from base_util import *
try:
  from _winreg import *
except ImportError:
  pass

SYSTEM_CLASS_KEY_ROOT = 'SYSTEM\CurrentControlSet\Control\Class'

PATTERN_GL_RENDER  = r'^OpenGL renderer string: Mesa (.+) \(.+\)$'
PATTERN_GL_VERSION = r'^OpenGL core profile version string: \d\.\d \(Core Profile\) Mesa ([\d\.]+).*$'

def is_win():
  return sys.platform == 'win32'

def is_linux():
  return sys.platform.startswith('linux')

def is_mac():
  return sys.platform == 'darwin'

def get_osname():
  if is_win():
    return 'win'
  elif is_linux():
    return 'linux'
  elif is_mac():
    return 'mac'

def get_hostname():
  return socket.gethostname()

def get_env():
  return os.environ.copy()

def get_win_gpu_info():
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
  return None, None

def get_linux_gpu_info():
  gpu = None
  ret = execute_command(['glxinfo'], print_log=False, return_log=True)
  for line in ret.splitlines():
    line = line.strip()
    if not gpu:
      match = re_match(PATTERN_GL_RENDER, line)
      if match:
        gpu = match.group(1)
    else:
      match = re_match(PATTERN_GL_VERSION, line)
      if match:
        return gpu, match.group(1)
  return None, None

def get_gpu_info():
  if is_win():
    return get_win_gpu_info()
  elif is_linux():
    return get_linux_gpu_info()
