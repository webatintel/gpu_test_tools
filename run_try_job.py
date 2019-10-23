#!/usr/bin/env python

import argparse
import sys

from gpu_test_util import *
from os import path

TRY_JOB_CONFIG = path.join(path.dirname(path.abspath(__file__)), 'try_job.json')

def parse_arguments():
  parser = argparse.ArgumentParser(
      description='Run try jobs\n'\
                  'The test configuration is defined in try_job.json.\n\n',
      formatter_class=argparse.RawTextHelpFormatter)
  parser.add_argument('--build', '-b',
      choices=['release', 'debug', 'default'], default='release',
      help='Build type. Default is \'release\'.\n'\
           'release/debug/default assume that the binaries are\n'\
           'generated into out/Release or out/Debug or out/Default.\n\n')
  parser.add_argument('--chrome-dir', '-c',
      help='Chrome source directory.\n\n')
  parser.add_argument('--aquarium-dir', '-a',
      help='Aquarium source directory.\n\n')
  parser.add_argument('--sync', '-s', action='store_true',
      help='Fetch latest source code and rebuild before running tests.\n\n')
  parser.add_argument('--pack', '-p', action='store_true',
      help='Package the binaries to a standalone directory.\n\n')
  parser.add_argument('--email', '-e', action='store_true',
      help='Send the report by email.\n\n')
  args = parser.parse_args()

  if args.chrome_dir:
    args.chrome_dir = path.abspath(args.chrome_dir)
    if path.exists(path.join(args.chrome_dir, 'src')):
      args.chrome_dir = path.join(args.chrome_dir, 'src')

  if args.aquarium_dir:
    args.aquarium_dir = path.abspath(args.aquarium_dir)

  # Load configuration
  config = read_json(TRY_JOB_CONFIG)
  args.report_receivers = config['report_receivers']

  if is_win():
    args.try_jobs = config['win_jobs']
  elif is_linux():
    args.try_jobs = config['linux_jobs']
  elif is_mac():
    args.try_jobs = config['mac_jobs']

  args.try_job_args = config['try_job_args']
  args.try_job_shards = config['try_job_shards']

  return args


def notify_command_error(receivers, error):
  send_email(receivers,
             '%s failed on %s' % (error.cmd[0], get_hostname()),
             '%s\n\n%s' % (' '.join(error.cmd), error.output))


def main():
  args = parse_arguments()

  # Update and package Chrome
  if args.chrome_dir:
    if args.sync:
      try:
        execute_command(['build_chrome', 'sync', 'gen', 'build', 'pack', '--build', args.build, '--dir', args.chrome_dir],
                        return_log=True)
      except CalledProcessError as e:
        notify_command_error(args.report_receivers['admin'], e)

    args.chrome_revision = execute_command(['build_chrome', 'rev', '--dir', args.chrome_dir],
                                           print_log=False, return_log=True)

    if args.pack:
      pack_dir = path.abspath('chrome')
      assert not path.exists(pack_dir)
      try:
        execute_command(['build_chrome', 'pack', '--build', args.build, '--dir', args.chrome_dir, '--pack-dir', pack_dir],
                        return_log=True)
        args.chrome_dir = pack_dir
      except CalledProcessError as e:
        notify_command_error(args.report_receivers['admin'], e)

  # Update and package Aquarium
  if args.aquarium_dir:
    if args.sync:
      try:
        execute_command(['build_aquarium', 'sync', 'gen', 'build', 'pack', '--build', args.build, '--dir', args.aquarium_dir],
                        return_log=True)
      except CalledProcessError as e:
        notify_command_error(args.report_receivers['aquarium'], e)

    args.aquarium_revision = execute_command(['build_aquarium', 'rev', '--dir', args.aquarium_dir],
                                             print_log=False, return_log=True)

    if args.pack:
      pack_dir = path.abspath('aquarium')
      assert not path.exists(pack_dir)
      try:
        execute_command(['build_aquarium', 'pack', '--build', args.build, '--dir', args.aquarium_dir, '--pack-dir', pack_dir],
                        return_log=True)
        args.aquarium_dir = pack_dir
      except CalledProcessError as e:
        notify_command_error(args.report_receivers['admin'], e)

  # Run tests
  target_set = set()
  for job in args.try_jobs:
    target = args.try_job_args[job][0]
    backend = args.try_job_args[job][1]
    shard = 1
    for key in ['%s_%s' % (target, backend), target]:
      if args.try_job_shards.has_key(key):
        shard = args.try_job_shards[key]
        break

    cmd = ['run_gpu_test', target, '--build', args.build]
    if backend:
      cmd.extend(['--backend', backend])
    if shard > 1:
      cmd.extend(['--shard', str(shard)])
    if target == 'aquarium':
      assert args.aquarium_dir
      cmd.extend(['--dir', args.aquarium_dir])
    else:
      assert args.chrome_dir
      cmd.extend(['--dir', args.chrome_dir])

    try:
      execute_command(cmd, return_log=True)
      if target.startswith('webgl'):
        target_set.add('webgl')
      else:
        target_set.add(target)
    except CalledProcessError as e:
      notify_command_error(args.report_receivers['admin'], e)

  # Dump test results
  for target in target_set:
    try:
      report = execute_command(['parse_result', target], print_log=False, return_log=True)
      if report:
        header = 'Location: %s\n' % os.getcwd()
        revision = args.aquarium_revision if target == 'aquarium' else args.chrome_revision
        if revision:
          header += 'Revision: %s\n' % revision
        report = header + report

        print('\n--------------------------------------------------\n')
        print(report)
        write_file('%s_test_report.txt' % target, report)
        if args.email:
          send_email(args.report_receivers[target],
                     '%s test report - %s / %s' % (target, get_osname(), get_hostname()),
                     report)
    except CalledProcessError as e:
      notify_command_error(args.report_receivers['admin'], e)

  return 0


if __name__ == '__main__':
  sys.exit(main())
