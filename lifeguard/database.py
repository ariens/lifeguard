from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker
from sqlalchemy.ext.declarative import declarative_base

from lifeguard import app

engine = create_engine(app.config['SQLALCHEMY_DATABASE_URI'], pool_recycle=3600, pool_size=30, max_overflow=0)
session_factory = sessionmaker(bind=engine)
Session = scoped_session(session_factory)

def init_db():
    from lifeguard.views.auth.models import User
    from lifeguard.views.cluster.models import Cluster
    from lifeguard.views.task.models import Task
    from lifeguard.views.vpool.models import VirtualMachinePool
    from lifeguard.views.vpool.models import PoolMembership
    from lifeguard.views.zone.models import Zone
    Base.metadata.create_all(bind=engine)

Base = declarative_base()
Base.query = Session.query_property()