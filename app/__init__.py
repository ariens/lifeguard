from flask import Flask
from flask_login import LoginManager

app = Flask(__name__)
app.config.from_envvar('LIFEGUARD_CFG_FILE')

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'auth.login'

from app.database import db_session, init_db
init_db()

@app.teardown_appcontext
def shutdown_session(exception=None):
    db_session.remove()

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