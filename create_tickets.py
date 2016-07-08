from datetime import datetime
import logging
from app.views.task.models import Task, TaskThread
from app import app, jira
from app.views.vpool.models import PoolTicketActions
from app.views.vpool.elasticity_tasks import plan_expansion
from app.jira_api import JiraApi
from app.tasks import all_pools_and_members
from queue import Queue
from threading import Thread
from app.database import Session
import traceback

threads = []

def worker(name):
  while True:
    work = q.get()
    members = work['members']
    pool = Session.merge(work['pool'])
    try:
      logging.info("[{}] assigned tickets for pool {}".format(name, pool.name))
      execute_tickets(name, pool)
      create_tickets(name, pool, members)
      logging.info("[{}] finished working on tickets for pool {}".format(name, pool.name))
    except Exception as e:
      defect_ticket = jira.defect_for_exception(
        username="ticket_script",
        summary_title="Lifeguard: Health Check => {})".format(e),
        tb=traceback.format_exc(),
        e=e)
      logging.error("[{}] experienced an error running diagnostic "
                    "pool {}, error: {}, created defect ticket {}".format(
        name, pool.name, e, defect_ticket.key))
    finally:
      q.task_done()

def create_tickets(name, pool, members):
  expansion_ticket = pool.pending_ticket(PoolTicketActions.expand)
  if expansion_ticket is not None:
    logging.info("[{}] expansion ticket {} already created for {}".format(
      name, expansion_ticket.ticket_key, pool.name))
  else:
    expansion_names = pool.get_expansion_names(members)
    if len(expansion_names) > 0:
      logging.info("[{}] {} requires expansion and an existing change ticket doesn't exist".format(name, pool.name))
      title = 'Plan Change => Pool Expansion: {} ({} members to {})'.format(pool.name, len(members), pool.cardinality)
      description = "Pool expansion triggered that will instantiate {} new VM(s): \n\n*{}".format(
            len(expansion_names),
            "\n*".join(expansion_names))
      task = Task(
        name=title,
        description="{}\n{}".format(title, description),
        username="ticket_script")
      Session.add(task)
      Session.commit()
      task_thread = TaskThread(task_id=task.id,
                               run_function=plan_expansion,
                               pool=pool,
                               expansion_names=expansion_names)
      task_thread.start()
      threads.append(task_thread)
      logging.info("[{}] launched background task {} to {}".format(name, task.id, title))

def execute_tickets(name, pool):
  for t in pool.change_tickets:
    issue = jira.instance.issue(t.ticket_key)
    if t.done == False:
      if JiraApi.done_issue(issue):
        t.done = True
        Session.add(t)
        Session.commit()
        logging.info("[{}] marked {} ticket {} as done for pool {} as Jira issue was Closed/Cancelled".format(
          name, t.action_name(), t.ticket_key, pool.name))
      else:
        if JiraApi.expired(issue):
          #TODO: determine why tickets can't be cancelled via Jira API (we can still mark as done in our DB)
          t.done = True
          Session.add(t)
          Session.commit()
          logging.info("[{}] marked {} ticket {} as done for pool {} as Jira issue expired".format(
            name, t.action_name(), t.ticket_key, pool.name))
        if JiraApi.in_window(issue):
          logging.info("[{}] {} ticket for pool {} is in window, launching task not yet implemented".format(
            name, t.action_name(), pool.name, issue.key))
          #TODO: Call the task to complete the ticket
        else:
          logging.info("[{}] {} ticket for pool {} not yet in window".format(
            name, t.action_name(), pool.name, issue.key))
    else:
      if not JiraApi.done_issue(issue):
        #TODO: determine why tickets can't be cancelled via the Jira API (so we can clean these up)
        pass

if __name__ == "__main__":
  q = Queue()
  logging.basicConfig(
    format='%(asctime)s %(levelname)s %(message)s',
    filename=app.config['LOG_FILE_TICKET_CREATOR'],
    level=app.config['LOG_LEVEL'] if app.config['LOG_LEVEL'] else 'INFO')
  logging.info("ticket creation script started")
  for (pool, members)  in all_pools_and_members():
    logging.info("retreived pool: {}".format(pool.name))
    q.put({'pool': pool,
           'members': members})

  for i in range(app.config['NUM_HEALTH_CHECK_THREADS']):
    t = Thread(target=worker, kwargs={'name': 'worker_{}'.format(i)})
    t.daemon = True
    t.start()
  q.join()
  logging.info("Queue is now empty, {} threads created".format(len(threads)))
  for t in threads:
    logging.info("joining thread {}-{}".format(t.ident, t.name))
    t.join()
    logging.info("thread {}-{} finished".format(t.ident, t.name))


