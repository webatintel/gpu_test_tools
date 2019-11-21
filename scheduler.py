#!/usr/bin/env python

import datetime
import os
import subprocess
import sys

def execute_command(cmd, dir):
  process = subprocess.Popen(cmd, shell=(sys.platform == 'win32'), cwd=dir)
  retcode = process.wait()
  if retcode:
    sys.exit(retcode)

def main():
  file_dir= os.path.dirname(os.path.abspath(__file__))
  workspace_dir = os.path.abspath(os.path.join(file_dir, '..', '..'))
  gpu_test_dir = os.path.join(workspace_dir, 'gpu_test')
  project_dir = os.path.join(workspace_dir, 'project')

  while True:
    execute_command(['git', 'fetch', 'origin'], file_dir)
    execute_command(['git', 'rebase', 'origin/master'], file_dir)

    current_time = datetime.datetime.now().strftime('%Y_%m%d_%H%M')
    test_dir = os.path.join(gpu_test_dir, current_time)
    os.makedirs(test_dir)
    execute_command(['run_try_job',
                     '--type', 'default',
                     '--chrome-dir', os.path.join(project_dir, 'chromium'),
                     '--aquarium-dir', os.path.join(project_dir, 'aquarium'),
                     '--update',
                     '--email'],
                    test_dir)

if __name__ == '__main__':
  sys.exit(main())
