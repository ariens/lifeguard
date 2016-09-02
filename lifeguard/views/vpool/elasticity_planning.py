import io
from lifeguard.database import Session
from lifeguard import app, jira
from jinja2 import Environment
from lifeguard.views.template.models import VarParser, ObjectLoader
from lifeguard.views.vpool.models import PoolTicket, PoolTicketActions
from math import ceil, floor

def plan_expansion(self, pool, expansion_names):
  task = crq = None
  try:
    pool = Session.merge(pool)
    start, end = jira.next_immediate_window_dates()
    logging = jira.instance.issue('SVC-1020')
    crq = jira.instance.create_issue(
      project=app.config['JIRA_CRQ_PROJECT'],
      issuetype={'name': 'Change Request'},
      assignee={'name': app.config['JIRA_USERNAME']},
      summary='[TEST IMPLEMENT] {}'.format(self.task.name),
      description=self.task.description,
      customfield_14530=start,
      customfield_14531=end,
      customfield_19031={'value': 'Maintenance'},
      customfield_15152=[{'value': 'Global'}],
      customfield_19430={'value': 'No conflict with any restrictions'},
      customfield_14135={'value': 'IPG', 'child': {'value': 'IPG Big Data'}},
      customfield_17679="Pool expansion required")
    self.log.msg("Created change request: {}".format(crq.key))
    jira.instance.transition_issue(crq, app.config['JIRA_TRANSITION_CRQ_PLANNING'])
    self.log.msg("Transitioned {} to planning".format(crq.key))
    jira.instance.create_issue_link('Relate', crq, logging)
    self.log.msg("Related {} to LOGGING service {}".format(crq.key, logging.key))
    task = jira.instance.create_issue(
      issuetype={'name': 'MOP Task'},
      assignee={'name': app.config['JIRA_USERNAME']},
      project=app.config['JIRA_CRQ_PROJECT'],
      description="Instanitate the attached templates in the zone associated "
                  "to the pool identified in the filename <pool_id>.<hostname>",
      summary='[TEST IMPLEMENTATION TASK] {}'.format(self.task.name),
      parent={'key': crq.key},
      customfield_14135={'value': 'IPG', 'child': {'value': 'IPG Big Data'}},
      customfield_15150={'value': 'No'})
    self.log.msg("Created task: {}".format(task.key))
    jira.instance.transition_issue(task, app.config['JIRA_TRANSITION_TASK_PLANNING'])
    self.log.msg("Transitioned {} to planning".format(task.key))
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
        filename='{}.{}.template'.format(pool.id, hostname),
        attachment=attachment_content)
      self.log.msg("Attached template for {} to task {}".format(hostname, task.key))
    jira.instance.transition_issue(task, app.config['JIRA_TRANSITION_TASK_WRITTEN'])
    self.log.msg("Transitioned task {} to written".format(task.key))
    jira.approver_instance.transition_issue(task, app.config['JIRA_TRANSITION_TASK_APPROVED'])
    self.log.msg("Approved task {}".format(task.key))
    jira.instance.transition_issue(crq, app.config['JIRA_TRANSITION_CRQ_PLANNED_CHANGE'])
    self.log.msg("Transitioned task {} to approved".format(task.key))
    jira.approver_instance.transition_issue(crq, app.config['JIRA_TRANSITION_CRQ_APPROVED'])
    self.log.msg("Transitioned change request {} to approved".format(crq.key))
    self.log.msg("Task ID {}".format(self.task.id))
    db_ticket = PoolTicket(
      pool=Session.merge(pool),
      action_id=PoolTicketActions.expand.value,
      ticket_key=crq.key,
      task=Session.merge(self.task))
    Session.add(db_ticket)
    Session.commit()
  except Exception as e:
    Session.rollback()
    if crq is not None:
      jira.cancel_crq_and_tasks(crq, comment="failure creating change tickets")
    raise e

