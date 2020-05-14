import datetime
import email.utils
import os
import random
import re
import smtplib
import string
import subprocess
import sys

from .file_util import *
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from os import path
from subprocess import CalledProcessError

PYTHON_CMD = 'vpython'
TRYJOB_CONFIG = path.join(path.dirname(path.dirname(path.abspath(__file__))), 'tryjob.json')

PATTERN_NINJA_PROGRESS = r'^\[(\d+)/(\d+)\] [A-Z\-\(\)]+ .+$'
PATTERN_CHROME_REVISION = r'^Cr-Commit-Position: refs/heads/master@{#(\d+)}$'

MATCHERS = {}

def re_match(pattern, text):
  global MATCHERS
  if pattern in MATCHERS:
    matcher = MATCHERS[pattern]
  else:
    matcher = re.compile(pattern)
    MATCHERS[pattern] = matcher
  return matcher.match(text)

def match_any(targets, condition):
  for target in targets:
    if condition(target):
      return True
  return False

def random_string(size):
  return ''.join(random.choice(string.ascii_lowercase) for i in range(size))

def get_currenttime(format=None):
  time = datetime.datetime.now()
  if format:
    return time.strftime(format)
  return time

def send_email(receiver, subject, body='', attachment=[]):
  if not receiver:
    return
  if not isinstance(receiver, list):
    receiver = [receiver]
  if not isinstance(attachment, list):
    attachment = [attachment]

  config = read_json(TRYJOB_CONFIG)
  message = MIMEMultipart()
  message['From'] = config['email']['sender']
  message['To'] =  email.utils.COMMASPACE.join(receiver)
  message['Subject'] = subject
  message.attach(MIMEText(body, 'plain'))

  for file_name in attachment:
    content = read_file(file_name)
    if not content:
      continue
    item = MIMEBase('application', "octet-stream")
    item.set_payload(content)
    encoders.encode_base64(item)
    item.add_header('Content-Disposition', 'attachment; filename="%s"' % path.basename(file_name))
    message.attach(item)

  try:
    smtp = smtplib.SMTP(config['email']['smtp_server'])
    smtp.sendmail(config['email']['sender'], receiver, message.as_string())
    smtp.quit()
  except Exception as e:
    print(e)


def execute_command_passthrough(cmd, dir=None, env=None):
  process = subprocess.Popen(cmd, cwd=dir, env=env, shell=(sys.platform=='win32'))
  retcode = process.wait()
  if retcode:
    raise CalledProcessError(retcode, cmd, '')


def execute_command(cmd, print_log=True, return_log=False, save_log=None, dir=None, env=None):
  log_lines = []
  log_file = None
  is_ninja_command = cmd[0].find('ninja') >= 0
  if is_ninja_command:
    start_time = get_currenttime()
    last_progress = 0
    last_progress_time = start_time
    progress_times = []

  try:
    if print_log:
      print('\n[%s] \'%s\' in \'%s\'' % 
          (get_currenttime('%Y/%m/%d %H:%M:%S'), ' '.join(cmd),
           path.abspath(dir) if dir else os.getcwd()))

    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               cwd=dir, env=env, shell=(sys.platform=='win32'))

    for line in iter(process.stdout.readline, b''):
      line = line.decode().strip()
      if (line.startswith('Unhandled inspector message') or
          line.startswith('WARNING:root:Unhandled inspector message')):
        continue

      # Generate progress bar
      if print_log and is_ninja_command:
        match = re_match(PATTERN_NINJA_PROGRESS, line)
        if match:
          progress = int(match.group(1)) * 100 // int(match.group(2))
          if progress > last_progress:
            line = '['
            for i in range(0, progress//2):
              line += '='
            line += '>'
            for i in range(progress//2, 50):
              line += ' '
            line += '] %d%%' % progress
            sys.stdout.write('\r' + line)

            current_time = get_currenttime()
            total_time = current_time - start_time
            sys.stdout.write('    Total time: %dmin' % (total_time.total_seconds() // 60))
            if progress == 100:
              sys.stdout.write('\n')
            else:
              time_interval = current_time - last_progress_time
              progress_times.append(time_interval.total_seconds() // (progress - last_progress))
              if len(progress_times) > 10:
                progress_times.pop(0)
              time_remaning =  sum(progress_times) // len(progress_times) * (100 - progress)
              sys.stdout.write('    Time remaining: %dmin' % (time_remaning // 60))
              last_progress = progress
              last_progress_time = current_time
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
    raise e
  finally:
    if log_file:
      log_file.close()

  retcode = process.wait()
  if retcode:
    raise CalledProcessError(retcode, cmd, '\n'.join(log_lines))
  return '\n'.join(log_lines)


def get_chrome_revision(chrome_dir, back_level=0):
  try:
    log = execute_command(['git', 'log', '-1', 'HEAD~%d' % back_level],
                          print_log=False, return_log=True, dir=chrome_dir)
    log_lines = log.split('\n')
    for i in range(len(log_lines)-1, -1, -1):
      match = re_match(PATTERN_CHROME_REVISION, log_lines[i])
      if match:
        return match.group(1)
  except CalledProcessError:
    pass
  return ''
