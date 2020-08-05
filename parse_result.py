#!/usr/bin/env python3

import argparse

from util.base_util import *
from util.file_util import *

PATTERN_UNITTEST_RESULT_FAIL          = r'^\d+ test(s?) failed:$'
PATTERN_UNITTEST_RESULT_FAIL_EXPECTED = r'^\d+ test(s?) failed as expected:$'
PATTERN_UNITTEST_RESULT_CRASH         = r'^\d+ test(s?) crashed:$'
PATTERN_UNITTEST_RESULT_TIMEOUT       = r'^\d+ test(s?) timed out:$'
PATTERN_UNITTEST_RESULT_SKIP          = r'^\d+ test(s?) not run:$'
PATTERN_UNITTEST_CASE  = r'^\[\d+/\d+\] (.+) \(\d+ ms\)$'
PATTERN_UNITTEST_ERROR = r'^(.+) \(.+:\d+\)$'

PATTERN_GTEST_RESULT_OK   = r'^\[\s+OK\s+\] ([\w\./<>]+) \(\d+ ms\)$'
PATTERN_GTEST_RESULT_SKIP = r'^\[\s+SKIPPED\s+\] ([\w\./<>]+) \(\d+ ms\)$'
PATTERN_GTEST_RESULT_FAIL = r'^\[\s+FAILED\s+\] ([\w\./<>]+), .+ \(\d+ ms\)$'
PATTERN_GTEST_RESULT_OVER = r'^\[=+\] \d+ tests from \d+ test suites ran\. \(\d+ ms total\)$'

PATTERN_AVERAGE_FPS = r'^Avg FPS: (\d+)$'

def parse_arguments():
  config = load_tryjob_config()
  module_set = set()
  for _, test_type, _, _ in config['tryjob']:
    module_set.add(test_type[0])

  parser = argparse.ArgumentParser(
      description='Parse test result and generate report',
      formatter_class=argparse.RawTextHelpFormatter)
  parser.add_argument('--result-type', '--type', '-t', nargs='+',
      choices=sorted(list(module_set)), default=sorted(list(module_set - set(['aquarium']))),
      help='What type of test result to parse, you can specify multiple. Default is all except aquarium.\n\n')
  parser.add_argument('--result-dir', '--dir', '-d', default='.',
      help='The directory where the result files are located. Default is current directory.\n\n')
  args = parser.parse_args()

  if 'aquarium' in args.result_type and len(args.result_type) > 1:
    raise Exception('Can not merge aquarium result with others')

  args.result_order, args.module_to_name = [], defaultdict(list)
  for test_name, test_type, _, _ in config['tryjob']:
    args.result_order.append(test_name)
    args.module_to_name[test_type[0]].append(test_name)

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
    self.retry = 0
    self.is_flaky = False
    self.is_timeout = False
    self.is_crash = False
    self.is_expected = False
    self.duration = None


class TestSuite(object):
  def __init__(self, name):
    self.name = name
    self.actual_pass = []
    self.actual_fail = []
    self.skip = []
    self.flaky_pass = []
    self.unexpected_pass = []
    self.unexpected_fail = []

  def __iadd__(self, other):
    self.actual_pass += other.actual_pass
    self.actual_fail += other.actual_fail
    self.skip += other.skip
    self.flaky_pass += other.flaky_pass
    self.unexpected_pass += other.unexpected_pass
    self.unexpected_fail += other.unexpected_fail
    return self

  def __bool__(self):
    return bool(self.actual_pass) or bool(self.actual_fail) or bool(self.skip)

  def AddResult(self, result):
    result.suite_name = self.name
    if result.result is None:
      self.skip.append(result)
    elif result.result:
      self.actual_pass.append(result)
      if not result.is_expected:
        self.unexpected_pass.append(result)
      elif result.is_flaky:
        self.flaky_pass.append(result)
    else:
      self.actual_fail.append(result)
      if not result.is_expected:
        self.unexpected_fail.append(result)

  def RemovePass(self, name):
    for pass_list in [self.actual_pass, self.unexpected_pass, self.flaky_pass]:
      index = index_match(pass_list, lambda x: x.name == name)
      if index >= 0:
        pass_list.pop(index)


def parse_json_result(name, value):
  test_result = TestResult(name)
  if value['actual'] == 'SKIP':
    return test_result

  actual = value['actual'].split(' ')
  test_result.result = 'PASS' in actual
  test_result.retry = len(actual) - 1
  if test_result.result:
    test_result.is_flaky = test_result.retry > 0
  else:
    test_result.is_crash = 'CRASH' in actual
    test_result.is_timeout = 'TIMEOUT' in actual

  expected = value['expected'].split(' ')
  if actual == expected:
    test_result.is_expected = True
  elif test_result.result and 'PASS' in expected:
    test_result.is_expected = True
  elif (not test_result.result and
        match_any(['FAIL', 'CRASH', 'TIMEOUT'], lambda x: x in expected)):
    test_result.is_expected = True
  else:
    test_result.is_expected = False

  if 'time' in value:
    test_result.duration = value['time']
  elif 'times' in value:
    test_result.duration = 0
    for time in value['times']:
      test_result.duration += time
  return test_result


