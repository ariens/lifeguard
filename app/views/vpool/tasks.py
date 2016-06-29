import io
from app.database import Session
import random
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, scoped_session
from app import app, jira
from app.views.task.models import Task
from app.views.vpool.models import VirtualMachinePool
from app.jira_api import JiraApi
from jinja2 import Environment
from app.views.template.models import VarParser, ObjectLoader
from app.views.vpool.models import PoolTicket, PoolTicketActions


def plan_expansion(self, pool, expansion_names):
  """
  This get's launched as a background task because the Jira API calls take too long
  :return:
  """
  task = crq = None
  try:
    pool = Session.merge(pool)
    start, end = jira.next_immediate_window_dates()
    logging = jira.instance.issue('SVC-1020')
    crq = jira.instance.create_issue(
      project=app.config['JIRA_CRQ_PROJECT'],
      issuetype={'name': 'Change Request'},
      assignee={'name': app.config['JIRA_USERNAME']},
      summary='[IMPLEMENT] {}'.format(self.task.name),
      description=self.task.description,
      customfield_14530=start,
      customfield_14531=end,
      customfield_19031={'value': 'Maintenance'},
      customfield_15152=[{'value': 'Global'}],
      customfield_19430={'value': 'No conflict with any restrictions'},
      customfield_14135={'value': 'IPG', 'child': {'value': 'IPG Big Data'}},
      customfield_17679="Pool expansion required")
    self.log_msg("Created change request: {}".format(crq.key))
    jira.instance.transition_issue(crq, app.config['JIRA_TRANSITION_CRQ_PLANNING'])
    self.log_msg("Transitioned {} to planning".format(crq.key))
    jira.instance.create_issue_link('Relate', crq, logging)
    self.log_msg("Related {} to LOGGING service {}".format(crq.key, logging.key))
    task = jira.instance.create_issue(
      issuetype={'name': 'MOP Task'},
      assignee={'name': app.config['JIRA_USERNAME']},
      project=app.config['JIRA_CRQ_PROJECT'],
      description="Instanitate the attached templates in the zone associated "
                  "to the pool identified in the filename <pool_id>.<hostname>",
      summary='[IMPLEMENTATION TASK] {}'.format(self.task.name),
      parent={'key': crq.key},
      customfield_14135={'value': 'IPG', 'child': {'value': 'IPG Big Data'}},
      customfield_15150={'value': 'No'})
    self.log_msg("Created task: {}".format(task.key))
    jira.instance.transition_issue(task, app.config['JIRA_TRANSITION_TASK_PLANNING'])
    self.log_msg("Transitioned {} to planning".format(task.key))
    env = Environment(loader=ObjectLoader())
    for hostname in expansion_names:
      vars = VarParser.parse_kv_strings_to_dict(
        pool.cluster.zone.vars,
        pool.cluster.vars,
        pool.vars,
        'hostname={}'.format(hostname))
      vm_template = env.from_string(pool.template).render(pool=pool, vars=vars)
      attachment_content = io.StringIO(vm_template)
      jira.instance.add_attachment(
        issue=task,
        filename='{}.{}.template'.format(poo.id, hostname),
        attachment=attachment_content)
      self.log_msg("Attached template for {} to task {}".format(hostname, task.key))
    jira.instance.transition_issue(task, app.config['JIRA_TRANSITION_TASK_WRITTEN'])
    self.log_msg("Transitioned task {} to written".format(task.key))
    jira.approver_instance.transition_issue(task, app.config['JIRA_TRANSITION_TASK_APPROVED'])
    self.log_msg("Approved task {}".format(task.key))
    jira.instance.transition_issue(crq, app.config['JIRA_TRANSITION_CRQ_PLANNED_CHANGE'])
    self.log_msg("Transitioned task {} to approved".format(task.key))
    jira.approver_instance.transition_issue(crq, app.config['JIRA_TRANSITION_CRQ_APPROVED'])
    self.log_msg("Transitioned change request {} to approved".format(crq.key))
    self.log_msg("Task ID {}".format(self.task.id))
    db_ticket = PoolTicket(
      pool=pool,
      action_id=PoolTicketActions.expand.value,
      ticket_key=crq.key,
      task=self.task)
    Session.add(db_ticket)
    Session.commit()
    Session.remove()
  except Exception as e:
    if task is not None:
      jira.instance.transition_issue(task, app.config['JIRA_TRANSITION_TASK_CANCELLED'])
      self.log_err("Transitioned task {} to cancelled".format(task.key))
      transitions = jira.instance.transitions(task)
      self.log_err("After cancelling task the available transitions are: {}".format([(t['id'], t['name']) for t in transitions]))
      jira.instance.transition_issue(task, app.config['JIRA_TRANSITION_TASK_CANCELLED'])
      self.log_err("Transition task {} to cancelled (again)".format(task.key))
      transitions = jira.instance.transitions(task)
      self.log_err("After second cancellation of task the available transitions are: {}".format([(t['id'], t['name']) for t in transitions]))
    if crq is not None:
      jira.instance.transition_issue(crq, app.config['JIRA_TRANSITION_CRQ_CANCELLED'])
      self.log_err("Transitioned change request {} to cancelled".format(crq.key))
    raise e

