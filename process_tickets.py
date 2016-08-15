import sys, os, getopt, logging
from app.views.task.models import Task, TaskThread
from app import app, jira
from app.views.vpool.elasticity_planning import plan_expansion, plan_shrink, plan_update
from app.views.vpool.elasticity_tasks import get_runnable_from_action_id
from app.jira_api import JiraApi
from app.tasks import all_pools_and_members
from queue import Queue
from threading import Thread
from app.database import Session
import traceback

threads = []

def worker(name, q, cowboy_mode, plan, implement):
  while True:
    work = q.get()
    members = work['members']
    pool = Session.merge(work['pool'])
    if cowboy_mode:
      name = "{}_{}".format('cowboy', name)
      logging.info("[{}] called in cowbow mode.  All change management "
                   "protocol around status/schedule will be ingored".format(name))
    try:
      logging.info("[{}] assigned tickets for pool {}".format(name, pool.name))
      if plan:
        existing_ticket = pool.pending_ticket()
        expansion_names = pool.get_expansion_names(members)
        shrink_members = pool.get_members_to_shrink(members)
        update_members = pool.get_update_members(members)
        if existing_ticket is not None:
          logging.info("[{}] existing expand ticket {} already created for {}".format(
            name, existing_ticket.ticket_key, pool.name))
        elif expansion_names:
          create_expansion_ticket(name, pool, members, expansion_names)
        elif shrink_members:
          create_shrink_ticket(name, pool, members, shrink_members)
        elif update_members:
          create_update_ticket(name, pool, members, update_members)
      else:
        logging.info("[{}] skipping ticket planning".format(name))
      if implement:
        execute_tickets(name, pool, cowboy_mode)
      else:
        logging.info("[{}] skipping ticket implementation".format(name))
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

def create_expansion_ticket(name, pool, members, expansion_names):
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
                           pool=Session.merge(pool),
                           expansion_names=expansion_names)
  threads.append(task_thread)
  logging.info("[{}] launched background task {} to {}".format(name, task.id, title))

def create_shrink_ticket(name, pool, members, shrink_members):
  logging.info("[{}] {} requires shrinking and an existing change ticket doesn't exist".format(name, pool.name))
  title = 'Plan Shrink => Pool {} ({} members to {})'.format(pool.name, len(members), pool.cardinality)
  description = "Pool shrink triggered that will shutdown {} VM(s): \n\n*{}".format(
        len(shrink_members),
        "\n*".join([m.vm.name for m in shrink_members]))
  task = Task(
    name=title,
    description="{}\n{}".format(title, description),
    username="ticket_script")
  Session.add(task)
  Session.commit()
  task_thread = TaskThread(task=task,
                           run_function=plan_shrink,
                           pool=Session.merge(pool),
                           shrink_members=shrink_members)
  threads.append(task_thread)
  logging.info("[{}] launched background task {} to {}".format(name, task.id, title))

def create_update_ticket(name, pool, members, update_members):
    logging.info("[{}] {} requires updating and an existing change ticket doesn't exist".format(name, pool.name))
    title = 'Plan Update => Pool {} ({}/{} members need updates)'.format(pool.name, len(members), pool.cardinality)
    description = "Pool update triggered that will update {} VM(s): \n\n*{}".format(
          len(update_members),
          "\n*".join([m.vm.name for m in update_members]))
    task = Task(
      name=title,
      description="{}\n{}".format(title, description),
      username="ticket_script")
    Session.add(task)
    Session.commit()
    task_thread = TaskThread(task=task,
                             run_function=plan_update,
                             pool=Session.merge(pool),
                             update_members=update_members)
    threads.append(task_thread)
    logging.info("[{}] launched background task {} to {}".format(name, task.id, title))

