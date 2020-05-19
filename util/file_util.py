import json
import os
import shutil
import sys
import zipfile

from os import path

def mkdir(dir_path):
  try:
    os.makedirs(dir_path)
  except OSError:
    pass

def chmod(path, mode):
  os.chmod(path, int(str(mode), 8))

def copy(src, dest):
  if path.isfile(src):
    shutil.copy(src, dest)
  elif path.isdir(src):
    dest = path.join(dest, path.basename(src)) if path.exists(dest) else dest
    shutil.copytree(src, dest)

def remove(path):
  if path.isfile(path):
    os.remove(path)
  elif path.isdir(path):
    shutil.rmtree(path)

def zip(dest_file, src_dir):
  with zipfile.ZipFile(dest_file, 'w', zipfile.ZIP_DEFLATED, allowZip64=True) as zip_file:
    for root, _, files in os.walk(src_dir):
      for src_file in files:
        src_file = path.join(root, src_file)
        zip_file.write(src_file, path.relpath(src_file, src_dir))

def unzip(src_file, dest_dir):
  with zipfile.ZipFile(src_file, 'r') as zip_file:
    zip_file.extractall(dest_dir)

def read_json(file_path):
  try:
    with open(file_path, 'r') as json_file:
      return json.load(json_file)
  except (OSError, ValueError):
    return {}

def write_json(file_path, dict_content):
  if dict_content:
    with open(file_path, 'w') as json_file:
      json.dump(dict_content, json_file)

def read_line(file_path):
  with open(file_path, 'r') as f:
    line = f.readline()
    while line:
      yield line.rstrip()
      line = f.readline()

def write_line(file_path, lines):
  with open(file_path, 'w') as f:
    f.write('\n'.join(lines) + '\n')

def read_file(file_path):
  try:
    with open(file_path, 'r') as f:
      return f.read()
  except OSError:
    return ''

def write_file(file_path, content):
  with open(file_path, 'w') as f:
    f.write(content)

def list_file(dir_path):
  for item in os.listdir(dir_path):
    item = path.join(dir_path, item)
    if path.isfile(item):
      yield item

def get_executable(file_path):
  return file_path + ('.exe' if sys.platform == 'win32' else '')

def copy_executable(src_dir, dest_dir, files):
  for file_name in files:
    if sys.platform == 'win32':
      file_name += '.exe'
      copy(path.join(src_dir, file_name), dest_dir)
      file_name += '.pdb'
      if path.exists(file_name):
        copy(path.join(src_dir, file_name), dest_dir)
    else:
      copy(path.join(src_dir, file_name), dest_dir)
      chmod(path.join(dest_dir, file_name), 755)

def copy_library(src_dir, dest_dir, files):
  for file_name in files:
    if sys.platform == 'win32':
      file_name += '.dll'
      copy(path.join(src_dir, file_name), dest_dir)
      file_name += '.pdb'
      if path.exists(file_name):
        copy(path.join(src_dir, file_name), dest_dir)
    else:
      file_name += '.so'
      file_name = ('lib' if not file_name.startswith('lib') else '') + file_name
      copy(path.join(src_dir, file_name), dest_dir)

def copy_resource(src_dir, dest_dir, items):
  for item in items:
    target_dir = path.join(dest_dir, path.dirname(item))
    mkdir(target_dir)
    copy(path.join(src_dir, item), target_dir)
