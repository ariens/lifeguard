import traceback
from flask import Flask
from flask_login import LoginManager

app = Flask(__name__)
app.config.from_envvar('LIFEGUARD_CFG_FILE')

from app.jira_api import JiraApi
jira = JiraApi()
jira.new_connect()

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'auth.login'

from app.database import init_db, Session
database.init_db()

from flask import render_template

@app.errorhandler(500)
def internal_server_error(e):
  defect = jira.defect_for_exception(
    summary_title="Lifeguard: Internal Server Error (500)",
    tb=traceback.format_exc(),
    e=e)
  if app.config['LINK_DEFECT_IN_500']:
    return render_template('500.html', defect_link=JiraApi.ticket_link(issue=defect)), 404
  else:
    return render_template('500.html'), 404

@app.teardown_appcontext
def shutdown_session(exception=None):
  Session.remove()

from app.views.auth import auth_bp
app.register_blueprint(auth_bp)

from app.views.zone import zone_bp
app.register_blueprint(zone_bp)

from app.views.cluster import cluster_bp
app.register_blueprint(cluster_bp)

from app.views.vpool import vpool_bp
app.register_blueprint(vpool_bp)

from app.views.task import task_bp
app.register_blueprint(task_bp)

from app.views.testing import testing_bp
app.register_blueprint(testing_bp)