from flask import render_template, Blueprint
import time

testing_bp = Blueprint('testing_bp', __name__, template_folder='templates')

@testing_bp.route('/testing/sleep/<int:seconds>/', methods=['GET'])
def sleep(seconds):
  """
  Just a simple testing route for confirming concurrent access,
  server threading, and client connection rate limiting
  :param seconds:
  :return:
  """
  time.sleep(seconds)
  return render_template('testing/sleep.html', seconds=seconds)
