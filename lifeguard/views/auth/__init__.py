from ldap3 import LDAPException
from flask import request, render_template, flash, redirect, url_for, Blueprint, g
from flask_login import current_user, login_user, logout_user, login_required
from lifeguard.database import Session
from lifeguard import login_manager
from lifeguard.views.auth.models import User, LoginForm

auth_bp = Blueprint('auth', __name__, template_folder='templates')

@login_manager.user_loader
def load_user(id):
  return User.query.get(int(id))

@auth_bp.before_request
def get_current_user():
  g.user = current_user

@auth_bp.route('/')
@auth_bp.route('/auth')
def home():
  return render_template('auth/auth.html')

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
  if current_user.is_authenticated:
    flash('You are already logged in.')
    return redirect(url_for('auth.home'))
  form = LoginForm(request.form)
  if request.method == 'POST' and form.validate():
    username = request.form.get('username')
    password = request.form.get('password')
    try:
      User.try_login(username, password)
    except LDAPException:
      flash(
        'Invalid username or password. Please try again.',
        'danger')
      return render_template('auth/login.html', form=form)
    try:
      with Session.begin_nested():
        user = User.query.filter_by(username=username).first()
        if not user:
          user = User(username)
          Session.add(user)
          Session.commit()
        login_user(user)
        flash('You have successfully logged in.', category='success')
      return redirect(url_for('auth.home'))
    except Exception as e:
      flash('There was an error logging in: {}'.format(e), category='danger')
      raise e
  if form.errors:
    flash(form.errors, 'danger')
  return render_template('auth/login.html', form=form)

@auth_bp.route('/logout')
@login_required
def logout():
  logout_user()
  return redirect(url_for('auth.home'))
