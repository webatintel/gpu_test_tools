import os
import socket
import subprocess
import sys

try:
  from winreg import *
except ImportError:
  pass

SYSTEM_CONTROL_CLASS_KEY = 'SYSTEM\CurrentControlSet\Control\Class'

PATTERN_GL_RENDER  = r'^OpenGL renderer string: Mesa (.+) \(.+\)$'
PATTERN_GL_VERSION = r'^OpenGL core profile version string: \d\.\d \(Core Profile\) Mesa ([\d\.]+).*$'

def is_win():
  return sys.platform == 'win32'

def is_linux():
  return sys.platform == 'linux'

def is_mac():
  return sys.platform == 'darwin'

def get_platform():
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

def get_gpu_info_win():
  with OpenKey(HKEY_LOCAL_MACHINE, SYSTEM_CONTROL_CLASS_KEY) as root_key:
    for i in range(QueryInfoKey(root_key)[0]):
      with OpenKey(root_key, EnumKey(root_key, i)) as class_key:
        for j in range(QueryInfoKey(class_key)[0]):
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

def get_gpu_info_linux():
  gpu = None
  ret = subprocess.run(['glxinfo'], check=True, stdout=subprocess.PIPE)
  for line in ret.stdout.decode().splitlines():
    if gpu:
      match = re_match(PATTERN_GL_VERSION, line)
      if match:
        return gpu, match.group(1)
    else:
      match = re_match(PATTERN_GL_RENDER, line)
      if match:
        gpu = match.group(1)
  return None, None

def get_gpu_info():
  if is_win():
    return get_gpu_info_win()
  elif is_linux():
    return get_gpu_info_linux()
