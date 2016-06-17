from app import app
from app.database import Base
from enum import Enum
from threading import Thread
import threading
from datetime import datetime
from app.jira_api import JiraApi
import traceback, sys
from sqlalchemy import Column, Integer, String, DateTime, Text, create_engine
from sqlalchemy.orm import scoped_session, sessionmaker


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
    if self.status == TaskStatus.pending.value:
      return None
    end = self.end_time if self.end_time is not None else datetime.utcnow()
    m, s = divmod((end - self.start_time).total_seconds(), 60)
    h, m = divmod(m, 60)
    if h != 0.0:
      return '{} hours, {} mins'.format(h, m)
    if m != 0.0:
      return '{} mins, {} secs'.format(h, s)
    return '{} secs'.format(s)

class TaskThread(Thread):
  fmt = "%Y-%m-%dT%H:%M:%S.%f%z"

  def __init__(self, task, run_function, log=None, **kwargs):
    if None in [task, run_function]:
      raise Exception("Required parameter(s) is None: task={}, run_function={}".format(task, run_function))
    self.log = log
    self.task = task
    self.run_function = run_function
    engine = create_engine(app.config['SQLALCHEMY_DATABASE_URI'])
    Session = scoped_session(sessionmaker(autocommit=False,
                                         autoflush=False,
                                         bind=engine))
    self.db_session = Session()
    self.db_session.merge(self.task)
    super().__init__(target=self.run_task, kwargs=kwargs)

  def log_msg(self, raw_msg):
    d = datetime.utcnow().strftime(TaskThread.fmt)
    msg = "{}: {}".format(d, raw_msg)
    if self.log is not None:
      self.log += "\n"
      self.log += msg
    else:
      self.log = msg

  def run_task(self, **kwargs):
    self.task.start_time = datetime.utcnow()
    self.task.ident = threading.get_ident()
    self.task.status = TaskStatus.running.value
    self.db_session.merge(self.task)
    self.db_session.commit()
    try:
      self.run_function(self, **kwargs)
      self.task.log = self.log
      self.task.end_time = datetime.utcnow()
      self.task.status = TaskStatus.finished.value
      self.task.result = TaskResult.success.value
      self.db_session.merge(self.task)
      self.db_session.commit()
    except Exception as e:
      self.task.log = self.log
      self.task.tb = traceback.format_exc()
      self.task.end_time = datetime.utcnow()
      self.task.status = TaskStatus.finished.value
      self.task.result = TaskResult.fail.value
      print("task result: {}".format(self.task.result))
      # Merge/commit in case the Jira defect ticket fails
      self.db_session.merge(self.task)
      print("task result: {}".format(self.task.result))
      self.db_session.commit()
      jira = JiraApi()
      jira.connect()
      self.task.defect_ticket = jira.defect_for_exception(
        "Background Task Error: {}".format(self.task.name), e, username=self.task.username).key
      self.db_session.merge(self.task)
      self.db_session.commit()
      print("task result: {}".format(self.task.result))