def plan_update(self, pool, id_to_template):
  """
  This get's launched as a background task because the Jira API calls take too long
  :return:
  """
  task = crq = None
  try:
    pool = Session.merge(pool)
    start, end = jira.next_immediate_window_dates()
    logging = jira.instance.issue('SVC-1020')
    crq = jira.instance.create_issue(
      project=app.config['JIRA_CRQ_PROJECT'],
      issuetype={'name': 'Change Request'},
      assignee={'name': app.config['JIRA_USERNAME']},
      summary="[IMPLEMENT] {}".format(self.task.name),
      description=self.task.description,
      customfield_14530=start,
      customfield_14531=end,
      customfield_19031={'value': 'Maintenance'},
      customfield_15152=[{'value': 'Global'}],
      customfield_19430={'value': 'No conflict with any restrictions'},
      customfield_14135={'value': 'IPG', 'child': {'value': 'IPG Big Data'}},
      customfield_17679="Pool update required")
    self.log_msg("Created change request: {}".format(crq.key))
    jira.instance.transition_issue(crq, app.config['JIRA_TRANSITION_CRQ_PLANNING'])
    self.log_msg("Transitioned {} to planning".format(crq.key))
    jira.instance.create_issue_link('Relate', crq, logging)
    self.log_msg("Related {} to LOGGING service {}".format(crq.key, logging.key))
    task = jira.instance.create_issue(
      issuetype={'name': 'MOP Task'},
      assignee={'name': app.config['JIRA_USERNAME']},
      project=app.config['JIRA_CRQ_PROJECT'],
      summary='[IMPLEMENTATION TASK] {}'.format(self.task.name),
      parent={'key': crq.key},
      customfield_14135={'value': 'IPG', 'child': {'value': 'IPG Big Data'}},
      customfield_15150={'value': 'No'})
    self.log_msg("Created task: {}".format(task.key))
    jira.instance.transition_issue(task, app.config['JIRA_TRANSITION_TASK_PLANNING'])
    self.log_msg("Transitioned {} to planning".format(task.key))
    env = Environment(loader=ObjectLoader())
    for vm_id, vm_template in id_to_template.items():
      filename = '{}.{}.template'.format(pool.id, vm_id)
      attachment_content = io.StringIO(vm_template)
      jira.instance.add_attachment(
        issue=task,
        filename=filename,
        attachment=attachment_content)
      self.log_msg("Attached template for {} to task {}".format(filename, task.key))
    jira.instance.transition_issue(task, app.config['JIRA_TRANSITION_TASK_WRITTEN'])
    self.log_msg("Transitioned task {} to written".format(task.key))
    jira.approver_instance.transition_issue(task, app.config['JIRA_TRANSITION_TASK_APPROVED'])
    self.log_msg("Approved task {}".format(task.key))
    jira.instance.transition_issue(crq, app.config['JIRA_TRANSITION_CRQ_PLANNED_CHANGE'])
    self.log_msg("Transitioned task {} to approved".format(task.key))
    jira.approver_instance.transition_issue(crq, app.config['JIRA_TRANSITION_CRQ_APPROVED'])
    self.log_msg("Transitioned change request {} to approved".format(crq.key))
    self.log_msg("Task ID {}".format(self.task.id))
    db_ticket = PoolTicket(
      pool=pool,
      action_id=PoolTicketActions.update.value,
      ticket_key=crq.key,
      task=self.task)
    Session.add(db_ticket)
    Session.commit()
    Session.remove()
  except Exception as e:
    if task is not None:
      jira.instance.transition_issue(task, app.config['JIRA_TRANSITION_TASK_CANCELLED'])
      self.log_err("Transitioned task {} to cancelled".format(task.key))
      transitions = jira.instance.transitions(task)
      self.log_err("After cancelling task the available transitions are: {}".format([(t['id'], t['name']) for t in transitions]))
      jira.instance.transition_issue(task, app.config['JIRA_TRANSITION_TASK_CANCELLED'])
      self.log_err("Transition task {} to cancelled (again)".format(task.key))
      transitions = jira.instance.transitions(task)
      self.log_err("After second cancellation of task the available transitions are: {}".format([(t['id'], t['name']) for t in transitions]))
    if crq is not None:
      jira.instance.transition_issue(crq, app.config['JIRA_TRANSITION_CRQ_CANCELLED'])
      self.log_err("Transitioned change request {} to cancelled".format(crq.key))
    raise e