from app import app, jira
from app.database import Base, Session
from enum import Enum
from threading import Thread
import threading
from datetime import datetime
from app.jira_api import JiraApi
import traceback, sys
from sqlalchemy import Column, Integer, String, DateTime, Text
from flask import url_for


class TaskResult(Enum):
  success = 0
  fail = 1

class TaskStatus(Enum):
  pending = 0
  running = 1
  finished = 2

class Task(Base):
  __tablename__ = 'task'
  id = Column(Integer, primary_key=True)
  name = Column(String(100), nullable=False)
  username = Column(String(50), nullable=False)
  description = Column(String(1000), nullable=False)
  defect_ticket = Column(String(100), unique=True)
  thread_id = Column(Integer)
  start_time = Column(DateTime)
  end_time = Column(DateTime)
  status = Column(Integer, nullable=False, default=TaskStatus.pending.value)
  result = Column(Integer)
  tb = Column(Text)
  log = Column(Text)

  def __init__(self,
               id=None,
               name=None,
               username=None,
               description=None,
               start_time=None,
               end_time=None,
               ident=None,
               status=TaskStatus.pending.value,
               result=None,
               defect_ticket=None,
               tb=None,
               log=None):
    self.id = id
    self.name = name
    self.username = username
    self.description = description
    self.start_time = start_time
    self.end_time = end_time
    self.ident = ident
    self.status = status
    self.result = result
    self.defect_ticket = defect_ticket
    self.tb = tb
    self.log = log

  def defect_link(self):
    if self.defect_ticket is not None:
      return JiraApi.ticket_link(key=self.defect_ticket)

  def status_name(self):
    return TaskStatus(self.status).name

  def result_name(self):
    return TaskResult(self.result).name

  def is_finished(self):
    return self.status == TaskStatus.finished.value

  def get_elapsed(self):
    if self.status is None or self.status == TaskStatus.pending.value:
      return None
    end = self.end_time if self.end_time is not None else datetime.utcnow()
    m, s = divmod((end - self.start_time).total_seconds(), 60)
    h, m = divmod(m, 60)
    if h != 0.0:
      return '{} hours, {} mins'.format(h, m)
    if m != 0.0:
      return '{} mins, {} secs'.format(h, s)
    return '{} secs'.format(s)

  def link(self):
    return '<a href="{}">TASK-{}</a>'.format(url_for('task_bp.view', task_id=self.id), self.id)

class TaskThread(Thread):
  log_date_fmt = "%Y-%m-%dT%H:%M:%S.%f%z"
  def __init__(self, task_id, run_function, log=None, **kwargs):
    if None in [task_id, run_function]:
      raise Exception("Required parameter(s) is None: task={}, run_function={}".format(task_id, run_function))
    self.log = log
    self.task = None
    self.task_id = task_id
    self.run_function = run_function
    super().__init__(target=self.run_task, kwargs=kwargs)

  def log_msg(self, raw_msg):
    d = datetime.utcnow().strftime(TaskThread.log_date_fmt)
    msg = "{}: {}".format(d, raw_msg)
    if self.log is not None:
      self.log += "\n"
      self.log += msg
    else:
      self.log = msg

  def log_err(self, raw_msg):
    d = datetime.utcnow().strftime(TaskThread.log_date_fmt)
    msg = "{} ERROR: {}".format(d, raw_msg)
    if self.log is not None:
      self.log += "\n"
      self.log += msg
    else:
      self.log = msg

  def run_task(self, **kwargs):
    self.task = Task.query.get(self.task_id)
    self.task.start_time = datetime.utcnow()
    self.task.ident = threading.get_ident()
    self.task.status = TaskStatus.running.value
    Session.merge(self.task)
    Session.commit()
    try:
      self.run_function(self, **kwargs)
      self.task.log = self.log
      self.task.end_time = datetime.utcnow()
      self.task.status = TaskStatus.finished.value
      self.task.result = TaskResult.success.value
      Session.merge(self.task)
      Session.commit()
    except Exception as e:
      self.task.log = self.log
      self.task.tb = traceback.format_exc()
      self.task.end_time = datetime.utcnow()
      self.task.status = TaskStatus.finished.value
      self.task.result = TaskResult.fail.value
      Session.merge(self.task)
      Session.commit()
      self.task.defect_ticket = jira.defect_for_exception(
        "Background Task Error: {}".format(self.task.name), e, username=self.task.username).key
      Session.merge(self.task)
      Session.commit()
    Session.remove()