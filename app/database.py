from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker
from sqlalchemy.ext.declarative import declarative_base

from app import app

engine = create_engine(app.config['SQLALCHEMY_DATABASE_URI'])
db_session = scoped_session(sessionmaker(autocommit=False,
                                         autoflush=False,
                                         bind=engine))
Base = declarative_base()
Base.query = db_session.query_property()

def init_db():
    from app.views.auth.models import User
    from app.views.cluster.models import Cluster
    from app.views.task.models import Task
    from app.views.vpool.models import VirtualMachinePool
    from app.views.vpool.models import PoolMembership
    from app.views.zone.models import Zone
    Base.metadata.create_all(bind=engine)
