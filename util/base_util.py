import collections
import datetime
import os
import random
import re
import socket
import string
import subprocess
import sys

from collections import defaultdict
from os import path
from subprocess import CalledProcessError

try:
  from winreg import *
except ImportError:
  pass

SYSTEM_CONTROL_CLASS_KEY = 'SYSTEM\CurrentControlSet\Control\Class'

PATTERN_NINJA_PROGRESS = r'^\[(\d+)/(\d+)\] [A-Z_\-\(\)]+ .+$'
PATTERN_CHROME_REVISION = r'^Cr-Commit-Position: refs/heads/master@{#(\d+)}$'

PATTERN_VENDOR = r'^    Vendor: (.+) \(0x(\w+)\)$'
PATTERN_DEVICE = r'^    Device: Mesa (.+) \(.+\) \(0x(\w+)\)$'
PATTERN_GL_VERSION = r'^OpenGL core profile version string: [\d\.]+ \(Core Profile\) (.+) ([\d\.]+).*$'
PATTERN_DEVICE_ID = r'^PCI\\VEN_(\w+)&DEV_(\w+)$'

MATCHERS = {}

class GpuInfo(object):
  def __init__(self):
    self.vendor = None
    self.vendor_id = None
    self.device = None
    self.device_id = None
    self.driver = None
    self.driver_version = None


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

def re_match(pattern, string):
  global MATCHERS
  if pattern in MATCHERS:
    matcher = MATCHERS[pattern]
  else:
    matcher = re.compile(pattern)
    MATCHERS[pattern] = matcher
  return matcher.match(string)

def match_any(iterable, match_func):
  for item in iterable:
    if match_func(item):
      return True
  return False

def find_match(iterable, match_func):
  for item in iterable:
    if match_func(item):
      return item
  return None

def index_match(sequence, match_func):
  for i in range(len(sequence)):
    if match_func(sequence[i]):
      return i
  return -1

def random_string(size):
  return ''.join(random.choice(string.ascii_lowercase) for i in range(size))

def get_currenttime(format=None):
  time = datetime.datetime.now()
  return time.strftime(format) if format else time

def execute(command, dir=None, env=None):
  print('\n[%s] \'%s\' in \'%s\'' % 
        (get_currenttime('%Y/%m/%d %H:%M:%S'), ' '.join(command),
         path.abspath(dir) if dir else os.getcwd()))
  subprocess.run(command, cwd=dir, env=env, shell=is_win(), check=True)

def execute_return(command, dir=None, env=None):
  ret = subprocess.run(command, cwd=dir, env=env, shell=is_win(),
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
  return ret.stdout.strip()

def execute_log(command, log_path, print_log=True, dir=None, env=None):
  print('\n[%s] \'%s\' in \'%s\'' % 
        (get_currenttime('%Y/%m/%d %H:%M:%S'), ' '.join(command),
         path.abspath(dir) if dir else os.getcwd()))
  process = subprocess.Popen(command, cwd=dir, env=env, shell=is_win(),
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
  with open(log_path, 'w') as log_file:
    for line in iter(process.stdout.readline, b''):
      line = line.decode().strip()
      log_file.write(line + '\n')
      log_file.flush()
      os.fsync(log_file.fileno())
      if print_log:
        print(line, flush=True)

  retcode = process.wait()
  if retcode:
    raise CalledProcessError(retcode, command)


def execute_progress(command, dir=None, env=None):
  is_ninja = command[0].find('ninja') >= 0
  start_time = get_currenttime()
  last_progress = 0
  endline = True

  print('\n[%s] \'%s\' in \'%s\'' %
        (get_currenttime('%Y/%m/%d %H:%M:%S'), ' '.join(command),
         path.abspath(dir) if dir else os.getcwd()))
  process = subprocess.Popen(command, cwd=dir, env=env, shell=is_win(),
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
  for line in iter(process.stdout.readline, b''):
    line = line.decode().strip()
    if is_ninja:
      match = re_match(PATTERN_NINJA_PROGRESS, line)

    if not match:
      if not endline:
        endline = True
        print()
      print(line, flush=True)
      continue

    progress = int(match.group(1)) * 100 // int(match.group(2))
    if progress == last_progress:
      continue
    last_progress = progress
    total_seconds = (get_currenttime() - start_time).total_seconds()

    line = '['
    for i in range(progress//2):
      line += '='
    line += '>'
    for i in range(progress//2, 50):
      line += ' '
    line += '] %d%%' % progress
    print('\r%s    Total time: %d min' % (line, total_seconds // 60), end='', flush=True)
    if progress == 100:
      endline = True
      print()
    else:
      endline = False

  retcode = process.wait()
  if retcode:
    raise CalledProcessError(retcode, command)


def get_chrome_revision(src_dir, back_level=0):
  ret = execute_return(['git', 'log', '-1', 'HEAD~%d' % back_level], dir=src_dir)
  for line in reversed(ret.split('\n')):
    match = re_match(PATTERN_CHROME_REVISION, line)
    if match:
      return match.group(1)
  return ''

def get_gpu_info_win():
  with OpenKey(HKEY_LOCAL_MACHINE, SYSTEM_CONTROL_CLASS_KEY) as root_key:
    for i in range(QueryInfoKey(root_key)[0]):
      with OpenKey(root_key, EnumKey(root_key, i)) as class_key:
        for j in range(QueryInfoKey(class_key)[0]):
          try:
            with OpenKey(class_key, EnumKey(class_key, j)) as sub_key:
              driver_desc, _ = QueryValueEx(sub_key, 'DriverDesc')
              if ('Intel(R)' in driver_desc and
                  'Graphics' in driver_desc and
                  not 'Control Panel' in driver_desc and
                  not 'Command Center' in driver_desc):
                driver_version, _ = QueryValueEx(sub_key, 'DriverVersion')
                device_id, _ = QueryValueEx(sub_key, 'MatchingDeviceId')
                match = re_match(PATTERN_DEVICE_ID, device_id)

                gpu_info = GpuInfo()
                gpu_info.vendor = 'Intel'
                gpu_info.vendor_id = match.group(1)
                gpu_info.device = driver_desc
                gpu_info.device_id = match.group(2).lower()
                gpu_info.driver = 'Intel'
                gpu_info.driver_version = driver_version
                return gpu_info
          except WindowsError:
            pass
  return None

def get_gpu_info_linux():
  gpu_info = GpuInfo()
  ret = execute_return(['glxinfo'])
  for line in ret.splitlines():
    if not gpu_info.vendor:
      match = re_match(PATTERN_VENDOR, line)
      if match:
        gpu_info.vendor, gpu_info.vendor_id = match.groups()
    if not gpu_info.device:
      match = re_match(PATTERN_DEVICE, line)
      if match:
        gpu_info.device, gpu_info.device_id = match.groups()
    if not gpu_info.driver:
      match = re_match(PATTERN_GL_VERSION, line)
      if match:
        gpu_info.driver, gpu_info.driver_version = match.groups()
    if gpu_info.vendor and gpu_info.device and gpu_info.driver:
      return gpu_info
  return None

def get_gpu_info():
  if is_win():
    return get_gpu_info_win()
  elif is_linux():
    return get_gpu_info_linux()
