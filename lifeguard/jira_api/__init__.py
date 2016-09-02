from jira import JIRA
from lifeguard import app
from flask_login import current_user
import pytz
import logging
import traceback
from datetime import datetime, timedelta

class TransitionException(Exception):
  pass

class JiraApi():
  str_jira_scheduled = "%Y-%m-%dT%H:%M:%S.000%z"
  def __init__(self,
               instance=None,
               approver_instance=None):
    self.instance = instance
    self.approver_instance = approver_instance

  @staticmethod
  def add_cowboy_verbiage(comment):
    return "{}  This change request was initiated in " \
           "cowboy mode which means that all change " \
           "management workflow, schedules, and " \
           "status fields are being ignored.".format(comment)

  def transition_issue(self, issue, state_name, **kwargs):
    state_id = app.config[state_name]
    try:
      self.instance.transition_issue(issue, state_id, **kwargs)
      logging.info("transitioned {} to {} ({})".format(issue.key, state_name, state_id))
    except Exception as e:
      logging.error("Error: {}".format(e))
      description = "Cannot transition {} in status {} to {} ({}). " \
                    "Available states are: {}".format(
        issue.key,
        issue.fields.status,
        state_name,
        state_id,
        {t['id'] : t['name'] for t in self.instance.transitions(issue)})
      defect = self.defect_for_exception(
        summary_title="issue transition exception",
        e=e,
        description=description,
        username="transition_issue()")
      logging.error("{} raised defect issue: {}".format(description, defect.key))
      raise e

  def cancel_crq_and_tasks(self, crq, comment):
    exceptions = []
    for t in crq.fields.subtasks:
      if str(t.fields.status).lower() in ['closed', 'cancelled']:
        logging.info("sub-task {} already in finished state ({})".format(t.key, t.fields.status))
        continue
      try:
        self.transition_issue(t,
          'JIRA_TRANSITION_TASK_CANCELLED',
          comment=comment,
          resolution={'id': app.config['JIRA_RESOLUTION_CANCELLED']})
      except Exception as e:
        logging.error("Error: {}".format(e))
        exceptions.append(e)
    if str(crq.fields.status).lower() != 'close':
      utc = pytz.utc
      tz = pytz.timezone(app.config['CM_TZ'])
      now_utc = utc.localize(datetime.utcnow())
      now_tz = now_utc.astimezone(tz)
      now_jira = now_tz.strftime(JiraApi.str_jira_scheduled)
      try:
        if str(crq.fields.status).lower() == 'implementation':
          self.transition_issue(
            crq,
            'JIRA_TRANSITION_CRQ_CLOSE',
            comment=comment,
            resolution={'id': app.config['JIRA_RESOLUTION_CANCELLED']},
            customfield_15235={"id": app.config['JIRA_RESOLUTION_DETAILS_UNSUCCESSFUL']},
            customfield_16430=now_jira,
            customfield_16431=now_jira)
        elif str(crq.fields.status).lower() == 'scheduled':
          self.transition_issue(
            crq,
            'JIRA_TRANSITION_CRQ_SCHEDULED_TO_CANCELLED',
            comment=comment)
        elif str(crq.fields.status).lower() == 'itcm/trm':
          self.transition_issue(
            crq,
            'JIRA_TRANSITION_CRQ_CANCELLED',
            comment=comment)
      except Exception as e:
        logging.error("Error: {}".format(e))
        exceptions.append(e)
    if len(exceptions):
      raise Exception("Caught {} exceptions trying to "
                      "cancel {} and it's sub-tasks".format(len(exceptions), crq))

  def start_crq(self, crq, log=None, cowboy_mode=False):
    comment = "Starting change request {} to {}.".format(crq.key, crq.fields.summary)
    if cowboy_mode:
      comment = JiraApi.add_cowboy_verbiage(comment)
    else:
      self.transition_issue(crq, 'JIRA_TRANSITION_CRQ_IMPLEMENTATION', comment=comment)
    if log:
      log.msg(comment)

  def complete_crq(self, crq, start_time, log=None, cowboy_mode=False):
    comment = "Successfully completed CRQ {} to {}".format(crq.key, crq.fields.summary)
    if cowboy_mode:
      comment = JiraApi.add_cowboy_verbiage(comment)
      self.cancel_crq_and_tasks(crq, comment=comment)
    else:
      self.transition_issue(
        crq,
        'JIRA_TRANSITION_CRQ_CLOSE',
        resolution={'id': app.config['JIRA_RESOLUTION_COMPLETED']},
        customfield_15235={"id": app.config['JIRA_RESOLUTION_DETAILS_SUCCESSFUL']},
        customfield_16430=start_time,
        customfield_16431=JiraApi.get_now(),
        comment=comment)
    if log:
      log.msg(comment)

  def start_task(self, task, log=None, cowboy_mode=False):
    comment = "Starting task {} to {}.".format(task.key, task.fields.summary)
    if cowboy_mode:
      comment = "{}  This task was initiated in cowboy " \
                "mode which means that all change management " \
                "workflow, schedules, and status fields are being " \
                "ignored.".format(comment)
    else:
      self.transition_issue(task, 'JIRA_TRANSITION_TASK_IMPLEMENTATION', comment=comment)
    if log is not None:
      log.msg(comment)

  def complete_task(self, task, start_time, log=None, cowboy_mode=False):
    comment = "Completed task {} to {}.".format(task.key, task.fields.summary)
    if cowboy_mode:
      comment = JiraApi.add_cowboy_verbiage(comment)
    else:
      self.transition_issue(
        task,
        'JIRA_TRANSITION_TASK_CLOSED',
        resolution={'id': app.config['JIRA_RESOLUTION_COMPLETED']},
        customfield_15235={"id": app.config['JIRA_RESOLUTION_DETAILS_SUCCESSFUL']},
        customfield_16430=start_time,
        customfield_16431=JiraApi.get_now(),
        comment=comment)
    if log:
      log.msg(comment)

  @staticmethod
  def get_now():
    utc = pytz.utc
    tz = pytz.timezone(app.config['CM_TZ'])
    now_utc = utc.localize(datetime.utcnow())
    now_tz = now_utc.astimezone(tz)
    now_jira = now_tz.strftime(JiraApi.str_jira_scheduled)
    return now_jira

  @staticmethod
  def is_ready(issue):
    if str(issue.fields.status).lower() != "scheduled":
      return False
    for t in issue.fields.subtasks:
      if str(t.fields.status).lower() != 'approved':
        return False
    return True

  @staticmethod
  def crq_and_tasks_ready(crq):
    if str(crq.fields.status) == app.config['JIRA_CRQ_READY_STATUS']:
      for t in crq.fields.subtasks:
        if str(t.fields.status) != app.config['JIRA_TASK_READY_STATUS']:
          logging.info("{} sub task {} status {} needs to be {}".format(
            crq.key, t.key, str(t.fields.status), app.config['JIRA_TASK_READY_STATUS']))
          return False
      return True
    logging.info("{} status {} needs to be {}".format(
      crq.key, str(crq.fields.status), app.config['JIRA_CRQ_READY_STATUS']))
    return False


  @staticmethod
  def expired(issue):
    tz = pytz.timezone(app.config['CM_TZ'])
    utc = pytz.utc
    now_utc = utc.localize(datetime.utcnow())
    now_tz = now_utc.astimezone(tz)
    window_end = datetime.strptime(issue.fields.customfield_14531, JiraApi.str_jira_scheduled)
    return  window_end < now_tz

  @staticmethod
  def in_window(issue):
    tz = pytz.timezone(app.config['CM_TZ'])
    utc = pytz.utc
    now_utc = utc.localize(datetime.utcnow())
    now_tz = now_utc.astimezone(tz)
    window_start = datetime.strptime(issue.fields.customfield_14530, JiraApi.str_jira_scheduled)
    window_end = datetime.strptime(issue.fields.customfield_14531, JiraApi.str_jira_scheduled)
    return  window_start <= now_tz <= window_end

  @staticmethod
  def next_immediate_window_dates():
    utc = pytz.utc
    tz = pytz.timezone(app.config['CM_TZ'])
    now_utc = utc.localize(datetime.utcnow())
    now_tz = now_utc.astimezone(tz)
    start = None
    if now_tz.hour < app.config['CM_DEADLINE_HOUR'] \
            or (now_tz.hour == app.config['CM_DEADLINE_HOUR'] and now_tz.minute < app.config['CM_DEADLINE_MIN']):
      start = tz.localize(datetime(now_tz.year, now_tz.month, now_tz.day, app.config['CM_SAME_DAY_START_HOUR']))
    else:
      delay_hours = timedelta(hours=app.config['CM_DEADLINE_MISSED_DELAY_HOURS'])
      start_day = now_tz + delay_hours
      start = tz.localize(datetime(
        start_day.year, start_day.month, start_day.day, app.config['CM_DEADLINE_MISSED_START_HOUR']))
    end = start + timedelta(hours=app.config['CM_WINDOW_LEN_HOURS'])
    return start.strftime(JiraApi.str_jira_scheduled), \
           end.strftime(JiraApi.str_jira_scheduled)

  @staticmethod
  def get_datetime_now():
    tz = pytz.timezone(app.config['CM_TZ'])
    now = pytz.utc.localize(datetime.utcnow()).astimezone(tz)
    return now.strftime(JiraApi.str_jira_scheduled)

  def new_connect(self):
    options = {'server': app.config['JIRA_HOSTNAME'], 'verify': False, 'check_update': False}
    self.instance = JIRA(options,
                basic_auth=(app.config['JIRA_USERNAME'], app.config['JIRA_PASSWORD']))
    self.approver_instance = JIRA(options,
                basic_auth=(app.config['JIRA_APPROVER_USERNAME'], app.config['JIRA_APPROVER_PASSWORD']))

  @staticmethod
  def ticket_link(issue=None, key=None):
    if issue is not None:
      return '<a href="{}/browse/{}">{}</a>'.format(app.config['JIRA_HOSTNAME'], issue.key, issue.key)
    if key is not None:
      return '<a href="{}/browse/{}">{}</a>'.format(app.config['JIRA_HOSTNAME'], key, key)
    raise Exception("both issue and key are None")

  def resolve(self, issue):
    self.instance.transition_issue(
      issue,
      app.config['JIRA_RESOLVE_TRANSITION_ID'],
      assignee={'name': app.config['JIRA_USERNAME']},
      resolution={'id': app.config['JIRA_RESOLVE_STATE_ID']})

  def defect_for_exception(self, summary_title, e, tb=None, username=None, description=None):
    if username is None:
      try:
        username = current_user.username
      except:
        username = "nobody"
    if tb is None:
      tb = traceback.format_exc()
    problem = "An {} exception occured".format(e)
    description = problem if description is None else "{}\n{}".format(problem, description)
    description = "{}\nTraceback:\n{}".format(description, tb)
    summary_title = '[auto-{}] Problem: {}'.format(username, summary_title)
    summary_title = (summary_title[:252] + '...') if len(summary_title) > 75 else summary_title
    return self.instance.create_issue(
      project=app.config['JIRA_PROJECT'],
      summary=summary_title,
      description=description,
      issuetype={'name': 'Defect'},
      customfield_13842=JiraApi.get_datetime_now(),
      customfield_13838= {"value": "No"},
      customfield_13831 =  [{"value": "Quality"},
                            {"value": "Risk Avoidance"}])

  def defect_for_diagnostics(self, username, summary_title, diagnostics):
    if username is None:
      try:
        username = current_user.username
      except:
        username = "nobody"
    description = "{} diagnostics failed".format(len(diagnostics))
    for d in diagnostics:
      description = "{}\nHost: {}".format(description, d.host)
      description = "{}\nCommand: {}".format(description, d.cmd)
      description = "{}\nExit Code: {}".format(description, d.exitcode)
      description = "{}\nStarted: {}".format(description, d.start_date)
      description = "{}\nFinished: {}".format(description, d.end_date)
      description = "{}\nInterrupted: {}".format(description, d.interrupted)
      description = "{}\nSTDOUT: {}".format(description, d.stdout)
      description = "{}\nSTDERR: {}".format(description, d.stderr)
      description = "{}\n{}".format(description, "-" * 40)
    summary_title = '[auto-{}] Problem: {}'.format(username, summary_title)
    return self.instance.create_issue(
      project=app.config['JIRA_PROJECT'],
      summary=summary_title,
      description=description,
      issuetype={'name': 'Defect'},
      customfield_13842=JiraApi.get_datetime_now(),
      customfield_13838= {"value": "No"},
      customfield_13831 =  [{"value": "Quality"},
                            {"value": "Risk Avoidance"}])