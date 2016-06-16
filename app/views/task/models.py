from app import app
from app.database import Base
from enum import Enum
from threading import Thread
import threading
from datetime import datetime
from app.jira_api import JiraApi
import traceback, sys
from sqlalchemy import Column, Integer, String, DateTime, create_engine
from sqlalchemy.orm import scoped_session, sessionmaker


class TaskResult(Enum):
  success = 0
  fail = 1


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
  status = Column(Integer)

  def __init__(self,
               id=None,
               name=None,
               username=None,
               description=None,
               start_time=None,
               end_time=None,
               ident=None,
               status=None,
               defect_ticket=None):
    self.id = id
    self.name = name
    self.username = username
    self.description = description
    self.start_time = start_time
    self.end_time = end_time
    self.ident = ident
    self.status= status
    self.defect_ticket = defect_ticket


class TaskThread(Thread):

  def __init__(self, task, run_function, **kwargs):
    if None in [task, run_function]:
      raise Exception("Required parameter(s) is None: task={}, run_function={}".format(task, run_function))
    self.task = task
    self.run_function = run_function
    engine = create_engine(app.config['SQLALCHEMY_DATABASE_URI'])
    Session = scoped_session(sessionmaker(autocommit=False,
                                         autoflush=False,
                                         bind=engine))
    self.db_session = Session()
    self.db_session.merge(self.task)
    super().__init__(target=self.run_task, kwargs=kwargs)

  def run_task(self, **kwargs):
    self.task.start_time = datetime.utcnow()
    self.task.ident = threading.get_ident()
    self.db_session.merge(self.task)
    try:
      self.run_function(**kwargs)
      self.task.status = TaskResult.success.value
    except Exception as e:
      traceback.print_exc(file=sys.stdout)
      self.task.status = TaskResult.fail.value
      jira = JiraApi()
      jira.connect()
      self.task.defect_ticket = jira.defect_for_exception("Background Task Error: {}".format(self.task.name), e).key
    self.task.end_time = datetime.utcnow()
    self.db_session.merge(self.task)
    self.db_session.commit()