def parse_json_result_dict(result_dict, test_suite, prefix=''):
  for key, value in result_dict.items():
    if 'actual' in value and 'expected' in value:
      test_suite.AddResult(parse_json_result(prefix + key, value))
    else:
      parse_json_result_dict(value, test_suite, prefix + key + '/')


def parse_json_result_file(result_file):
  result_name, _ = path.splitext(path.basename(result_file))
  test_suite = TestSuite(result_name)
  parse_json_result_dict(read_json(result_file)['tests'], test_suite)
  return test_suite


def parse_unittest_result_file(result_file):
  result_name, _ = path.splitext(path.basename(result_file))
  test_suite = TestSuite(result_name)
  error_result = ''
  for line in read_line(result_file):
    if error_result:
      match = re_match(PATTERN_UNITTEST_ERROR, line)
      if match:
        result = TestResult(match.group(1))
        if error_result != 'skip':
          result.result = False
          result.is_timeout = error_result == 'timeout'
          result.is_crash = error_result == 'crash'
          result.is_expected = error_result == 'fail_expected'
        test_suite.RemovePass(result.name)
        test_suite.AddResult(result)
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
    elif re_match(PATTERN_UNITTEST_RESULT_FAIL_EXPECTED, line):
      error_result = 'fail_expected'
    elif re_match(PATTERN_UNITTEST_RESULT_CRASH, line):
      error_result = 'crash'
    elif re_match(PATTERN_UNITTEST_RESULT_TIMEOUT, line):
      error_result = 'timeout'
    elif re_match(PATTERN_UNITTEST_RESULT_SKIP, line):
      error_result = 'skip'
  return test_suite


def parse_gtest_result_file(result_file):
  result_name, _ = path.splitext(path.basename(result_file))
  test_suite = TestSuite(result_name)
  for line in read_line(result_file):
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
  result_name, _ = path.splitext(path.basename(result_file))
  for line in read_line(result_file):
    match = re_match(PATTERN_AVERAGE_FPS, line)
    if match:
      result = PerfResult(result_name)
      result.average_fps = int(match.group(1))
      return result


def generate_test_report(test_suites):
  max_name_len = 0
  for test_suite in test_suites:
    max_name_len = max(max_name_len, len(test_suite.name))
  name_format = '{:<%d}' % (max_name_len+2)
  report = 'Test Result:\n'
  for test_suite in test_suites:
    report += name_format.format(test_suite.name)
    report += '{:<14}'.format('[Pass:%d]' % len(test_suite.actual_pass))
    report += '{:<11}'.format('[Fail:%d]' % len(test_suite.actual_fail))
    report += '{:<11}'.format('[Skip:%d]' % len(test_suite.skip))
    report += '{:<17}'.format('[Flaky Pass:%d]' % len(test_suite.flaky_pass))
    report += '{:<15}'.format('[New Pass:%d]' % len(test_suite.unexpected_pass))
    report += '[New Fail:%d]\n' % len(test_suite.unexpected_fail)

  if match_any(test_suites, lambda x: x.unexpected_fail):
    report += '\nNew Fail:\n'
    for test_suite in test_suites:
      for test_result in test_suite.unexpected_fail:
        report += '%s    %s\n' % (test_result.suite_name, test_result.name)

  if match_any(test_suites, lambda x: x.unexpected_pass and not x.name.startswith('webgpu')):
    report += '\nNew Pass:\n'
    for test_suite in test_suites:
      if not test_suite.name.startswith('webgpu'):
        for test_result in test_suite.unexpected_pass:
          report += '%s    %s\n' % (test_result.suite_name, test_result.name)
  
  if match_any(test_suites, lambda x: x.flaky_pass):
    report += '\nFlaky Pass:\n'
    for test_suite in test_suites:
      for test_result in test_suite.flaky_pass:
        report += '%s    %s\n' % (test_result.suite_name, test_result.name)
  return report


def main():
  args = parse_arguments()

  def find_result_file(module):
    result_ext = 'json' if module in ['content', 'blink'] else 'log'
    for file_path in list_file(args.result_dir):
      file_name = path.basename(file_path)
      if (file_name.endswith(result_ext) and 
          match_any(args.module_to_name[module], lambda x: file_name.startswith(x))):
        yield file_path

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
    for module in args.result_type:
      for result_file in find_result_file(module):
        if module in ['content', 'blink']:
          test_suite = parse_json_result_file(result_file)
        elif module in ['gpu', 'angle']:
          test_suite = parse_unittest_result_file(result_file)
        elif module in ['dawn']:
          test_suite = parse_gtest_result_file(result_file)
        if test_suite:
          name, ext = path.splitext(test_suite.name)
          while ext:
            name, ext = path.splitext(name)
          merged_result.setdefault(name, TestSuite(name))
          merged_result[name] += test_suite

    if merged_result:
      sorted_suites = []
      for name in args.result_order:
        if name in merged_result:
          sorted_suites.append(merged_result.pop(name))
      assert not merged_result
      print(generate_test_report(sorted_suites), end='')


if __name__ == '__main__':
  sys.exit(main())
