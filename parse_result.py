#!/usr/bin/env python3

import argparse
import os
import sys

from util.base_util import *
from util.file_util import *
from os import path

PATTERN_UNITTEST_RESULT_FAIL    = r'^\d+ test(s?) failed:$'
PATTERN_UNITTEST_RESULT_CRASH   = r'^\d+ test(s?) crashed:$'
PATTERN_UNITTEST_RESULT_TIMEOUT = r'^\d+ test(s?) timed out:$'
PATTERN_UNITTEST_RESULT_SKIP    = r'^\d+ test(s?) not run:$'
PATTERN_UNITTEST_CASE  = r'^\[\d+/\d+\] (.+) \(\d+ ms\)$'
PATTERN_UNITTEST_ERROR = r'^(.+) \(.+:\d+\)$'

PATTERN_GTEST_RESULT_OK   = r'^\[\s+OK\s+\] ([\w\./<>]+) \(\d+ ms\)$'
PATTERN_GTEST_RESULT_SKIP = r'^\[\s+SKIPPED\s+\] ([\w\./<>]+) \(\d+ ms\)$'
PATTERN_GTEST_RESULT_FAIL = r'^\[\s+FAILED\s+\] ([\w\./<>]+), .+ \(\d+ ms\)$'
PATTERN_GTEST_RESULT_OVER = r'^\[=+\] \d+ tests from \d+ test suites ran\. \(\d+ ms total\)$'

PATTERN_AVERAGE_FPS = r'^Avg FPS: (\d+)$'

def parse_arguments():
  config = read_json(TRYJOB_CONFIG)
  test_set = set()
  for _, test_arg, _, _ in config['tryjob']:
    test_set.add(test_arg[0])

  parser = argparse.ArgumentParser(
      description='Parse test result and generate report',
      formatter_class=argparse.RawTextHelpFormatter)
  parser.add_argument('--result-type', '--type', '-t', nargs='+',
      choices=sorted(list(test_set)), default=sorted(list(test_set - set(['aquarium']))),
      help='What type of test result to parse, you can specify multiple. Default is all except aquarium.\n\n')
  parser.add_argument('--result-dir', '--dir', '-d', default='.',
      help='The directory where the result files are located. Default is current directory.\n\n')
  args = parser.parse_args()

  if 'aquarium' in args.result_type and len(args.result_type) > 1:
    raise Exception('Can not merge aquarium result with others')

  args.test_names = []
  args.test_name_map = {}
  for test_name, test_arg, _, _ in config['tryjob']:
    pos = test_name.find('(')
    if pos > 0:
      test_name = test_name[0:pos]
    args.test_names.append(test_name)
    args.test_name_map.setdefault(test_arg[0], [])
    args.test_name_map[test_arg[0]].append(test_name)

  args.result_dir = path.abspath(args.result_dir)
  return args


class PerfResult(object):
  def __init__(self, name):
    self.name = name
    self.average_fps = None


class TestResult(object):
  def __init__(self, name):
    self.name = name
    self.suite_name = None
    # True->Pass; False->Fail; None->Skip
    self.result = None
    self.is_expected = False
    self.is_flaky = False
    self.is_timeout = False
    self.is_crash = False
    self.retry = 0
    self.duration = None


class TestSuite(object):
  def __init__(self, name):
    self.name = name
    self.actual_passed = []
    self.actual_failed = []
    self.flaky_passed = []
    self.unexpected_passed = []
    self.unexpected_failed = []
    self.skipped = []

  def __iadd__(self, other):
    self.actual_passed += other.actual_passed
    self.actual_failed += other.actual_failed
    self.flaky_passed += other.flaky_passed
    self.unexpected_passed += other.unexpected_passed
    self.unexpected_failed += other.unexpected_failed
    self.skipped += other.skipped
    return self

  def __bool__(self):
    return bool(self.actual_passed or self.actual_failed or self.skipped)

  def AddResult(self, result):
    result.suite_name = self.name
    if result.result is None:
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


def parse_json_result(key, value):
  test_result = TestResult(key)
  actual = value['actual'].split(' ')
  if len(actual) == 1 and actual[0] == 'SKIP':
    return test_result

  test_result.result = False
  for item in actual:
    test_result.result |= (item == 'PASS')

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

  if 'time' in value:
    test_result.duration = value['time']
  elif 'times' in value:
    test_result.duration = 0
    for item in value['times']:
      test_result.duration += item
  return test_result


def parse_json_result_dict(result_dict, test_suite, prefix=''):
  for key, value in result_dict.items():
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


