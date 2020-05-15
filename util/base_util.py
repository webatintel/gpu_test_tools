import collections
import datetime
import email.utils
import json
import os
import random
import re
import smtplib
import string
import subprocess
import sys

from collections import defaultdict
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from os import path
from subprocess import CalledProcessError

TRYJOB_CONFIG = path.abspath(path.join(path.dirname(path.abspath(__file__)), '..', 'tryjob.json'))

PATTERN_NINJA_PROGRESS = r'^\[(\d+)/(\d+)\] [A-Z\-\(\)]+ .+$'
PATTERN_CHROME_REVISION = r'^Cr-Commit-Position: refs/heads/master@{#(\d+)}$'

MATCHERS = {}

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

def send_email(receiver, subject, body='', attach=[]):
  receiver = receiver if isinstance(receiver, list) else [receiver]
  attach = attach if isinstance(attach, list) else [attach]

  with open(TRYJOB_CONFIG, 'r') as json_file:
    config = json.load(json_file)
  message = MIMEMultipart()
  message['From'] = config['email']['sender']
  message['To'] =  email.utils.COMMASPACE.join(receiver)
  message['Subject'] = subject
  message.attach(MIMEText(body, 'plain'))

  for file_path in attach:
    attachment = MIMEBase('application', "octet-stream")
    with open(file_path, 'r') as f:
      attachment.set_payload(f.read())
    encoders.encode_base64(attachment)
    attachment.add_header('Content-Disposition', 'attachment; filename="%s"'
                          % path.basename(file_path))
    message.attach(attachment)

  try:
    smtp = smtplib.SMTP(config['email']['smtp_server'])
    smtp.sendmail(config['email']['sender'], receiver, message.as_string())
    smtp.quit()
  except Exception as e:
    print(e)

def execute_passthrough(command, dir=None, env=None):
  process = subprocess.Popen(command, cwd=dir, env=env, shell=(sys.platform=='win32'))
  retcode = process.wait()
  if retcode:
    raise CalledProcessError(retcode, command, '')

def execute(command, print_log=True, return_log=False, save_log=None, dir=None, env=None):
  log_lines = []
  log_file = open(save_log, 'w') if save_log else None
  is_ninja_command = command[0].find('ninja') >= 0
  if is_ninja_command:
    start_time = get_currenttime()
    last_progress, base_progress_time = 0, 0

  try:
    if print_log:
      print('\n[%s] \'%s\' in \'%s\'' % 
            (get_currenttime('%Y/%m/%d %H:%M:%S'), ' '.join(command),
             path.abspath(dir) if dir else os.getcwd()))
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               cwd=dir, env=env, shell=(sys.platform=='win32'))

    for line in iter(process.stdout.readline, b''):
      line = line.decode().strip()
      if match_any(['Unhandled inspector message',
                    'WARNING:root:Unhandled inspector message'],
                   lambda x: line.startswith(x)):
        continue
      # Generate progress bar
      if print_log and is_ninja_command:
        match = re_match(PATTERN_NINJA_PROGRESS, line)
        if match:
          progress = int(match.group(1)) * 100 // int(match.group(2))
          if progress > last_progress:
            line = '['
            for i in range(progress//2):
              line += '='
            line += '>'
            for i in range(progress//2, 50):
              line += ' '
            line += '] %d%%' % progress
            sys.stdout.write('\r' + line)

            total_seconds = (get_currenttime() - start_time).total_seconds()
            sys.stdout.write('    Total time: %dmin' % (total_seconds // 60))
            if progress == 100:
              last_progress = 0
              sys.stdout.write('\n')
            else:
              last_progress = progress
              if progress <= 10:
                base_progress_time = total_seconds // progress * 8 // 5
              elif progress <= 15:
                base_progress_time = total_seconds // progress * 7 // 5
              elif progress <= 20:
                base_progress_time = total_seconds // progress * 6 // 5
              elif progress <= 50:
                base_progress_time = total_seconds // progress

              time_remaining = 0
              if progress <= 50:
                time_remaining += base_progress_time * 50 - total_seconds
              if progress <= 60:
                time_remaining += base_progress_time * (60 - max(50, progress))  * 15 // 6
              if progress <= 80:
                time_remaining += base_progress_time * (80 - max(60, progress))  * 25 // 6
              if progress <= 100:
                time_remaining += base_progress_time * (100 - max(80, progress)) * 35 // 6
              sys.stdout.write('    Time remaining: %dmin' % (time_remaining // 60))
            sys.stdout.flush()
          continue
        elif last_progress:
          continue

      # Output log
      if print_log:
        print(line)
        sys.stdout.flush()
      if return_log:
        log_lines.append(line)
      if save_log:
        log_file.write(line + '\n')
        log_file.flush()
        os.fsync(log_file.fileno())
  except Exception as e:
    raise e
  finally:
    if log_file:
      log_file.close()

  retcode = process.wait()
  if retcode:
    raise CalledProcessError(retcode, command, '\n'.join(log_lines))
  return '\n'.join(log_lines)

def get_chrome_revision(src_dir, back_level=0):
  try:
    ret = execute(['git', 'log', '-1', 'HEAD~%d' % back_level],
                  print_log=False, return_log=True, dir=src_dir)
    for line in reversed(ret.split('\n')):
      match = re_match(PATTERN_CHROME_REVISION, line)
      if match:
        return match.group(1)
  except CalledProcessError:
    pass
  return ''
