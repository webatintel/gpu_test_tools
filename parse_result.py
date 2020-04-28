#!/usr/bin/env python

import argparse
import os
import sys

from util.base_util import *
from util.file_util import *
from os import path

PATTERN_GTEST_RESULT_FAIL = r'^\d+ test(s?) failed:$'
PATTERN_GTEST_RESULT_CRASH = r'^\d+ test(s?) crashed:$'
PATTERN_GTEST_RESULT_TIMEOUT = r'^\d+ test(s?) timed out:$'
PATTERN_GTEST_RESULT_SKIP = r'^\d+ test(s?) not run:$'
PATTERN_GTEST_CASE = r'^\[\d+/\d+\] (.+) \(\d+ ms\)$'
PATTERN_GTEST_ERROR = r'^(.+) \(.+:\d+\)$'
PATTERN_DAWN_RESULT_START = r'^\[=+\] \d+ tests from \d+ test suites ran\. \(\d+ ms total\)$'
PATTERN_DAWN_RESULT_OK = r'^\[\s+OK\s+\] ([\w\./<>]+) \(\d+ ms\)$'
PATTERN_DAWN_RESULT_SKIP = r'^\[\s+SKIPPED\s+\] ([\w\./]+)$'
PATTERN_DAWN_RESULT_FAIL = r'^\[\s+FAILED\s+\] ([\w\./]+),.+$'
PATTERN_AVERAGE_FPS = r'^Avg FPS: (\d+)$'

TRYJOB_CONFIG = path.join(path.dirname(path.abspath(__file__)), 'tryjob.json')

def parse_arguments():
  parser = argparse.ArgumentParser(
      description='Parse test results and generate report',
      formatter_class=argparse.RawTextHelpFormatter)
  parser.add_argument('--test-type', '--type', '-t', nargs='+',
      choices=['webgl', 'blink', 'dawn', 'angle', 'gpu', 'aquarium'],
      default=['webgl', 'blink', 'dawn', 'angle', 'gpu'],
      help='The test results to parse, you can specify multiple. Default is all except aquarium.\n\n')
  parser.add_argument('--result-dir', '--dir', '-d', default='.',
      help='The directory where the results locate in.\n\n')
  args = parser.parse_args()

  if 'aquarium' in args.test_type and len(args.test_type) > 1:
    raise Exception('Can not merge aquarium result with other results')

  args.result_dir = path.abspath(args.result_dir)
  return args


class PerfResult(object):
  def __init__(self, name):
    self.name = name
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


def parse_json_result(key, value):
  test_result = TestResult(key)
  actual = value['actual'].split(' ')
  if len(actual) == 1 and actual[0] == 'SKIP':
    test_result.is_skipped = True
    return test_result

  test_result.result = False
  for item in actual:
    test_result.result = test_result.result or item == 'PASS'

  if 'time' in value:
    test_result.duration = value['time']
  elif 'times' in value:
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
  if value['actual'] == 'CRASH':
    test_result.is_crash = True
  elif value['actual'] == 'TIMEOUT':
    test_result.is_timeout = True

  test_result.retry = len(actual) - 1
  return test_result


def parse_json_result_dict(result_dict, test_suite, prefix=''):
  for key,value in result_dict.items():
    if 'actual' in value and 'expected' in value:
      test_suite.AddResult(parse_json_result(prefix + key, value))
    else:
      parse_json_result_dict(value, test_suite, prefix + key + '/')


def parse_json_result_file(result_file):
  result_name, result_ext = path.splitext(path.basename(result_file))
  test_suite = TestSuite(result_name)
  result_dict = read_json(result_file)
  parse_json_result_dict(result_dict['tests'], test_suite)
  return test_suite


def parse_gtest_result_file(result_file):
  result_name, result_ext = path.splitext(path.basename(result_file))
  test_suite = TestSuite(result_name)
  error_result = ''
  for line in read_line(result_file):
    line = line.strip()
    if error_result:
      match = re_match(PATTERN_GTEST_ERROR, line)
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
      match = re_match(PATTERN_GTEST_CASE, line)
      if match:
        result = TestResult(match.group(1))
        result.result = True
        result.is_expected = True
        test_suite.AddResult(result)
        continue

    if re_match(PATTERN_GTEST_RESULT_FAIL, line):
      error_result = 'fail'
    elif re_match(PATTERN_GTEST_RESULT_CRASH, line):
      error_result = 'crash'
    elif re_match(PATTERN_GTEST_RESULT_TIMEOUT, line):
      error_result = 'timeout'
    elif re_match(PATTERN_GTEST_RESULT_SKIP, line):
      error_result = 'skip'

  return test_suite


