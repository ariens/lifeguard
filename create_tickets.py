from datetime import datetime
import logging
from app.views.task.models import Task, TaskThread
from app import app, jira
from app.views.vpool.models import PoolTicketActions
from app.views.vpool.elasticity_planning import plan_expansion
from app.views.vpool.elasticity_tasks import expand
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
      create_tickets(name, pool, members)
      execute_tickets(name, pool)
      logging.info("[{}] finished working on tickets for pool {}".format(name, pool.name))
    except Exception as e:
      defect_ticket = jira.defect_for_exception(
        username="ticket_script",
        summary_title="Lifeguard: Health Check => {})".format(e),
        tb=traceback.format_exc(),
        e=e)
      logging.error("[{}] experienced an error pool {}, error: {}, created defect ticket {}".format(
        name, pool.name, e, defect_ticket.key))
    finally:
      q.task_done()

def create_tickets(name, pool, members):
  expansion_ticket = pool.pending_ticket(PoolTicketActions.expand)
  #TODO: Remove None to force ticket creation
  if None and expansion_ticket is not None:
    logging.info("[{}] expansion ticket {} already created for {}".format(
      name, expansion_ticket.ticket_key, pool.name))
  else:
    expansion_names = pool.get_expansion_names(members)
    if expansion_names is not None and len(expansion_names) > 0:
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
      task_thread = TaskThread(task=task,
                               run_function=plan_expansion,
                               pool=pool,
                               expansion_names=expansion_names)
      task_thread.start()
      threads.append(task_thread)
      logging.info("[{}] launched background task {} to {}".format(name, task.id, title))

def execute_tickets(name, pool):
  for t in pool.change_tickets:
    if t.done == False:
      logging.info("[{}] fetching {}".format(name, t.ticket_key))
      crq = jira.instance.issue(t.ticket_key)
      if JiraApi.expired(crq):
        logging.info("[{}] {} has expired".format(name, crq.key))
        jira.cancel_crq_and_tasks(crq, "change has expired")
        t.done = True
        Session.add(t)
        Session.commit()
        logging.info("[{}] marked {} ticket {} as done for pool {} as crq is expired".format(
          name, t.action_name(), t.ticket_key, pool.name))
        continue
      elif JiraApi.in_window(crq):
        if jira.is_ready(crq):
          title = "{} pool {} under ticket {}".format(t.action_name(), pool.name, crq.key)
          task = Task(
            name=title,
            description=title,
            username="ticket_script")
          Session.add(task)
          Session.commit()
          runnable = None
          if t.action_id == PoolTicketActions.expand.value:
            runnable = expand
          if runnable is None:
            raise Exception("t.action_id is not a supported action to implement")
          task_thread = TaskThread(task=task,
                                   run_function=runnable,
                                   pool=pool,
                                   pool_ticket=t,
                                   issue=crq)
          task_thread.start()
          threads.append(task_thread)
          logging.info("[{}] launched background task {} to {}".format(name, task.id, title))
        else:
          logging.error("[{}] {} is in window and either it or one or "
                        "more sub tasks are not ready".format(name, crq.key))
      else:
        logging.info("[{}] {} ticket for pool {} not yet in window".format(
          name, t.action_name(), pool.name, crq.key))

    #TODO: Remove the break after we're done testing one at a time
    logging.info("breaking out early as we're testing one at a time")
    break

if __name__ == "__main__":
  q = Queue()
  logging.basicConfig(
    format='%(asctime)s %(levelname)s %(message)s',
    filename=app.config['LOG_FILE_TICKET_CREATOR'],
    level=app.config['LOG_LEVEL'] if app.config['LOG_LEVEL'] else 'INFO')
  logging.info("****************************************")
  logging.info("**** ticket creation script started ****")
  logging.info("****************************************")
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