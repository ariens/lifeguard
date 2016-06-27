from flask_wtf import Form
from wtforms import TextAreaField, StringField
from wtforms.validators import InputRequired
from app.views.cluster.models import Cluster
from app.views.template.models import VarParser, ObjectLoader
from app.database import Base, Session
from app.one import OneProxy
from app.one import INCLUDING_DONE
from  jinja2 import Environment
from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime
from sqlalchemy.orm import relationship, backref
import re
from enum import Enum


class ExpandException(Exception):
  pass


class VirtualMachinePool(Base):
  __tablename__ = 'virtual_machine_pool'
  id = Column(Integer, primary_key=True)
  name = Column(String(100), unique=True, nullable=False)
  cluster_id = Column(Integer, nullable=False)
  zone_number = Column(Integer, nullable=False)
  template = Column(Text(), default='{% extends cluster.template %}')
  vars = Column(Text(), default='')
  cardinality = Column(Integer, nullable=False, default=1)
  cluster = relationship(
    'Cluster',
    primaryjoin="and_(VirtualMachinePool.cluster_id == Cluster.id, VirtualMachinePool.zone_number == Cluster.zone_number)",
    foreign_keys=[cluster_id, zone_number])

  def __init__(self, id=None, name=None, zone_number=None, cluster_id=None, cardinality=None):
    self.id = id
    self.name = name
    self.cluster_id = cluster_id
    self.zone_number = zone_number
    self.cardinality = cardinality

  def __str__(self):
    return 'VirtualMachinePool: id={}, name={}, cluster_id={}, cluster={}, ' \
           'zone_number={}, template={}, vars={}, cardinality={}'.format(
      self.id,
      self.name,
      self.cluster_id,
      self.cluster,
      self.zone_number,
      self.template,
      self.vars,
      self.cardinality)

  def __repr__(self):
    self.__str__()

  def get_memberships(self, fetch_vms=True):
    """
    Get the PoolMembership objects that are associated with the pool
    :param fetch_vms: If true, the vm attribute will be populated (incurs potentially
    timely call to the ONE api
    :return:
    """
    memberships =  PoolMembership.query.filter_by(pool=self).all()
    if fetch_vms:
      one_proxy = OneProxy(self.cluster.zone.xmlrpc_uri, self.cluster.zone.session_string, verify_certs=False)
      vms_dict = {vm.id: vm for vm in one_proxy.get_vms(INCLUDING_DONE)}
      for m in memberships:
        m.vm = vms_dict[m.vm_id]
    return memberships

  def name_for_number(self, number):
    pattern = re.compile("^([^\.]+)\.(.*)$")
    match = pattern.match(self.name)
    if match is None:
      raise Exception("Failed to parse pool name for hostname of number: {}".format(number))
    return '{}{}.{}'.format(match.group(1), number, match.group(2))

  def num_outdated_vms(self, members):
    num = 0
    for m in members:
      if not m.is_current():
        num += 1
    return num

  def num_legacy_vms(self, members):
    num = 0
    for m in members:
      if m.is_legacy():
        num += 1
    return num

  def num_done_vms(self, members):
    num = 0
    for m in members:
      if m.is_done():
        num += 1
    return num

  def get_tickets(self):
    return PoolTicket.query.filter_by(pool=self).all()

  def get_cluster(self):
    return Cluster.query.filter_by(zone_number=self.zone_number, id=self.cluster_id).first()

  def get_members_to_shrink(self, members, confirm_vm_ids=None):
    if len(members) <= self.cardinality:
      return None
    shrink = []
    num_2_member = {m.parse_number(): m for m in members}
    sorted_numbers = sorted(num_2_member)
    while len(sorted_numbers) > self.cardinality:
      candidate = num_2_member[sorted_numbers.pop()]
      print('confirm list: {}'.format(confirm_vm_ids))
      if confirm_vm_ids is not None and candidate.vm.id not in confirm_vm_ids:
        raise Exception("member (name={}, vm_id={}) not in confirm list".format(
          candidate.vm.name, candidate.vm.id))
      shrink.append(candidate)
    return shrink

  def get_expansion_names(self, members, form_expansion_names):
    """
    Checks if there are hosts that are required for expansion and if so generates their new
    names by creating lowest missing values of 'N' in poolname<N>.sub.domain.tld.
    :return:
    expansion_names: array of new hostnames that need to be instantiated
    """
    if (len(members) >= self.cardinality):
      return None
    members_by_num = {m.parse_number(): m for m in members}
    expansion_names = []
    for number in range(1, self.cardinality + 1):
      if number not in members_by_num.keys():
        expansion_name = self.name_for_number(number)
        if form_expansion_names is not None and expansion_name not in form_expansion_names:
          raise Exception("Hostname for expansion not previously confirmed in form submission, "
                          "review and confirm again: {}".format(expansion_name))
        expansion_names.append(expansion_name)
    if form_expansion_names is not None:
      for form_name in form_expansion_names:
        if form_name not in expansion_names:
          raise Exception("Previously confirmed hostname for expansion no longer determined required, "
                          "review and confirm again: {}".format(form_name))
    return expansion_names

  @staticmethod
  def get_all(cluster):
    return Session().query(VirtualMachinePool).filter_by(cluster=cluster)

  def get_peer_pools(self):
    return Session().query(VirtualMachinePool).filter_by(cluster=self.cluster)