def plan_update(self, pool, update_members):
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
    self.log.msg("Created change request: {}".format(crq.key))
    jira.instance.transition_issue(crq, app.config['JIRA_TRANSITION_CRQ_PLANNING'])
    self.log.msg("Transitioned {} to planning".format(crq.key))
    jira.instance.create_issue_link('Relate', crq, logging)
    self.log.msg("Related {} to LOGGING service {}".format(crq.key, logging.key))
    batch_size = floor(len(update_members) / app.config['BATCH_SIZE_PERCENT'])
    batch_size = 1 if batch_size == 0 else batch_size
    num_batches = min(len(update_members), app.config['BATCH_SIZE_PERCENT'])
    self.log.msg("updating {} hosts in pool {} requires {} tasks with no more than {} hosts per task".format(
      len(update_members),
      pool.name,
      num_batches,
      batch_size))
    batch_num = 0
    while len(update_members):
      batch_num += 1
      task = jira.instance.create_issue(
        issuetype={'name': 'MOP Task'},
        assignee={'name': app.config['JIRA_USERNAME']},
        project=app.config['JIRA_CRQ_PROJECT'],
        summary='[TASK {}/{} (Update {}%)] {}'.format(batch_num, num_batches, app.config['BATCH_SIZE_PERCENT'], self.task.name),
        parent={'key': crq.key},
        customfield_14135={'value': 'IPG', 'child': {'value': 'IPG Big Data'}},
        customfield_15150={'value': 'No'})
      self.log.msg("Created task: {}".format(task.key))
      jira.instance.transition_issue(task, app.config['JIRA_TRANSITION_TASK_PLANNING'])
      self.log.msg("Transitioned {} to planning".format(task.key))
      env = Environment(loader=ObjectLoader())
      for num in range(0, min(len(update_members), batch_size)):
        m = update_members.pop()
        filename = '{}.{}.template'.format(m.pool.id, m.vm_id)
        attachment_content = io.StringIO(m.current_template())
        jira.instance.add_attachment(
          issue=task,
          filename=filename,
          attachment=attachment_content)
        self.log.msg("Attached template for {} to task {}".format(filename, task.key))
      jira.instance.transition_issue(task, app.config['JIRA_TRANSITION_TASK_WRITTEN'])
      self.log.msg("Transitioned task {} to written".format(task.key))
      jira.approver_instance.transition_issue(task, app.config['JIRA_TRANSITION_TASK_APPROVED'])
      self.log.msg("Approved task {}".format(task.key))
    jira.instance.transition_issue(crq, app.config['JIRA_TRANSITION_CRQ_PLANNED_CHANGE'])
    self.log.msg("Transitioned change request {} to approved".format(task.key))
    jira.approver_instance.transition_issue(crq, app.config['JIRA_TRANSITION_CRQ_APPROVED'])
    self.log.msg("Transitioned change request {} to approved".format(crq.key))
    self.log.msg("Task ID {}".format(self.task.id))
    db_ticket = PoolTicket(
      pool=pool,
      action_id=PoolTicketActions.update.value,
      ticket_key=crq.key,
      task=Session.merge(self.task))
    Session.add(db_ticket)
    Session.commit()
  except Exception as e:
    Session.rollback()
    if crq is not None:
      jira.cancel_crq_and_tasks(crq, comment="failure creating change tickets")
    raise e

def plan_shrink(self, pool, shrink_members):
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
      customfield_17679="Pool shrink required")
    self.log.msg("Created change request: {}".format(crq.key))
    jira.instance.transition_issue(crq, app.config['JIRA_TRANSITION_CRQ_PLANNING'])
    self.log.msg("Transitioned {} to planning".format(crq.key))
    jira.instance.create_issue_link('Relate', crq, logging)
    self.log.msg("Related {} to LOGGING service {}".format(crq.key, logging.key))
    task = jira.instance.create_issue(
      issuetype={'name': 'MOP Task'},
      assignee={'name': app.config['JIRA_USERNAME']},
      project=app.config['JIRA_CRQ_PROJECT'],
      summary='[IMPLEMENTATION TASK] {}'.format(self.task.name),
      parent={'key': crq.key},
      customfield_14135={'value': 'IPG', 'child': {'value': 'IPG Big Data'}},
      customfield_15150={'value': 'No'})
    self.log.msg("Created task: {}".format(task.key))
    jira.instance.transition_issue(task, app.config['JIRA_TRANSITION_TASK_PLANNING'])
    self.log.msg("Transitioned {} to planning".format(task.key))
    for m in [Session.merge(m) for m in shrink_members]:
      filename = '{}.{}.template'.format(pool.id, m.vm_id)
      attachment_content = io.StringIO(m.template)
      jira.instance.add_attachment(
        issue=task,
        filename=filename,
        attachment=attachment_content)
      self.log.msg("Attached member {} to shrink to task {}".format(filename, task.key))
    jira.instance.transition_issue(task, app.config['JIRA_TRANSITION_TASK_WRITTEN'])
    self.log.msg("Transitioned task {} to written".format(task.key))
    jira.approver_instance.transition_issue(task, app.config['JIRA_TRANSITION_TASK_APPROVED'])
    self.log.msg("Approved task {}".format(task.key))
    jira.instance.transition_issue(crq, app.config['JIRA_TRANSITION_CRQ_PLANNED_CHANGE'])
    self.log.msg("Transitioned task {} to approved".format(task.key))
    jira.approver_instance.transition_issue(crq, app.config['JIRA_TRANSITION_CRQ_APPROVED'])
    self.log.msg("Transitioned change request {} to approved".format(crq.key))
    self.log.msg("Task ID {}".format(self.task.id))
    db_ticket = PoolTicket(
      pool=pool,
      action_id=PoolTicketActions.shrink.value,
      ticket_key=crq.key,
      task=Session.merge(self.task))
    Session.add(db_ticket)
    Session.commit()
  except Exception as e:
    if crq is not None:
      jira.cancel_crq_and_tasks(crq, comment="failure creating change tickets")
    raise e
