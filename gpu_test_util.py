#!/usr/bin/env python

import datetime
import email.utils
import json
import os
import re
import shutil
import smtplib
import socket
import subprocess
import sys
import time
import zipfile

from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from os import path
from subprocess import CalledProcessError

PYTHON_CMD = 'python'
EMAIL_SENDER = 'gpu_test@wp-40.sh.intel.com'
SMTP_SERVER = '10.239.47.74'

PATTERN_NINJA = r'^\[(\d+)/(\d+)\] [A-Z\-\(\)]+ .+$'

MATCHERS = {}

def re_match(pattern, text):
  global MATCHERS
  if MATCHERS.has_key(pattern):
    matcher = MATCHERS[pattern]
  else:
    matcher = re.compile(pattern)
    MATCHERS[pattern] = matcher
  return matcher.match(text)

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

def sleep(second):
  time.sleep(second)

def format_date(date, format):
  return date.strftime(format)

def format_time(time, format):
  return time.strftime(format)

def get_currentdate(format=None):
  date = datetime.date.today()
  if format:
    return format_date(date, format)
  return date

def get_currenttime(format=None):
  time = datetime.datetime.now()
  if format:
    return format_time(time, format)
  return time

def get_hostname():
  return socket.gethostname()

def get_env():
  return os.environ.copy()

def mkdir(dir):
  try:
    os.makedirs(dir)
  except OSError:
    pass

def chmod(path, mode):
  os.chmod(path, int(str(mode), 8))

def copy(src, dest):
  if path.isfile(src):
    shutil.copy(src, dest)
  elif path.isdir(src):
    if path.exists(dest):
      dest = path.join(dest, path.basename(src))
    shutil.copytree(src, dest)

def remove(src):
  if path.isfile(src):
    os.remove(src)
  elif path.isdir(src):
    shutil.rmtree(src)

def move(src, dest):
  shutil.move(src, dest)

def unzip(src_file, dest_dir, remove_src=False):
  with zipfile.ZipFile(src_file, 'r') as zip_file:
    zip_file.extractall(dest_dir)
  if remove_src:
    os.remove(src_file)
  return dest_dir

def read_json(file_name):
  try:
    with open(file_name, 'r') as json_file:
      return json.load(json_file)
  except Exception:
    return {}

def write_json(file_name, content_dict):
  if not content_dict:
    return
  with open(file_name, 'w') as json_file:
    json.dump(content_dict, json_file)

def read_line(file_name):
  with open(file_name, 'r') as f:
    while True:
      line = f.readline()
      if not line:
        break
      yield line.strip()

def read_file(file_name):
  try:
    with open(file_name, 'r') as f:
      return f.read()
  except Exception:
    return ''

def write_file(file_name, content):
  if not content:
    return
  with open(file_name, 'w') as f:
    f.write(content)

def list_file(dir):
  for item in os.listdir(dir):
    file_name = path.join(dir, item)
    if path.isfile(file_name):
      yield file_name

def send_email(receivers, subject, body='', attached_files=[]):
  if not receivers:
    return
  if not isinstance(receivers, list):
    receivers = [receivers]

  message = MIMEMultipart()
  message['From'] = EMAIL_SENDER
  message['To'] =  email.utils.COMMASPACE.join(receivers)
  message['Subject'] = subject
  message.attach(MIMEText(body, 'plain'))

  for file_name in attached_files:
    attachment = MIMEBase('application', "octet-stream")
    attachment.set_payload(read_file(file_name))
    encoders.encode_base64(attachment)
    attachment.add_header('Content-Disposition', 'attachment; filename="%s"' % path.basename(file_path))
    message.attach(attachment)

  try:
    smtp = smtplib.SMTP(SMTP_SERVER)
    smtp.sendmail(EMAIL_SENDER, receivers, message.as_string())
    smtp.quit()
  except Exception as e:
    print(e)

def execute_command(cmd,
                    print_log=True, return_log=False, save_log=None,
                    dir=None, env=None):
  log_lines = []
  log_file = None
  is_progress_command = cmd[0].find('ninja') >= 0
  progress_percent = 0

  try:
    if print_log:
      print('\n[%s] \'%s\' in \'%s\'' % 
          (get_currenttime('%Y/%m/%d %H:%M:%S'),
           ' '.join(cmd),
           path.abspath(dir) if dir else os.getcwd()))

    process = subprocess.Popen(cmd,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        shell=is_win(), cwd=dir, env=env)

    for line in iter(process.stdout.readline, b''):
      line = line.strip()
      # Generate progress bar
      if is_progress_command:
        match = re_match(PATTERN_NINJA, line)
        if match:
          if print_log:
            n = int(match.group(1)) * 100 / int(match.group(2))
            if n > progress_percent:
              progress_percent = n
              line = '\r['
              for i in range(0, progress_percent/2):
                line += '='
              line += '>'
              for i in range(progress_percent/2, 50):
                line += ' '
              line += '] %d%%' % progress_percent
              sys.stdout.write(line)
              if progress_percent == 100:
                progress_percent = 0
                sys.stdout.write('\n')
              sys.stdout.flush()
          continue

      # Output log
      if print_log:
        print(line)
        sys.stdout.flush()
      if return_log:
        log_lines.append(line)
      if save_log:
        if not log_file:
          log_file = open(save_log, 'w')
        log_file.write(line + '\n')
        log_file.flush()
        os.fsync(log_file.fileno())
  except Exception as e:
    if print_log:
      print(e)
    if return_log:
      log_lines.extend(str(e).split('\n'))
    if save_log:
      if not log_file:
        log_file = open(save_log, 'w')
      log_file.write(e)
    raise CalledProcessError(1, cmd, '\n'.join(log_lines))
  finally:
    if log_file:
      log_file.close()

  retcode = process.wait()
  if retcode:
    raise CalledProcessError(retcode, cmd, '\n'.join(log_lines))
  return '\n'.join(log_lines)
