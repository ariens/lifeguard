from app.database import Session
from app.one import OneProxy
from app import jira
from app.jira_api import JiraApi
from app.views.vpool.models import PoolMembership, PoolTicketActions, PoolMemberDiagnostic
from app.views.vpool.health import Diagnostic
from app.tasks.retry import retry
from datetime import datetime
from queue import Queue
from threading import Thread
from app import app
import time

def get_runnable_from_action_id(action_id):
  action_to_runnable = {PoolTicketActions.expand.value: expand,
                        PoolTicketActions.update.value: update,
                        PoolTicketActions.shrink.value: shrink}
  if action_id not in action_to_runnable:
    raise Exception("Action ID {} is not a supported action to implement".format(action_id))
  return action_to_runnable[action_id]

@retry(delay_seconds=app.config['HEALTH_CHECK_RETRY_DELAY_S'],
       max_lifetime_seconds=app.config['HEALTH_CHECK_RETRY_LIFETIME_S'])
def run_diagnostic(d):
  """
  Will keep trying to run a diagnostic until a successful exit code is returned.
  The initial delay (to avoid caching missing DNS records), the time to wait
  between attempts, and the length of time to keep trying are configurable from
  the application settings
  :param d:
  :return:
  """
  d.run()
  if d.exitcode != 0:
    raise Exception("diagnostic on {} got exit code {}".format(d.host, d.exitcode))
  return

def diagnostic_worker(q, results, log):
  while True:
    work = q.get()
    member = Session.merge(work['member'])
    vm = work['vm']
    diagnostic = Diagnostic(user=app.config['SSH_HEALTH_CHECK_USER'],
                            host=vm.name,
                            ssh_identity_file=app.config['SSH_IDENTITY_FILE'],
                            cmd=app.config['SSH_HEALTH_CHECK_CMD'],
                            timeout=app.config['SSH_HEALTH_CHECK_TIMEOUT'])
    try:
      run_diagnostic(diagnostic)
      log.msg("diagnostic against {} succeeded".format(diagnostic.host))
    except Exception as e:
      log.err("diagnostic error: {}".format(e))
    finally:
      Session.add(PoolMemberDiagnostic(
        vm_id=vm.id,
        pool=member.pool,
        start_date=diagnostic.start_date,
        end_date=diagnostic.end_date,
        stdout=diagnostic.stdout,
        stderr=diagnostic.stderr,
        exitcode=diagnostic.exitcode))
      Session.commit()
      #log.msg("saved diagnostic for {}".format(vm.name))
      results.append(diagnostic)
      q.task_done()

def run_diagnostics(members, log):
  """
  Runs diagnotics againts members to determine their health status
  :param members: The list of members to check health against
  :return: The list of diagnostics ran against the members
  """
  results = []
  q = Queue()
  for member in members:
    q.put({'member': member, 'vm': member.vm})
  for i in range(app.config['NUM_HEALTH_CHECK_THREADS']):
    t = Thread(target=diagnostic_worker, kwargs={'q': q,
                                                 'results': results,
                                                 'log': log})
    log.msg("starting diagnostic worker: #{}".format(i))
    t.daemon = True
    t.start()
  q.join()
  return results

def failed_diagnostics(diagnostics):
  for d in diagnostics:
    if not d.succeeded:
      yield d

def run_diagnostics_on_pool(pool, log):
  members = pool.get_memberships()
  results = run_diagnostics(members, log)
  failures = list(failed_diagnostics(results))
  if failures:
    title = "{} diagnostics failed for pool {}".format(len(failures), pool.name)
    defect_ticket = jira.defect_for_diagnostics(username="ticket_script",
                                                summary_title=title,
                                                diagnostics=failures)
    log.err("{} created Jira defect: {}".format(title, defect_ticket.key))
    comment = "{} failed diagnostics after change".format(len(failures))
    raise Exception(comment)

