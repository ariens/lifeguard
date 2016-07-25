from app.database import Session
from app.one import OneProxy
from app import jira
from app.jira_api import JiraApi
from app.views.vpool.models import PoolMembership, PoolTicketActions
from datetime import datetime

def get_runnable_from_action_id(action_id):
  action_to_runnable = {PoolTicketActions.expand.value: expand,
                        PoolTicketActions.update.value: update,
                        PoolTicketActions.shrink.value: shrink}
  if action_id not in action_to_runnable:
    raise Exception("Action ID {} is not a supported action to implement".format(action_id))
  return action_to_runnable[action_id]

def expand(self, pool, pool_ticket, issue, cowboy_mode=False):
  new_vm_ids = []
  pool = Session.merge(pool)
  pool_ticket = Session.merge(pool_ticket)
  self.task = Session.merge(self.task)
  one_proxy = OneProxy(pool.cluster.zone.xmlrpc_uri, pool.cluster.zone.session_string, verify_certs=False)
  try:
    with Session.begin_nested():
      c_start = JiraApi.get_now()
      if not cowboy_mode:
        jira.start_crq(issue, comment="starting change")
        self.log.msg("starting change {}, ticket moved to implementation".format(issue.key))
      else:
        self.log.msg("starting change {} in cowbow mode, ignoring "
                     "CRQ workflow operations".format(issue.key))
      for t in issue.fields.subtasks:
        t_start = JiraApi.get_now()
        if not cowboy_mode:
          jira.start_task(t, comment="starting task")
          self.log.msg("starting task to expand pool {} under {}".format(pool.name, issue.key))
          self.log.msg("started sub task {}".format(t.key))
        else:
          self.log.msg("starting task to expand pool {} under {} in "
                       "cowbow mode, ignore task workflow".format(pool.name, issue.key))
        t2 = jira.instance.issue(t.key)
        for a in t2.fields.attachment:
          template = a.get().decode(encoding="utf-8", errors="strict")
          vm_id = one_proxy.create_vm(template=template)
          new_vm_ids.append(vm_id)
          m = PoolMembership(pool=pool, vm_id=vm_id, template=a.get(), date_added=datetime.utcnow())
          Session.merge(m)
          self.log.msg("created new vm: {}".format(a.filename))
        if not cowboy_mode:
          jira.complete_task(t, comment="completed task", start_time=t_start)
          self.log.msg("marked task {} as completed successfully".format(t.key))
      if not cowboy_mode:
        jira.complete_crq(issue, comment="completed task", start_time=c_start)
        self.log.msg("marked crq {} as completed successfully".format(issue.key))
      if cowboy_mode:
        jira.cancel_crq_and_tasks(issue, comment="change was implemented in cowbow mode, "
                                                 "CRQ/sub-tasks cancelled and workflow ignored")
      self.log.msg("change {} completed successfully".format(issue.key))
    Session.commit()
  except Exception as e:
    self.log.err("Error occured: {}".format(e))
    jira.cancel_crq_and_tasks(issue, "an exception occured running this change: {}".format(e))
    self.log.msg("Trying to clean up {} new VMs".format(len(new_vm_ids)))
    for kill_id in new_vm_ids:
      try:
        one_proxy.kill_vm(vm_id=kill_id)
        self.log.msg("killed VM ID {}".format(kill_id))
      except Exception as e2:
        self.log.err("Exception killing vm_id={}, error: {}".format(kill_id, e2))
    raise e
  finally:
    with Session.begin_nested():
      pool_ticket.done = True
      Session.merge(pool_ticket)
    Session.commit()

