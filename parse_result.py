#!/usr/bin/env python

import argparse
import sys

from util.base_util import *
from os import path

PATTERN_RESULT_FAIL = r'^\d+ test(s?) failed:$'
PATTERN_RESULT_CRASH = r'^\d+ test(s?) crashed:$'
PATTERN_RESULT_TIMEOUT = r'^\d+ test(s?) timed out:$'
PATTERN_RESULT_SKIP = r'^\d+ test(s?) not run:$'
PATTERN_CASE_PASS = r'^\[\d+/\d+\] (.+) \(\d+ ms\)$'
PATTERN_CASE_ERROR = r'^(.+) \(.+:\d+\)$'

def parse_arguments():
  parser = argparse.ArgumentParser(
      description='Parse test results and generate report',
      formatter_class=argparse.RawTextHelpFormatter)
  parser.add_argument('target', nargs='?',
      choices=['webgl', 'angle', 'fyi', 'aquarium'], default='webgl',
      help='Specify the test results you want to parse.\n\n'\
           'webgl    :  WebGL and WebGL2 conformance tests\n'\
           'angle    :  ANGLE tests\n'\
           'fyi      :  Miscellaneous less important tests\n'\
           'aquarium :  Aquarium tests\n\n')
  parser.add_argument('--dir', '-d', default='.',
      help='The directory where the results locate in.\n\n')
  args = parser.parse_args()

  args.dir = path.abspath(args.dir)
  return args


class AquariumResult(object):
  def __init__(self, name):
    self.name = name
    self.fps_list = []
    self.average_fps = None


class TestResult(object):
  def __init__(self, name):
    self.name = name
    self.test_suite = None
    self.duration = None
    self.retry = 0
    self.result = None
    self.is_expected = False
    self.is_skipped = False
    self.is_flaky = False
    self.is_timeout = False
    self.is_crash = False


class TestSuite(object):
  def __init__(self, name):
    self.name = name
    self.actual_passed = []
    self.actual_failed = []
    self.flaky_passed = []
    self.unexpected_passed = []
    self.unexpected_failed = []
    self.skipped = []

  def AddResult(self, result):
    result.test_suite = self
    if result.is_skipped:
      self.skipped.append(result)
    elif result.result:
      self.actual_passed.append(result)
      if not result.is_expected:
        self.unexpected_passed.append(result)
      elif result.retry:
        self.flaky_passed.append(result)
    else:
      self.actual_failed.append(result)
      if not result.is_expected:
        self.unexpected_failed.append(result)

  def IsEmpty(self):
    if self.actual_passed or self.actual_failed or self.skipped:
      return False
    return True


def parse_telemetry_result(key, value):
  test_result = TestResult(key)
  actual = value['actual'].split(' ')
  if len(actual) == 1 and actual[0] == 'SKIP':
    test_result.is_skipped = True
    return test_result

  test_result.result = False
  for item in actual:
    test_result.result = test_result.result or item == 'PASS'

  test_result.duration = 0
  for item in value['times']:
    test_result.duration = test_result.duration + item

  if value['actual'] == value['expected']:
    test_result.is_expected = True
  elif test_result.result and value['expected'] == 'PASS':
    test_result.is_expected = True
  elif not test_result.result and value['expected'] == 'FAIL':
    test_result.is_expected = True

  if test_result.result and len(actual) > 1:
    test_result.is_flaky = True

  test_result.retry = len(actual) - 1
  return test_result


def parse_telemetry_result_dict(result_dict, test_suite, prefix=''):
  for key,value in result_dict.iteritems():
    if value.get('actual'):
      test_suite.AddResult(parse_telemetry_result(prefix + key, value))
    else:
      parse_telemetry_result_dict(value, test_suite, prefix + key + '/')


def parse_telemetry_result_file(result_file):
  result_dict = read_json(result_file)
  if not result_dict:
    return
  result_name, result_ext = path.splitext(path.basename(result_file))
  test_suite = TestSuite(result_name)
  parse_telemetry_result_dict(result_dict['tests'], test_suite)
  return test_suite


def parse_angle_result_file(result_file):
  result_name, result_ext = path.splitext(path.basename(result_file))
  test_suite = TestSuite(result_name)
  error_result = ''
  for line in read_line(result_file):
    if error_result:
      match = re_match(PATTERN_CASE_ERROR, line)
      if match:
        result = TestResult(match.group(1))
        if error_result == 'skip':
          result.is_skipped = True
        else:
          result.result = False
          if error_result == 'timeout':
            result.is_timeout = True
          elif error_result == 'crash':
            result.is_crash = True
        test_suite.AddResult(result)
        for i in range(0, len(test_suite.actual_passed)):
          if test_suite.actual_passed[i].name == result.name:
            test_suite.actual_passed.pop(i)
            break
        continue
    else:
      match = re_match(PATTERN_CASE_PASS, line)
      if match:
        result = TestResult(match.group(1))
        result.result = True
        result.is_expected = True
        test_suite.AddResult(result)
        continue

    if re_match(PATTERN_RESULT_FAIL, line):
      error_result = 'fail'
    elif re_match(PATTERN_RESULT_CRASH, line):
      error_result = 'crash'
    elif re_match(PATTERN_RESULT_TIMEOUT, line):
      error_result = 'timeout'
    elif re_match(PATTERN_RESULT_SKIP, line):
      error_result = 'skip'

  return test_suite