def expand(self, pool, pool_ticket, issue, cowboy_mode=False):
  new_vm_ids = []
  pool = Session.merge(pool)
  pool_ticket = Session.merge(pool_ticket)
  self.task = Session.merge(self.task)
  one_proxy = OneProxy(pool.cluster.zone.xmlrpc_uri, pool.cluster.zone.session_string, verify_certs=False)
  try:
    with Session.begin_nested():
      c_start = JiraApi.get_now()
      jira.start_crq(issue, log=self.log, cowboy_mode=cowboy_mode)
      for t in issue.fields.subtasks:
        t_start = JiraApi.get_now()
        t2 = jira.instance.issue(t.key)
        jira.start_task(t2, log=self.log, cowboy_mode=cowboy_mode)
        for a in t2.fields.attachment:
          template = a.get().decode(encoding="utf-8", errors="strict")
          vm_id = one_proxy.create_vm(template=template)
          new_vm_ids.append(vm_id)
          m = PoolMembership(pool=pool, vm_id=vm_id, template=a.get(), date_added=datetime.utcnow())
          Session.merge(m)
          self.log.msg("created new vm: {}".format(a.filename))
          jira.complete_task(t, start_time=t_start, log=self.log, cowboy_mode=cowboy_mode)
    Session.commit()
    self.log.msg("waiting for 120 seconds before running post change diagnostics")
    time.sleep(120)
    run_diagnostics_on_pool(pool, self.log)
    jira.complete_crq(issue, start_time=c_start, log=self.log, cowboy_mode=cowboy_mode)
  except Exception as e:
    self.log.err("Error occured: {}".format(e))
    jira.cancel_crq_and_tasks(issue, comment="an exception occured running this change: {}".format(e))
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
    jira.start_crq(issue, log=self.log, cowboy_mode=cowboy_mode)
    for t in issue.fields.subtasks:
      t_start = JiraApi.get_now()
      t2 = jira.instance.issue(t.key)
      jira.start_task(t2, log=self.log, cowboy_mode=cowboy_mode)
      for a in t2.fields.attachment:
        with Session.begin_nested():
          pool_id, vm_id = a.filename.split('.', 2)[:2]
          member = PoolMembership.query.filter_by(pool=pool, vm_id=vm_id).first()
          one_proxy.kill_vm(member.vm_id)
          Session.delete(member)
          self.log.msg("Killed VM {} and removed it as member of pool {}".format(member.vm_id, pool.name))
        Session.commit()
      jira.complete_task(t, start_time=t_start, log=self.log, cowboy_mode=cowboy_mode)
    Session.commit()
    self.log.msg("waiting for 120 seconds before running post change diagnostics")
    time.sleep(120)
    run_diagnostics_on_pool(pool, self.log)
    jira.complete_crq(issue, start_time=c_start, log=self.log, cowboy_mode=cowboy_mode)
  except Exception as e:
    self.log.err("Error occured: {}".format(e))
    jira.cancel_crq_and_tasks(issue, comment="an exception occured running this change: {}".format(e))
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
    jira.start_crq(issue, log=self.log, cowboy_mode=cowboy_mode)
    for t in issue.fields.subtasks:
      t_start = JiraApi.get_now()
      t2 = jira.instance.issue(t.key)
      jira.start_task(t2, log=self.log, cowboy_mode=cowboy_mode)
      updated_members = []
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
          updated_members.append(new_member)


          self.log.msg("waiting for 300 seconds before running post change diagnostics")
          time.sleep(300)
          run_diagnostics_on_pool(pool, self.log)



        Session.commit()
      jira.complete_task(t, start_time=t_start, log=self.log, cowboy_mode=cowboy_mode)
    Session.commit()
    jira.complete_crq(issue, start_time=c_start, log=self.log, cowboy_mode=cowboy_mode)
  except Exception as e:
    self.log.err("Error occured: {}".format(e))
    jira.cancel_crq_and_tasks(issue, comment="an exception occured running this change: {}".format(e))
    raise e
  finally:
    with Session.begin_nested():
      pool_ticket.done = True
      Session.merge(pool_ticket)
    Session.commit()