from flask_wtf import Form
from sqlalchemy.schema import ForeignKeyConstraint
from wtforms import StringField
from wtforms.validators import InputRequired
from lifeguard.database import Base
from sqlalchemy import Column, Integer, String, ForeignKey, Text
from sqlalchemy.orm import relationship, backref

class Cluster(Base):
  __tablename__ = 'cluster'
  id = Column(Integer, primary_key=True)
  zone = relationship('Zone', backref=backref('zone_ref'))
  zone_number = Column(Integer, ForeignKey('zone.number'), primary_key=True)
  name = Column(String(100), unique=True, nullable=False)
  template = Column(Text())
  vars = Column(Text())
  ForeignKeyConstraint('zone_number', 'zone.number')

  def __init__(self, id=id, zone_number=None, zone=None, name=None, template=None, vars=None):
    self.id = id
    self.zone = zone
    self.zone_number = zone_number
    self.name = name
    self.template = template
    self.vars=vars

  def __str__(self):
    return 'Cluster: id={}, name={}, zone_number={}, zone={}'.format(
      self.id, self.name, self.zone_number, self.zone)

  def __repr__(self):
    self.__str__()

class ClusterTemplateForm(Form):
  pass

class GenerateTemplateForm(Form):
  pass


class CreateVmForm(Form):
  hostname = StringField('Hostname', [InputRequired()], default='<somename>.log82.altus.bblabs')
  cpu = StringField('CPU', [InputRequired()], default='.25')
  vcpu = StringField('VCPU', [InputRequired()], default='1')
  memory_megabytes = StringField('Memory (MB)', [InputRequired()], default='2048')