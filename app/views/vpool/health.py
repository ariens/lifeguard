import subprocess
from datetime import datetime
from app.database import Session
from app import app

class Diagnostic:

  def __init__(self,
               user=None,
               host=None,
               ssh_identity_file=None,
               cmd=None,
               stdout=None,
               stderr=None,
               exitcode=None,
               start_date=None,
               end_date=None,
               timeout=5,
               interupted=False):
    self.user = user
    self.host = host
    self.ssh_identity_file = ssh_identity_file
    self.cmd = cmd
    self.timeout = timeout
    self.stdout = stdout
    self.stderr = stderr
    self.exitcode = exitcode
    self.interupted = interupted
    self.start_date = start_date
    self.end_date = end_date

  def run(self):
    self.start_date = datetime.utcnow()
    cmd = subprocess.Popen(['ssh',
      '-i', self.ssh_identity_file,
      '-o', 'StrictHostKeyChecking=no',
      '-o', 'UserKnownHostsFile=/dev/null',
      '{}@{}'.format(self.user, self.host),
      self.cmd],
      stdout=subprocess.DEVNULL, stdin=subprocess.PIPE, universal_newlines=True)
    try:
      self.stdout, self.stderr = cmd.communicate(timeout=self.timeout)
    except subprocess.TimeoutExpired:
      cmd.kill()
      self.stdout, self.stderr = cmd.communicate()
      self.interupted = True
    finally:
      self.end_date = datetime.utcnow()
    self.exitcode = cmd.returncode