def shrink(self, pool, pool_ticket, issue, cowboy_mode=False):
  pool = Session.merge(pool)
  pool_ticket = Session.merge(pool_ticket)
  self.task = Session.merge(self.task)
  one_proxy = OneProxy(pool.cluster.zone.xmlrpc_uri, pool.cluster.zone.session_string, verify_certs=False)
  try:
    c_start = JiraApi.get_now()
    if not cowboy_mode:
      jira.start_crq(issue, comment="starting change")
      self.log.msg("starting change {}, ticket moved to implementation".format(issue.key))
    else:
      self.log.msg("starting change {} in cowbow mode, ignoring "
                   "CRQ workflow operations".format(issue.key))
    for t in issue.fields.subtasks:
      t_start = JiraApi.get_now()
      if not cowboy_mode:
        jira.start_task(t, comment="starting task")
        self.log.msg("starting task to shrink pool {} under {}".format(pool.name, issue.key))
        self.log.msg("started sub task {}".format(t.key))
      else:
        self.log.msg("starting task to shrink pool {} under {} in "
                     "cowbow mode, ignore task workflow".format(pool.name, issue.key))
      t2 = jira.instance.issue(t.key)
      for a in t2.fields.attachment:
        with Session.begin_nested():
          pool_id, vm_id = a.filename.split('.', 2)[:2]
          member = PoolMembership.query.filter_by(pool=pool, vm_id=vm_id).first()
          one_proxy.kill_vm(member.vm_id)
          Session.delete(member)
          self.log.msg("Killed VM {} and removed it as member of pool {}".format(member.vm_id, pool.name))
        Session.commit()
      if not cowboy_mode:
        jira.complete_task(t, comment="completed task", start_time=t_start)
        self.log.msg("marked task {} as completed successfully".format(t.key))
    if not cowboy_mode:
      jira.complete_crq(issue, comment="completed task", start_time=c_start)
      self.log.msg("marked crq {} as completed successfully".format(issue.key))
    if cowboy_mode:
      jira.cancel_crq_and_tasks(issue, comment="change was implemented in cowbow mode, "
                                               "ignored status/scheduling, implemented change, then cancelled "
                                               "CRQ/sub-tasks to close tickets")
    self.log.msg("change {} completed successfully".format(issue.key))
    Session.commit()
  except Exception as e:
    self.log.err("Error occured: {}".format(e))
    jira.cancel_crq_and_tasks(issue, "an exception occured running this change: {}".format(e))
    raise e
  finally:
    with Session.begin_nested():
      pool_ticket.done = True
      Session.merge(pool_ticket)
    Session.commit()

def update(self, pool, pool_ticket, issue, cowboy_mode=False):
  pool = Session.merge(pool)
  pool_ticket = Session.merge(pool_ticket)
  self.task = Session.merge(self.task)
  one_proxy = OneProxy(pool.cluster.zone.xmlrpc_uri, pool.cluster.zone.session_string, verify_certs=False)
  try:
    c_start = JiraApi.get_now()
    if not cowboy_mode:
      jira.start_crq(issue, comment="starting change")
      self.log.msg("starting change {}, ticket moved to implementation".format(issue.key))
    else:
      self.log.msg("starting change {} in cowbow mode, ignoring "
                   "CRQ workflow operations".format(issue.key))
    for t in issue.fields.subtasks:
      t_start = JiraApi.get_now()
      if not cowboy_mode:
        jira.start_task(t, comment="starting task")
        self.log.msg("starting task to update pool {} under {}".format(pool.name, issue.key))
        self.log.msg("started sub task {}".format(t.key))
      else:
        self.log.msg("starting task to update pool {} under {} in "
                     "cowbow mode, ignore task workflow".format(pool.name, issue.key))
      t2 = jira.instance.issue(t.key)
      for a in t2.fields.attachment:
        with Session.begin_nested():
          pool_id, vm_id = a.filename.split('.', 2)[:2]
          template = a.get().decode(encoding="utf-8", errors="strict")
          member = PoolMembership.query.filter_by(pool=pool, vm_id=vm_id).first()
          one_proxy.kill_vm(member.vm_id)
          self.log.msg("killed VM ID: {}".format(vm_id))
          Session.delete(member)
          new_id = one_proxy.create_vm(template=template)
          new_member = PoolMembership(pool=pool, vm_id=new_id, template=template, date_added=datetime.utcnow())
          Session.add(new_member)
          self.log.msg("Instantiated new VM ID {} and added as member of pool {}".format(new_member.vm_id, pool.name))
        Session.commit()
      if not cowboy_mode:
        jira.complete_task(t, comment="completed task", start_time=t_start)
        self.log.msg("marked task {} as completed successfully".format(t.key))
    if not cowboy_mode:
      jira.complete_crq(issue, comment="completed task", start_time=c_start)
      self.log.msg("marked crq {} as completed successfully".format(issue.key))
    if cowboy_mode:
      jira.cancel_crq_and_tasks(issue, comment="change was implemented in cowbow mode, "
                                               "ignored status/scheduling, implemented change, then cancelled "
                                               "CRQ/sub-tasks to close tickets")
    self.log.msg("change {} completed successfully".format(issue.key))
    Session.commit()
  except Exception as e:
    self.log.err("Error occured: {}".format(e))
    jira.cancel_crq_and_tasks(issue, "an exception occured running this change: {}".format(e))
    raise e
  finally:
    with Session.begin_nested():
      pool_ticket.done = True
      Session.merge(pool_ticket)
    Session.commit()