def execute_tickets(name, pool, cowboy_mode=False):
  for t in pool.change_tickets:
    try:
      if t.done == False:
        logging.info("[{}] fetching {}".format(name, t.ticket_key))
        crq = jira.instance.issue(t.ticket_key)
        if not cowboy_mode and JiraApi.expired(crq):
          logging.info("[{}] {} has expired".format(name, crq.key))
          jira.cancel_crq_and_tasks(crq, "change has expired")
          t.done = True
          Session.add(t)
          logging.info("[{}] marked {} ticket {} as done for pool {} as crq is expired".format(
            name, t.action_name(), t.ticket_key, pool.name))
        elif cowboy_mode or JiraApi.in_window(crq):
          logging.info("[{}] change {} is in window".format(name, crq.key))
          if cowboy_mode or jira.is_ready(crq):
            title = "{} pool {} under ticket {}".format(t.action_name(), pool.name, crq.key)
            task = Task(
              name=title,
              description=title,
              username="ticket_script")
            Session.add(task)
            Session.commit()
            task_thread = TaskThread(task=task,
                                     run_function=get_runnable_from_action_id(t.action_id),
                                     pool=pool,
                                     pool_ticket=t,
                                     issue=crq,
                                     cowboy_mode=cowboy_mode)
            threads.append(task_thread)
            logging.info("[{}] launched background task {} to {}".format(name, task.id, title))
          else:
            logging.error("[{}] {} is in window and either it or one or "
                          "more sub tasks are not ready".format(name, crq.key))
        else:
          logging.info("[{}] {} change {} for pool {} not yet in window".format(
            name, t.action_name(), crq.key, pool.name))
    except Exception as e:
      logging.error("[{}] error executing {}: {}".format(name, t.ticket_key, e))

def process_tickets(cowbow_mode, plan, implement):
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
    t = Thread(target=worker, kwargs={'q': q,
                                      'name': 'worker_{}'.format(i),
                                      'cowboy_mode': cowbow_mode,
                                      'plan': plan,
                                      'implement': implement})
    t.daemon = True
    t.start()
  q.join()
  logging.info("Queue is now empty, {} threads created".format(len(threads)))
  for t in threads:
    logging.info("starting thread {}-{}".format(t.ident, t.name))
    t.start()
  for t in threads:
    logging.info("joining thread {}-{}".format(t.ident, t.name))
    t.join()
    logging.info("thread {}-{} finished".format(t.ident, t.name))
  logging.info("finished")

def parse_boolean_opt(b_str, opt_name):
  if b_str.lower() in ['true', 'yes']:
    return True
  elif b_str.lower() in ['false', 'no']:
    return False
  else:
    raise Exception("cannot parse boolean value {} for {} (expecting true/false or yes/no)".format(b_str, opt_name))

def usage():
  print("Usage: /path/to/python {} [<options>]".format(os.path.basename(__file__)))
  print("Options:")
  print("\t--plan=True (create CRQs for actions that need to be performed)")
  print("\t--implement=True (implement CRQs for actions that need to be performed)")
  print("\t--cowboy-mode=False (implement CRQs regardless of status/schedule then cancel CRQ andd sub-tasks once done)")
  print("\t-h, --help (this message)")

def parse_args(argv):
  cowboy_mode = False
  plan = True
  implement = True
  try:
    opts, args = getopt.getopt(argv,"h:c", ["cowboy-mode=", "help=", "plan=", "implement="])
    for opt, arg in opts:
      if opt == ['-h', '--help']:
        usage()
        sys.exit()
      elif opt in ("--cowboy-mode"):
        cowboy_mode = parse_boolean_opt(arg, "--cowboy-mode")
      elif opt in ("--plan"):
        plan = parse_boolean_opt(arg, "--plan")
      elif opt in ("--implement"):
        implement = parse_boolean_opt(arg, "--implement")
  except Exception as err:
    print(str(err))
    usage()
    sys.exit(2)
  process_tickets(cowboy_mode, plan, implement)

if __name__ == "__main__":
  parse_args(sys.argv[1:])