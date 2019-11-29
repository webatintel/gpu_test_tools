#!/usr/bin/env python

from base_util import *
from os import path

PATTERN_REVISION = r'^Cr-Commit-Position: refs/heads/master@{#(\d+)}$'

def get_chrome_revision(chrome_dir, back_level=0):
  try:
    log = execute_command(['git', 'log', '-1', 'HEAD~%d' % back_level],
                          print_log=False, return_log=True, dir=chrome_dir)
    log_lines = log.split('\n')
    for i in range(len(log_lines)-1, -1, -1):
      match = re_match(PATTERN_REVISION, log_lines[i])
      if match:
        return match.group(1)
  except CalledProcessError:
    pass
  return ''

def get_aquarium_revision(aquarium_dir):
  try:
    aquarium_revision = execute_command(['git', 'rev-parse', 'HEAD'],
                                        print_log=False, return_log=True,
                                        dir=aquarium_dir)
    dawn_revision = execute_command(['git', 'rev-parse', 'HEAD'],
                                    print_log=False, return_log=True,
                                    dir=path.join(aquarium_dir, 'third_party', 'dawn'))
    if aquarium_revision and dawn_revision:
      return '%s_%s' % (aquarium_revision[0:6], dawn_revision[0:6])
  except CalledProcessError:
    pass
  return ''
