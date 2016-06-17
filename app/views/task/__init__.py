import traceback, sys
from flask import request, redirect, url_for, render_template, flash, Blueprint, g, Markup
from app.views.task.models import Task
from flask_login import current_user, login_required
from app.views.task.models import Task, TaskResult, TaskThread

task_bp = Blueprint('task_bp', __name__, template_folder='templates')

@task_bp.route('/task/view/<int:task_id>', methods=['GET', 'POST'])
@login_required
def view(task_id):
  task = None
  try:
    task = Task.query.get(task_id)
  except Exception as e:
    traceback.print_exc(file=sys.stdout)
    flash("There was an error fetching task_id={}: {}".format(task_id, e), category='danger')
    return redirect(url_for('zone_bp.list'))
  return render_template('task/view.html', task=task)

@task_bp.route('/task/list', methods=['GET'])
@login_required
def list():
  tasks = None
  try:
    tasks = Task.query.order_by(Task.end_time.desc()).all()
  except Exception as e:
    traceback.print_exc(file=sys.stdout)
    flash("There was an error fetching tasks: {}".format(e), category='danger')
    return redirect(url_for('auth_bp.home'))
  return render_template('task/list.html', tasks=tasks)