def parse_dawn_result_file(result_file):
  result_name, result_ext = path.splitext(path.basename(result_file))
  test_suite = TestSuite(result_name)
  test_result_started = False
  for line in read_line(result_file):
    line = line.strip()
    if not test_result_started:
      if re_match(PATTERN_DAWN_RESULT_START, line):
        test_result_started = True
        continue

      match = re_match(PATTERN_DAWN_RESULT_OK, line)
      if match:
        result = TestResult(match.group(1))
        result.result = True
        result.is_expected = True
        test_suite.AddResult(result)

    else:
      match = re_match(PATTERN_DAWN_RESULT_SKIP, line)
      if match:
        result = TestResult(match.group(1))
        result.is_skipped = True
        test_suite.AddResult(result)
        continue

      match = re_match(PATTERN_DAWN_RESULT_FAIL, line)
      if match:
        result = TestResult(match.group(1))
        result.result = False
        test_suite.AddResult(result)

  return test_suite


def parse_aquarium_result_file(result_file):
  result_name, result_ext = path.splitext(path.basename(result_file))
  for line in read_line(result_file):
    line = line.strip()
    match = re_match(PATTERN_AVERAGE_FPS, line)
    if match:
      result = PerfResult(result_name)
      result.average_fps = int(match.group(1))
      return result


def merge_shard_result(test_suites):
  config = read_json(TRYJOB_CONFIG)
  merged_result = {}
  for test_suite in test_suites:
    name = test_suite.name
    while True:
      name, ext = path.splitext(name)
      if not ext:
        break
    test_type, backend = name.split('_', 1)
    for test_name, _, test_arg, _ in config['tryjob']:
      if test_arg[0] == test_type and test_arg[1] == backend:
        name = test_name
        break

    merged_result.setdefault(name, TestSuite(name))
    merged_result[name].actual_passed += test_suite.actual_passed
    merged_result[name].actual_failed += test_suite.actual_failed
    merged_result[name].flaky_passed += test_suite.flaky_passed
    merged_result[name].unexpected_passed += test_suite.unexpected_passed
    merged_result[name].unexpected_failed += test_suite.unexpected_failed
    merged_result[name].skipped += test_suite.skipped

  return sorted(merged_result.values(), key=lambda suite: suite.name)


def generate_test_report(test_suites):
  max_name_len = 0
  detailed_cases = {}
  for test_suite in test_suites:
    max_name_len = max(max_name_len, len(test_suite.name))
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

  name_format = '{:<%d}' % (max_name_len+2)
  report = 'Test Result:\n'
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


def main():
  args = parse_arguments()

  if args.test_type == ['aquarium']:
    perf_results = []
    max_name_len = 0
    for file_name in list_file(args.result_dir):
      file_name = path.basename(file_name)
      if file_name.startswith('aquarium') and file_name.endswith('.log'):
        result = parse_aquarium_result_file(file_name)
        if result and result.average_fps > 0:
          perf_results.append(result)
          max_name_len = max(max_name_len, len(result.name))

    if perf_results:
      report = 'Average FPS:\n'
      name_format = '{:<%d}' % (max_name_len+2)
      for result in perf_results:
        report += '%s%d\n' % (name_format.format(result.name), result.average_fps)
      print(report, end='')
  else:
    test_suites = []
    for test_type in args.test_type:
      for file_name in list_file(args.result_dir):
        file_name = path.basename(file_name)
        test_suite = None
        if test_type in ['webgl', 'blink']:
          if file_name.startswith(test_type) and file_name.endswith('.json'):
            test_suite = parse_json_result_file(file_name)
        elif test_type in ['angle', 'gpu']:
          if file_name.startswith(test_type) and file_name.endswith('.log'):
            test_suite = parse_gtest_result_file(file_name)
        elif test_type == 'dawn':
          if file_name.startswith('dawn') and file_name.endswith('.log'):
            test_suite = parse_dawn_result_file(file_name)
        if test_suite and not test_suite.IsEmpty():
          test_suites.append(test_suite)

    if test_suites:
      test_suites = merge_shard_result(test_suites)
      report = generate_test_report(test_suites)
      if report:
        print(report, end='')

  return 0


if __name__ == '__main__':
  sys.exit(main())
