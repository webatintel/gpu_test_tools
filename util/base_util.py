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

PATTERN_NINJA_PROGRESS = r'^\[(\d+)/(\d+)\] [A-Z\-\(\)]+ .+$'
PATTERN_CHROME_REVISION = r'^Cr-Commit-Position: refs/heads/master@{#(\d+)}$'

PATTERN_GL_RENDER  = r'^OpenGL renderer string: Mesa (.+) \(.+\)$'
PATTERN_GL_VERSION = r'^OpenGL core profile version string: \d\.\d \(Core Profile\) Mesa ([\d\.]+).*$'

MATCHERS = {}

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
      if match_any(['Unhandled inspector message',
                    'WARNING:root:Unhandled inspector message'],
                    lambda x: line.startswith(x)):
        continue
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
  last_progress, base_progress_time = 0, 0

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
      print(line, flush=True)
      continue
    progress = int(match.group(1)) * 100 // int(match.group(2))
    if progress == last_progress:
      continue

    last_progress = progress
    line = '['
    for i in range(progress//2):
      line += '='
    line += '>'
    for i in range(progress//2, 50):
      line += ' '
    line += '] %d%%' % progress
    print('\r' + line, end='')

    total_seconds = (get_currenttime() - start_time).total_seconds()
    print('    Total time: %d min' % (total_seconds // 60), end='')
    if progress == 100:
      print('                              ', flush=True)
      continue

    if progress <= 3:
      pass
    elif progress <= 10:
      base_progress_time = total_seconds / progress * 8 // 5
    elif progress <= 20:
      base_progress_time = total_seconds / progress * 6 // 5
    elif progress <= 50:
      base_progress_time = total_seconds / progress

    if not base_progress_time:
      print('    Time remaining: - min', end='', flush=True)
    else:
      time_remaining = 0
      if progress <= 50:
        time_remaining += base_progress_time * 50 - total_seconds
      if progress <= 60:
        time_remaining += base_progress_time * (60 - max(50, progress))  * 15 // 6
      if progress <= 80:
        time_remaining += base_progress_time * (80 - max(60, progress))  * 25 // 6
      if progress <= 100:
        time_remaining += base_progress_time * (100 - max(80, progress)) * 35 // 6
      print('    Time remaining: %d min  ' % (time_remaining // 60), end='', flush=True)

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
                return driver_desc, driver_version
          except WindowsError:
            pass
  return None, None

def get_gpu_info_linux():
  gpu, driver = None, None
  ret = execute_return(['glxinfo'])
  for line in ret.splitlines():
    if not gpu:
      match = re_match(PATTERN_GL_RENDER, line)
      gpu = match.group(1) if match else None
    if not driver:
      match = re_match(PATTERN_GL_VERSION, line)
      driver = match.group(1) if match else None
    if gpu and driver:
      return gpu, driver
  return gpu, driver

def get_gpu_info():
  if is_win():
    return get_gpu_info_win()
  elif is_linux():
    return get_gpu_info_linux()