class PoolMembership(Base):
  __tablename__ = 'pool_membership'
  vm_id = Column(Integer, primary_key=True)
  pool_id = Column(Integer, ForeignKey('virtual_machine_pool.id'), primary_key=True)
  pool = relationship('VirtualMachinePool', backref=backref('virtual_machine_pool', lazy='dynamic'))
  date_added = Column(DateTime, nullable=False)
  template = Column(Text(), default='{% extends cluster.template %}')

  def __init__(self, pool_id=None, pool=None, vm_id=None, date_added=None, vm=None, template=None):
    self.pool_id = pool_id
    self.pool = pool
    self.vm_id = vm_id
    self.date_added = date_added
    self.vm = vm
    self.template = template

  def remove_cmd(self):
    if self.is_done():
      return 'delete'
    else:
      return "shutdown"

  def is_done(self):
    if self.vm.state_id >= 4:
      return True

  def is_current(self):
    env = Environment(loader=ObjectLoader())
    vars =  VarParser.parse_kv_strings_to_dict(
      self.pool.cluster.zone.vars,
      self.pool.cluster.vars,
      self.pool.vars,
      'hostname={}'.format(self.vm.name))
    return self.template == env.from_string(self.pool.template).render(pool=self.pool, vars=vars)

  @staticmethod
  def get_all(zone):
    return Session().query(PoolMembership).join(
      PoolMembership.pool, aliased=True).filter_by(zone=zone)

  def parse_number(self):
    if self.vm is None:
      raise Exception("cannot determine number from virtual machine name when vm is None")
    num_pattern = re.compile("^[\dA-Za-z]+\D(\d+)\.")
    match = num_pattern.match(self.vm.name)
    if match is not None:
      return int(match.group(1))
    else:
      raise Exception("cannot determine number from virtual machine name {}".format(self.vm.name))

  def __str__(self):
    return 'PoolMembership: pool_id={}, pool={}, vm_id={}, vm={}, date_added={}'.format(
      self.pool_id,
      self.pool,
      self.vm_id,
      self.vm,
      self.date_added)

  def __repr__(self):
    self.__str__()


class PoolTicketActions(Enum):
  expand = 0
  shrink = 1
  update = 2


class PoolTicket(Base):
  __tablename__ = 'pool_ticket'
  pool = relationship('VirtualMachinePool', backref=backref('pool_tickets'), cascade='all')
  pool_id = Column(Integer, ForeignKey('virtual_machine_pool.id'), primary_key=True)
  ticket_key = Column(String(17), primary_key=True)
  task = relationship('Task', backref=backref('pool_tickets'), cascade='all')
  task_id = Column(Integer, ForeignKey('task.id'))
  action_id = Column(Integer, nullable=False)

  def __init__(self, pool=None, pool_id=None, ticket_key=None, task=None, task_id=None, action_id=None):
    self.pool_id = pool_id
    self.pool = pool
    self.ticket_key = ticket_key
    self.task = task
    self.task_id = task_id
    self.action_id = action_id

  def action_name(self):
    return PoolTicketActions(self.action_id).name

class PoolEditForm(Form):
  name = StringField('Name', [InputRequired()])
  cardinality = StringField('Cardinality', [InputRequired()])
  template = TextAreaField('Zone Template')
  vars = TextAreaField('Zone Variables')


class GenerateTemplateForm(Form):
  pass
