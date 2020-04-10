#!/usr/bin/env python

import datetime
import os
import sched
import subprocess
import sys
import time

TEST_TIME = '20:00'

FILE_DIR= os.path.dirname(os.path.abspath(__file__))
WORKSPACE_DIR = os.path.abspath(os.path.join(FILE_DIR, '..', '..'))
GPU_TEST_DIR = os.path.join(WORKSPACE_DIR, 'gpu_test')
PROJECT_DIR = os.path.join(WORKSPACE_DIR, 'project')


def execute_command(cmd, dir=None):
  process = subprocess.Popen(cmd, shell=(sys.platform == 'win32'), cwd=dir)
  retcode = process.wait()
  if retcode:
    sys.exit(retcode)


def run_try_job():
  execute_command(['git', 'fetch', 'origin'], FILE_DIR)
  execute_command(['git', 'rebase', 'origin/master'], FILE_DIR)
  execute_command(['git', 'checkout', 'master'],
                  os.path.join(PROJECT_DIR, 'chromium', 'src'))

  current_time = datetime.datetime.now().strftime('%Y_%m%d_%H%M')
  test_dir = os.path.join(GPU_TEST_DIR, current_time)
  os.makedirs(test_dir)
  execute_command(['run_try_job',
                   '--type', 'default',
                   '--chrome-dir', os.path.join(PROJECT_DIR, 'chromium'),
                   '--aquarium-dir', os.path.join(PROJECT_DIR, 'aquarium'),
                   '--update',
                   '--email'],
                  test_dir)

  execute_command(['check_try_job',
                   '--dir', os.path.join(PROJECT_DIR, 'chromium'),
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
