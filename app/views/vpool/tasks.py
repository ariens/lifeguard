import io
from app import app, jira
from app.views.vpool.models import VirtualMachinePool
from app.jira_api import JiraApi
from jinja2 import Environment
from app.views.template.models import VarParser, ObjectLoader

def plan_expansion(self, title, description, username, pool_id, expansion_names):
  """
  This get's launched as a background task because the Jira API calls take too long
  :return:
  """
  from sqlalchemy import create_engine
  from sqlalchemy.orm import scoped_session, sessionmaker

  engine = create_engine(app.config['SQLALCHEMY_DATABASE_URI'])
  Session = scoped_session(sessionmaker(autocommit=False,
                                        autoflush=False,
                                        bind=engine))
  session = Session()
  pool = VirtualMachinePool.query.get(pool_id)
  session.merge(pool)
  logging = crq = task = None
  try:
    start, end = jira.next_immediate_window_dates()
    logging = jira.instance.issue('SVC-1020')
    crq = jira.instance.create_issue(
      project=app.config['JIRA_CRQ_PROJECT'],
      issuetype={'name': 'Change Request'},
      assignee={'name': app.config['JIRA_USERNAME']},
      summary='[auto-{}] {}'.format(username, title),
      description=description,
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
      summary='[auto-{}] expansion'.format(username),
      parent={'key': crq.key},
      customfield_14135={'value': 'IPG', 'child': {'value': 'IPG Big Data'}},
      customfield_15150={'value': 'No'})
    self.log_msg("Created task: {}".format(task.key))
    jira.instance.transition_issue(task, app.config['JIRA_TRANSITION_TASK_PLANNING'])
    self.log_msg("Transition {} to planning".format(task.key))
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
        filename='{}.template'.format(hostname),
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
  except Exception as e:
    if crq is not None:
      jira.instance.transition_issue(crq, app.config['JIRA_TRANSITION_CRQ_CANCELLED'])
    if task is not None:
      jira.instance.transition_issue(task, app.config['JIRA_TRANSITION_TASK_CANCELLED'])
    raise e