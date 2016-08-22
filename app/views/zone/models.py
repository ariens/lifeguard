from flask_wtf import Form
from wtforms import StringField, PasswordField, TextAreaField
from wtforms.validators import InputRequired
from app.database import Base
from sqlalchemy import Column, Integer, String, Text
from app.ddns import DdnsAuditor

class Zone(Base):
  __tablename__ = 'zone'
  number = Column(Integer, primary_key=True)
  name = Column(String(100), unique=True, nullable=False)
  xmlrpc_uri = Column(String(100), nullable=False)
  session_string = Column(String(100), nullable=False)

  template = Column(Text())
  vars = Column(Text())
  ddns_master = Column(String(250), nullable=False)
  ddns_domain = Column(String(250), nullable=False)
  ddns_tsig_fwd_name = Column(String(250), nullable=False)
  ddns_tsig_fwd_key = Column(String(250), nullable=False)
  ddns_tsig_rev_name = Column(String(250), nullable=False)
  ddns_tsig_rev_key = Column(String(250), nullable=False)

  def __init__(self,
               number=None,
               name=None,
               xmlrpc_uri=None,
               session_string=None,
               template=None,
               vars=None,
               ddns_master=None,
               ddns_domain=None,
               ddns_tsig_fwd_name=None,
               ddns_tsig_fwd_key=None,
               ddns_tsig_rev_name=None,
               ddns_tsig_rev_key=None):
    self.number = number
    self.name = name
    self.xmlrpc_uri = xmlrpc_uri
    self.session_string = session_string
    self.template = template
    self.vars = vars
    self.ddns_master = ddns_master
    self.ddns_domain = ddns_domain
    self.ddns_tsig_fwd_name = ddns_tsig_fwd_name
    self.ddns_tsig_fwd_key = ddns_tsig_fwd_key
    self.ddns_tsig_rev_name = ddns_tsig_rev_name
    self.ddns_tsig_rev_key = ddns_tsig_rev_key

  def __str__(self):
    return 'Zone: number={}, name={}, xmlrpc_uri={}'.format(
      self.number, self.name, self.xmlrpc_uri)

  def __repr__(self):
    self.__str__()

  def get_ddns_api(self):
    return DdnsAuditor(zone=self)


class ZoneForm(Form):
  name = StringField('Name', [InputRequired()])
  number = StringField('Number', [InputRequired()])
  xmlrpc_uri = StringField('XML-RPC URI', [InputRequired()])
  session_string = PasswordField('Session String', [InputRequired()])
  ddns_master = StringField('DDNS Master', [InputRequired()])
  ddns_domain = StringField('DDNS Domain', [InputRequired()])
  ddns_tsig_fwd_name = StringField('TSIG Forward Key Name', [InputRequired()])
  ddns_tsig_fwd_key = StringField('TSIG Forward Key Value', [InputRequired()])
  ddns_tsig_rev_name = StringField('TSIG Reverse Key Name', [InputRequired()])
  ddns_tsig_rev_key = StringField('TSIG Reverse Key Value', [InputRequired()])

class ZoneTemplateForm(Form):
  template = TextAreaField('Zone Template')
  vars = TextAreaField('Zone Variables')