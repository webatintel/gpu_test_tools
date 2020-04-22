#!/usr/bin/env python

import json
import os
import shutil
import zipfile

from os import path

def mkdir(dir):
  try:
    os.makedirs(dir)
  except OSError:
    pass

def chmod(path, mode):
  os.chmod(path, int(str(mode), 8))

def copy(src, dest):
  if path.isfile(src):
    shutil.copy(src, dest)
  elif path.isdir(src):
    if path.exists(dest):
      dest = path.join(dest, path.basename(src))
    shutil.copytree(src, dest)

def remove(src):
  if path.isfile(src):
    os.remove(src)
  elif path.isdir(src):
    shutil.rmtree(src)

def zip(zip_file, src_dir):
  with zipfile.ZipFile(zip_file, 'w', zipfile.ZIP_DEFLATED, allowZip64=True) as f:
    for root, _, files in os.walk(src_dir):
      for src_file in files:
        src_file = path.join(root, src_file)
        f.write(src_file, path.relpath(src_file, src_dir))

def unzip(zip_file, dest_dir):
  with zipfile.ZipFile(zip_file, 'r') as f:
    f.extractall(dest_dir)

def read_json(json_file):
  try:
    with open(json_file, 'r') as f:
      return json.load(f)
  except Exception:
    return {}

def write_json(json_file, content_dict):
  if content_dict:
    with open(json_file, 'w') as f:
      json.dump(content_dict, f)

def read_line(file_name):
  with open(file_name, 'r') as f:
    while True:
      line = f.readline()
      if not line:
        break
      yield line

def read_file(file_name):
  try:
    with open(file_name, 'r') as f:
      return f.read()
  except Exception:
    return ''

def write_file(file_name, content):
  if content:
    with open(file_name, 'w') as f:
      f.write(content)

def list_file(dir):
  for item in os.listdir(dir):
    file_name = path.join(dir, item)
    if path.isfile(file_name):
      yield file_name
