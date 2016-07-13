from app.database import Session
from app.one import OneProxy
from app import app, jira
from app.views.vpool.models import PoolMembership
import traceback
from datetime import datetime

def expand(self, pool, pool_ticket, issue):
  new_vm_ids = []
  pool = Session.merge(pool)
  pool_ticket = Session.merge(pool_ticket)
  self.task = Session.merge(self.task)
  try:
    jira.start_crq(issue, comment="starting change")
    self.log.msg("starting change {}, ticket moved to implementation".format(issue.key))
  except Exception as e:
    self.log.err("Failed to start {} and transition to implementation".format(issue.key))
    jira.fail_crq(issue, "Failing change after errors moving ticket to implementation")
    self.log.msg("Failed change request {}".format(issue.key))
    raise e
  one_proxy = OneProxy(pool.cluster.zone.xmlrpc_uri, pool.cluster.zone.session_string, verify_certs=False)
  self.log.msg("starting task to expand pool {} under {}".format(pool.name, issue.key))
  Session.begin_nested()
  exception = None
  try:
    for t in issue.fields.subtasks:
      if exception:
        jira.fail_task(t)
        self.log.err("cancelled {} after previous sub-task encourtered error".format(t.key))
        continue
      try:
        jira.start_task(t)
        self.log.msg("Transitioned sub task {} to implementation".format(t.key))
        t2 = jira.instance.issue(t.key)
        for a in t2.fields.attachment:
          template = a.get().decode(encoding="utf-8", errors="strict")
          vm_id = one_proxy.create_vm(template=template)
          new_vm_ids.append(vm_id)
          self.log.msg("allocated vm: {} as ID={}".format(a.filename, vm_id))
          m = PoolMembership(pool=pool, vm_id=vm_id, template=a.get(), date_added=datetime.utcnow())
          Session.add(m)
        jira.complete_task(t)
        raise Exception("purposefully injected error")

      except Exception as e:
        raise e
        exception = e
        jira.fail_task(t, app.config['JIRA_RESOLUTION_FAILED'])
        self.log.err("failed task {} after error: {}".format(t.key, e))
    if exception:
      raise exception
    pool_ticket.done = True
    Session.merge(pool_ticket)
    Session.commit()
  except Exception as e:
    raise e
    Session.rollback()
    jira.fail_crq(issue)
    self.log.err("failed task {} after errors were encountered".format(issue.key))
    defect = jira.defect_for_exception(summary_title="expand failed", tb=traceback.format_exc(), e=e, username='ticket_script')
    self.log.err("There was an exception: {}, created defect: {}".format(e, defect.key))
    self.log.msg("Entering into cleanup mode")
    self.log.msg("Trying to clean up {} new VMs".format(len(new_vm_ids)))
    for kill_id in new_vm_ids:
      try:
        one_proxy.kill_vm(vm_id=kill_id)
        self.log.msg("killed VM ID {}".format(vm_id))
      except Exception as e2:
        self.log.err("Exception killing vm_id={}, error: {}".format(kill_id, e2))
    raise e