def parse_aquarium_result_file(result_file):
  result_name, result_ext = path.splitext(path.basename(result_file))
  is_data_line = False
  for line in read_line(result_file):
    if is_data_line:
      test_result = AquariumResult(result_name)
      fps_sum = 0
      for item in line.split(';'):
        if item:
          test_result.fps_list.append(int(item))
          fps_sum += int(item)
      test_result.average_fps = fps_sum / len(test_result.fps_list)
      return test_result
    elif line == 'Print FPS Data:':
      is_data_line = True


def merge_shard_result(test_suites):
  merged_result = {}
  for test_suite in test_suites:
    name = test_suite.name
    while True:
      name, ext = path.splitext(name)
      if not ext:
        break

    merged_result.setdefault(name, TestSuite(name))
    merged_result[name].actual_passed.extend(test_suite.actual_passed)
    merged_result[name].actual_failed.extend(test_suite.actual_failed)
    merged_result[name].flaky_passed.extend(test_suite.flaky_passed)
    merged_result[name].unexpected_passed.extend(test_suite.unexpected_passed)
    merged_result[name].unexpected_failed.extend(test_suite.unexpected_failed)
    merged_result[name].skipped.extend(test_suite.skipped)

  return merged_result.values()


def generate_test_report(test_suites, detailed_cases):
  report = ''
  if test_suites:
    max_name_len = 0
    for test_suite in test_suites:
      max_name_len = max(max_name_len, len(test_suite.name))
    name_format = '{:<%d}' % (max_name_len+2)

    report += '\nTest Result:\n'
    for test_suite in test_suites:
      report += name_format.format(test_suite.name)
      report += '{:<14}'.format('[Pass:%d]' % len(test_suite.actual_passed))
      report += '{:<11}'.format('[Fail:%d]' % len(test_suite.actual_failed))
      report += '{:<11}'.format('[Skip:%d]' % len(test_suite.skipped))
      report += '{:<17}'.format('[Flaky Pass:%d]' % len(test_suite.flaky_passed))
      report += '{:<15}'.format('[New Pass:%d]' % len(test_suite.unexpected_passed))
      report += '[New Fail:%d]\n' % len(test_suite.unexpected_failed)

  if detailed_cases:
    for name, results in detailed_cases.items():
      report += '\n%s:\n' % name
      for result in results:
        report += '%s\n' % result
  return report


def dump_telemetry_result(args):
  test_suites = []
  for item in list_file(args.dir):
    file_name = path.basename(item)
    if file_name.startswith(args.target) and file_name.endswith('.json'):
      test_suite = parse_telemetry_result_file(item)
      if not test_suite.IsEmpty():
        test_suites.append(test_suite)
  if not test_suites:
    return

  test_suites = merge_shard_result(test_suites)
  detailed_cases = {}
  for test_suite in test_suites:
    if test_suite.flaky_passed:
      detailed_cases.setdefault('Flaky Pass', [])
      for test_result in test_suite.flaky_passed:
        result = '%s    %s' % (test_result.test_suite.name, test_result.name)
        detailed_cases['Flaky Pass'].append(result)

    if test_suite.unexpected_passed:
      detailed_cases.setdefault('New Pass', [])
      for test_result in test_suite.unexpected_passed:
        result = '%s    %s' % (test_result.test_suite.name, test_result.name)
        detailed_cases['New Pass'].append(result)

    if test_suite.unexpected_failed:
      detailed_cases.setdefault('New Fail', [])
      for test_result in test_suite.unexpected_failed:
        result = '%s    %s' % (test_result.test_suite.name, test_result.name)
        detailed_cases['New Fail'].append(result)

  return generate_test_report(test_suites, detailed_cases)


def dump_angle_result(args):
  test_suites = []
  for item in list_file(args.dir):
    file_name = path.basename(item)
    if file_name.startswith('angle') and file_name.endswith('.log'):
      test_suite = parse_angle_result_file(item)
      if not test_suite.IsEmpty():
        test_suites.append(test_suite)
  if not test_suites:
    return

  test_suites = merge_shard_result(test_suites)
  detailed_cases = {}
  for test_suite in test_suites:
    if test_suite.unexpected_failed:
      detailed_cases.setdefault('New Fail', [])
      for test_result in test_suite.unexpected_failed:
        result = '%s    %s' % (test_result.test_suite.name, test_result.name)
        detailed_cases['New Fail'].append(result)

  return generate_test_report(test_suites, detailed_cases)


def dump_aquarium_result(args):
  test_results = []
  for item in list_file(args.dir):
    file_name = path.basename(item)
    if file_name.startswith('aquarium') and file_name.endswith('.log'):
      test_result = parse_aquarium_result_file(item)
      if test_result:
        test_results.append(test_result)
  if not test_results:
    return

  detailed_cases = {}
  detailed_cases['Average FPS'] = []
  for test_result in test_results:
    result = '%s    %d' % (test_result.name, test_result.average_fps)
    detailed_cases['Average FPS'].append(result)
  return generate_test_report(None, detailed_cases)


def main():
  args = parse_arguments()
  if args.target == 'webgl' or args.target == 'fyi':
    report = dump_telemetry_result(args)
  elif args.target == 'angle':
    report = dump_angle_result(args)
  elif args.target == 'aquarium':
    report = dump_aquarium_result(args)

  if report:
    print(report)

  return 0


if __name__ == '__main__':
  sys.exit(main())
