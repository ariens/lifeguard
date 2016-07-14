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
  one_proxy = OneProxy(pool.cluster.zone.xmlrpc_uri, pool.cluster.zone.session_string, verify_certs=False)
  try:
    with Session.begin_nested():
      jira.start_crq(issue, comment="starting change")
      self.log.msg("starting change {}, ticket moved to implementation".format(issue.key))
      self.log.msg("starting task to expand pool {} under {}".format(pool.name, issue.key))
      for t in issue.fields.subtasks:
        jira.start_task(t, comment="starting task")
        self.log.msg("started sub task {}".format(t.key))
        t2 = jira.instance.issue(t.key)
        for a in t2.fields.attachment:
          template = a.get().decode(encoding="utf-8", errors="strict")
          vm_id = one_proxy.create_vm(template=template)
          new_vm_ids.append(vm_id)
          m = PoolMembership(pool=pool, vm_id=vm_id, template=a.get(), date_added=datetime.utcnow())
          Session.merge(m)
          self.log.msg("created new vm: {}".format(a.filename))
        jira.complete_task(t, comment="completed task")
      Session.commit()
      self.log.msg("change {} completed successfully".format(issue.key))
  except Exception as e:
    self.log.error("Error occured: {}".format(e))
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
    with Session.begin_nested:
      pool_ticket.done = True
      Session.merge(pool_ticket)
      Session.commit()
