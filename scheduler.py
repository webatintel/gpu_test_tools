#!/usr/bin/env python

import datetime
import os
import sched
import subprocess
import sys
import time
from os import path

TEST_TIME = '20:00'

FILE_DIR= path.dirname(path.abspath(__file__))
BIN_DIR= path.join(FILE_DIR, 'bin')
PROJECT_DIR = path.abspath(path.join(FILE_DIR, '..', '..', 'project'))

def execute_command(cmd, dir=None):
  process = subprocess.Popen(cmd, shell=(sys.platform=='win32'), cwd=dir)
  retcode = process.wait()
  if retcode:
    sys.exit(retcode)

def run_try_job():
  execute_command(['git', 'checkout', '.'], FILE_DIR)
  execute_command(['git', 'fetch', 'origin'], FILE_DIR)
  execute_command(['git', 'rebase', 'origin/master'], FILE_DIR)

  execute_command([path.join(BIN_DIR, 'run_tryjob'),
                   '--job', 'webgl', 'webgpu', 'dawn', 'angle', 'gpu', 'aquarium',
                   '--chrome-dir', path.join(PROJECT_DIR, 'chromium'),
                   '--aquarium-dir', path.join(PROJECT_DIR, 'aquarium'),
                   '--update', '--email'])
  execute_command([path.join(BIN_DIR, 'check_tryjob'),
                   '--dir', path.join(PROJECT_DIR, 'chromium'),
                   '--email'])

def main():
  scheduler = sched.scheduler(time.time, time.sleep)
  today = datetime.date.today()
  test_time = datetime.datetime(
      today.year, today.month, today.day,
      int(TEST_TIME.split(':')[0]), int(TEST_TIME.split(':')[1]))
  while True:
    print("\nNext test time: " + test_time.strftime('%Y/%m/%d %H:%M'))
    scheduler.enterabs(time.mktime(test_time.timetuple()), 1, run_try_job, ())
    scheduler.run()
    test_time += datetime.timedelta(days=1)

if __name__ == '__main__':
  sys.exit(main())
