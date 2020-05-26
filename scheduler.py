#!/usr/bin/env python3

import datetime
import os
import sched
import subprocess
import sys
import time

from os import path

REPOSITORY_DIR = path.dirname(path.abspath(__file__))
CHROME_DIR   = path.abspath(path.join(REPOSITORY_DIR, '..', '..', 'project', 'chromium'))
AQUARIUM_DIR = path.abspath(path.join(REPOSITORY_DIR, '..', '..', 'project', 'aquarium'))
RUN_TRYJOB   = path.join(REPOSITORY_DIR, 'bin', 'run_tryjob')
CHECK_TRYJOB = path.join(REPOSITORY_DIR, 'bin', 'check_tryjob')

def execute(command, dir=None):
  subprocess.run(command, cwd=dir, shell=(sys.platform=='win32'))

def run_tryjob(job_type):
  execute(['git', 'checkout', '.'], REPOSITORY_DIR)
  execute(['git', 'fetch', 'origin'], REPOSITORY_DIR)
  execute(['git', 'rebase', 'origin/master'], REPOSITORY_DIR)
  execute([RUN_TRYJOB, '--update', '--email', '--job'] + job_type +
          ['--chrome-dir', CHROME_DIR, '--aquarium-dir', AQUARIUM_DIR])
  if sys.platform == 'win32':
    execute([CHECK_TRYJOB, '--dir', CHROME_DIR, '--email'])

def main():
  scheduler = sched.scheduler(time.time, time.sleep)
  test_time = None
  while True:
    today = datetime.date.today()
    if not test_time or today > test_time.date():
      test_date = today
    else:
      test_date = today + datetime.timedelta(days=1)
    test_time = datetime.datetime(test_date.year, test_date.month, test_date.day, 20, 0)
    print('\nTest time: ' + test_time.strftime('%Y/%m/%d %H:%M'))

    job_type = ['regular']
    job_type += ['fyi'] if test_time.isoweekday() == 6 else []
    job_type += ['aquarium'] if test_time.isoweekday() == 7 else []
    scheduler.enterabs(time.mktime(test_time.timetuple()), 1, run_tryjob, (job_type,))
    scheduler.run()

if __name__ == '__main__':
  sys.exit(main())
