import email.utils
import glob
import json
import os
import shutil
import smtplib
import stat
import sys
import zipfile

from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from os import path

REPOSITORY_DIR = path.dirname(path.dirname(path.abspath(__file__)))

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
  else:
    print(src + ' not exists')
    assert False

def remove(pathname):
  def onerror(func, path, exc):
    if not os.access(path, os.W_OK):
      os.chmod(path, stat.S_IWUSR)
      func(path)
    else:
      raise

  if pathname.find('*') >= 0:
    for item in glob.glob(pathname):
      remove(item)
  elif not path.exists(pathname):
    pass
  elif path.isfile(pathname):
    os.remove(pathname)
  elif path.isdir(pathname):
    shutil.rmtree(pathname, onerror=onerror)
  else:
    assert False

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
  except ValueError:
    return {}

def load_tryjob_config():
  return read_json(path.join(REPOSITORY_DIR, 'tryjob.json'))

def list_file(dir_path):
  for item in os.listdir(dir_path):
    item = path.join(dir_path, item)
    if path.isfile(item):
      yield item

def read_file(file_path):
  with open(file_path, 'r') as f:
    return f.read()

def write_file(file_path, content):
  with open(file_path, 'w') as f:
    f.write(content)

def read_line(file_path):
  with open(file_path, 'r') as f:
    line = f.readline()
    while line:
      yield line.rstrip()
      line = f.readline()

def write_line(file_path, lines):
  with open(file_path, 'w') as f:
    for line in lines:
      f.write(line + '\n')

def send_email(receiver, subject, body='', attach=[]):
  receiver = receiver if isinstance(receiver, list) else [receiver]
  attach = attach if isinstance(attach, list) else [attach]
  config = load_tryjob_config()

  message = MIMEMultipart()
  message['From'] = config['email']['sender']
  message['To'] =  email.utils.COMMASPACE.join(receiver)
  message['Subject'] = subject
  message.attach(MIMEText(body, 'plain'))

  for file_path in attach:
    attachment = MIMEBase('application', "octet-stream")
    attachment.set_payload(read_file(file_path))
    encoders.encode_base64(attachment)
    attachment.add_header('Content-Disposition', 'attachment; filename="%s"'
                          % path.basename(file_path))
    message.attach(attachment)

  try:
    smtp = smtplib.SMTP(config['email']['smtp_server'])
    smtp.sendmail(config['email']['sender'], receiver, message.as_string())
    smtp.quit()
  except Exception as e:
    print(e)
