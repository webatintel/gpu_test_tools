#!/usr/bin/env python

import datetime
import email.utils
import os
import re
import smtplib
import subprocess
import sys

from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from os import path
from subprocess import CalledProcessError

EMAIL_SENDER = 'gpu_test@wp-40.sh.intel.com'
SMTP_SERVER = '10.239.47.103'

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

def get_currenttime(format=None):
  time = datetime.datetime.now()
  if format:
    return time.strftime(format)
  return time

def send_email(receivers, subject, body='', attached_files=[]):
  if not receivers:
    return
  if not isinstance(receivers, list):
    receivers = [receivers]
  if not isinstance(attached_files, list):
    attached_files = [attached_files]

  message = MIMEMultipart()
  message['From'] = EMAIL_SENDER
  message['To'] =  email.utils.COMMASPACE.join(receivers)
  message['Subject'] = subject
  message.attach(MIMEText(body, 'plain'))

  for file_name in attached_files:
    attachment = MIMEBase('application', "octet-stream")
    with open(file_name, 'r') as f:
      attachment.set_payload(f.read())
    encoders.encode_base64(attachment)
    attachment.add_header('Content-Disposition', 'attachment; filename="%s"' % path.basename(file_path))
    message.attach(attachment)

  try:
    smtp = smtplib.SMTP(SMTP_SERVER)
    smtp.sendmail(EMAIL_SENDER, receivers, message.as_string())
    smtp.quit()
  except Exception as e:
    print(e)


def execute_command(cmd, print_log=True, return_log=False, save_log=None,
                    dir=None, env=None):
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
          (get_currenttime('%Y/%m/%d %H:%M:%S'),
           ' '.join(cmd),
           path.abspath(dir) if dir else os.getcwd()))

    process = subprocess.Popen(cmd,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        shell=(sys.platform=='win32'), cwd=dir, env=env)

    for line in iter(process.stdout.readline, b''):
      line = line.strip()
      if (line.startswith('Unhandled inspector message') or
          line.startswith('WARNING:root:Unhandled inspector message')):
        continue

      # Generate progress bar
      if print_log and is_ninja_command:
        match = re_match(PATTERN_NINJA_PROGRESS, line)
        if match:
          progress = int(match.group(1)) * 100 / int(match.group(2))
          if progress > last_progress:
            line = '['
            for i in range(0, progress/2):
              line += '='
            line += '>'
            for i in range(progress/2, 50):
              line += ' '
            line += '] %d%%' % progress
            sys.stdout.write('\r' + line)

            current_time = get_currenttime()
            total_time = current_time - start_time
            sys.stdout.write('    Total time: %dmin' % (total_time.total_seconds() / 60))
            if progress == 100:
              sys.stdout.write('\n')
            else:
              time_interval = current_time - last_progress_time
              progress_times.append(time_interval.total_seconds() / (progress - last_progress))
              if len(progress_times) > 10:
                progress_times.pop(0)
              time_remaning =  sum(progress_times) / len(progress_times) * (100 - progress)
              sys.stdout.write('    Time remaining: %dmin' % (time_remaning / 60))
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
    if print_log:
      print(e)
    if return_log:
      log_lines.extend(str(e).split('\n'))
    if save_log:
      if not log_file:
        log_file = open(save_log, 'w')
      log_file.write(str(e))
    raise CalledProcessError(1, cmd, '\n'.join(log_lines))
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
