from app.database import Session
from app.views.vpool.models import VirtualMachinePool

pools = Session.query(VirtualMachinePool).all()
for p in pools:
  print(p)