from app import app
from app.database import Session
from app.views.vpool.models import VirtualMachinePool
from app.one import OneProxy, INCLUDING_DONE
import logging

def all_pools_and_members():
  """
  Gets all pools efficiently by caching VMs per zone
  :return: A array of pool, member_array tuples
  """
  a = []
  zone_vm_cache = {}
  for pool in Session.query(VirtualMachinePool).all():
    if not pool.cluster.zone.name in zone_vm_cache:
      logging.info("VM cache for zone {} doesn't exist...".format(pool.cluster.zone.name))
      one_proxy = OneProxy(pool.cluster.zone.xmlrpc_uri, pool.cluster.zone.session_string, verify_certs=False)
      zone_vm_cache[pool.cluster.zone.name] = {vm.id: vm for vm in one_proxy.get_vms(INCLUDING_DONE)}
      logging.info("VM cache for zone {} populated with {} entries".format(
        pool.cluster.zone.name, len(zone_vm_cache[pool.cluster.zone.name])))
    a.append((pool, pool.get_memberships(vm_cache=zone_vm_cache[pool.cluster.zone.name])))
  return a
