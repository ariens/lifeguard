from app import app, jira
from app.database import Session
from app.views.vpool.models import PoolMemberDiagnostic
from app.views.vpool.health import Diagnostic
from app.tasks import all_pools_and_members
from threading import Thread
from queue import Queue
import logging
import traceback

def worker(q, number):
  while True:
    work = q.get()
    member = Session.merge(work['member'])
    vm = work['vm']
    diagnostic = work['diagnostic']
    try:
      logging.info("[{}] about to run diagnostic on {}".format(number, diagnostic.host))
      diagnostic.run()
      logging.info("[{}] finished running diagnostic on {} (exit code: {})".format(number, vm.id, diagnostic.exitcode))
      Session.add(PoolMemberDiagnostic(
        vm_id=vm.id,
        pool=member.pool,
        start_date=diagnostic.start_date,
        end_date=diagnostic.end_date,
        stdout=diagnostic.stdout,
        stderr=diagnostic.stderr,
        exitcode=diagnostic.exitcode))
      Session.commit()
      logging.info("[{}] Saved diagnostic for {}".format(number, vm.id))
    except Exception as e:
      defect_ticket = jira.defect_for_exception(
        summary_title="Lifeguard: Health Check => {})".format(e),
        tb=traceback.format_exc(),
        e=e)
      logging.error("[{} worker experienced an error running diagnostic "
                    "host {}, error: {}, created defect ticket {}".format(
        number, vm.name, e, defect_ticket.key))
    finally:
      q.task_done()

if __name__ == '__main__':
  logging.basicConfig(
    format='%(asctime)s %(levelname)s %(message)s',
    filename=app.config['LOG_FILE_HEALTH_CHECKER'],
    level=app.config['LOG_LEVEL'] if app.config['LOG_LEVEL'] else 'INFO')
  logging.info("ticket creation script started")
  q = Queue()
  for (pool, members)  in all_pools_and_members():
    for member in members:
      q.put({'member': member,
             'vm': member.vm,
             'diagnostic': Diagnostic(user=app.config['SSH_HEALTH_CHECK_USER'],
                                      host=member.vm.name,
                                      ssh_identity_file=app.config['SSH_IDENTITY_FILE'],
                                      cmd=app.config['SSH_HEALTH_CHECK_CMD'],
                                      timeout=app.config['SSH_HEALTH_CHECK_TIMEOUT'])})

  for i in range(app.config['NUM_HEALTH_CHECK_THREADS']):
    t = Thread(target=worker, kwargs={'q': q, 'number': i})
    t.daemon = True
    t.start()
  q.join()
  print("queue is empty, exiting")