def parse_unittest_result_file(result_file):
  result_name, result_ext = path.splitext(path.basename(result_file))
  test_suite = TestSuite(result_name)
  error_result = ''
  for line in read_line(result_file):
    line = line.strip()
    if error_result:
      match = re_match(PATTERN_UNITTEST_ERROR, line)
      if match:
        result = TestResult(match.group(1))
        if error_result != 'skip':
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
      match = re_match(PATTERN_UNITTEST_CASE, line)
      if match:
        result = TestResult(match.group(1))
        result.result = True
        result.is_expected = True
        test_suite.AddResult(result)
        continue

    if re_match(PATTERN_UNITTEST_RESULT_FAIL, line):
      error_result = 'fail'
    elif re_match(PATTERN_UNITTEST_RESULT_CRASH, line):
      error_result = 'crash'
    elif re_match(PATTERN_UNITTEST_RESULT_TIMEOUT, line):
      error_result = 'timeout'
    elif re_match(PATTERN_UNITTEST_RESULT_SKIP, line):
      error_result = 'skip'

  return test_suite


def parse_gtest_result_file(result_file):
  result_name, result_ext = path.splitext(path.basename(result_file))
  test_suite = TestSuite(result_name)
  for line in read_line(result_file):
    line = line.strip()
    if re_match(PATTERN_GTEST_RESULT_OVER, line):
      break

    match = re_match(PATTERN_GTEST_RESULT_OK, line)
    if match:
      result = TestResult(match.group(1))
      result.result = True
      result.is_expected = True
      test_suite.AddResult(result)
      continue

    match = re_match(PATTERN_GTEST_RESULT_SKIP, line)
    if match:
      result = TestResult(match.group(1))
      test_suite.AddResult(result)
      continue

    match = re_match(PATTERN_GTEST_RESULT_FAIL, line)
    if match:
      result = TestResult(match.group(1))
      result.result = False
      test_suite.AddResult(result)
      continue

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


def generate_test_report(test_suites):
  max_name_len = 0
  has_new_fail = False
  has_new_pass = False
  has_flaky_pass = False
  for test_suite in test_suites:
    max_name_len = max(max_name_len, len(test_suite.name))
    has_new_fail |= bool(test_suite.unexpected_failed)
    has_new_pass |= (bool(test_suite.unexpected_passed) and not test_suite.name.startswith('webgpu_blink'))
    has_flaky_pass |= bool(test_suite.flaky_passed)

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

  if has_new_fail:
    report += '\nNew Fail:\n'
    for test_suite in test_suites:
      for test_result in test_suite.unexpected_failed:
        report += '%s    %s\n' % (test_result.suite_name, test_result.name)

  if has_new_pass:
    report += '\nNew Pass:\n'
    for test_suite in test_suites:
      if test_suite.name.startswith('webgpu_blink'):
        continue
      for test_result in test_suite.unexpected_passed:
        report += '%s    %s\n' % (test_result.suite_name, test_result.name)

  if has_flaky_pass:
    report += '\nFlaky Pass:\n'
    for test_suite in test_suites:
      for test_result in test_suite.flaky_passed:
        report += '%s    %s\n' % (test_result.suite_name, test_result.name)

  return report


def main():
  args = parse_arguments()

  def find_result_file(test):
    for file_path in list_file(args.result_dir):
      if test in ['webgl', 'webgl2', 'blink']:
        result_ext = 'json'
      elif test in ['gpu', 'angle', 'dawn', 'aquarium']:
        result_ext = 'log'
      file_name = path.basename(file_path)
      if not file_name.endswith(result_ext):
        continue
      for name in args.test_name_map[test]:
        if file_name.startswith(name):
          yield file_path
          break

  if args.result_type == ['aquarium']:
    perf_results = []
    max_name_len = 0
    for result_file in find_result_file('aquarium'):
      result = parse_aquarium_result_file(result_file)
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
    merged_result = {}
    for test in args.result_type:
      for result_file in find_result_file(test):
        if test in ['webgl', 'webgl2', 'blink']:
          test_suite = parse_json_result_file(result_file)
        elif test in ['dawn', 'angle', 'gpu']:
          test_suite = parse_unittest_result_file(result_file)
          if not test_suite:
            test_suite = parse_gtest_result_file(result_file)
        if test_suite:
          name, ext = path.splitext(test_suite.name)
          while ext:
            name, ext = path.splitext(name)
          merged_result.setdefault(name, TestSuite(name))
          merged_result[name] += test_suite

    if merged_result:
      sorted_suites = []
      for name in args.test_names:
        if name in merged_result:
          sorted_suites.append(merged_result.pop(name))
      assert not merged_result
      print(generate_test_report(sorted_suites), end='')


if __name__ == '__main__':
  sys.exit(main())
