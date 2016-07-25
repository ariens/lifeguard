from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker
from sqlalchemy.ext.declarative import declarative_base

from app import app

engine = create_engine(app.config['SQLALCHEMY_DATABASE_URI'], pool_recycle=3600)
session_factory = sessionmaker(bind=engine)
Session = scoped_session(session_factory)

def init_db():
    from app.views.auth.models import User
    from app.views.cluster.models import Cluster
    from app.views.task.models import Task
    from app.views.vpool.models import VirtualMachinePool
    from app.views.vpool.models import PoolMembership
    from app.views.zone.models import Zone
    Base.metadata.create_all(bind=engine)

Base = declarative_base()
Base.query = Session.query_property()
