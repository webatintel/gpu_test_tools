#!/usr/bin/env python3

import datetime
import os
import sched
import subprocess
import sys
import time
from os import path

FILE_DIR = path.dirname(path.abspath(__file__))
CHROME_DIR   = path.abspath(path.join(FILE_DIR, '..', '..', 'project', 'chromium'))
AQUARIUM_DIR = path.abspath(path.join(FILE_DIR, '..', '..', 'project', 'aquarium'))
RUN_TRYJOB_CMD   = path.join(FILE_DIR, 'bin', 'run_tryjob')
CHECK_TRYJOB_CMD = path.join(FILE_DIR, 'bin', 'check_tryjob')

def execute(cmd, dir=None):
  process = subprocess.Popen(cmd, cwd=dir, shell=(sys.platform=='win32'))
  retcode = process.wait()
  if retcode:
    sys.exit(retcode)

def run_tryjob():
  weekday = datetime.date.today().weekday()
  job_type = ['regular']
  if weekday == 5:
    job_type += ['fyi']
  elif weekday == 6:
    job_type += ['aquarium']

  execute(['git', 'checkout', '.'], FILE_DIR)
  execute(['git', 'fetch', 'origin'], FILE_DIR)
  execute(['git', 'rebase', 'origin/master'], FILE_DIR)
  execute([RUN_TRYJOB_CMD, '--update', '--email', '--job'] + job_type +
          ['--chrome-dir', CHROME_DIR, '--aquarium-dir', AQUARIUM_DIR])
  if sys.platform == 'win32':
    execute([CHECK_TRYJOB_CMD, '--dir', CHROME_DIR, '--email'])

def main():
  scheduler = sched.scheduler(time.time, time.sleep)
  today = datetime.date.today()
  test_time = datetime.datetime(today.year, today.month, today.day, 20, 0)
  while True:
    print("\nNext test time: " + test_time.strftime('%Y/%m/%d %H:%M'))
    scheduler.enterabs(time.mktime(test_time.timetuple()), 1, run_tryjob, ())
    scheduler.run()
    test_time += datetime.timedelta(days=1)

if __name__ == '__main__':
  sys.exit(main())
