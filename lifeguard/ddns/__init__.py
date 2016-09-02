import dns.update
import dns.query
import dns.tsigkeyring
import dns.resolver
from lifeguard.views.task.models import DumbLog


class DdnsAuditor:

  def __init__(self, zone):
    self.zone = zone
    self.fwd_keyring = dns.tsigkeyring.from_text({zone.ddns_tsig_fwd_name: zone.ddns_tsig_fwd_key})
    self.rev_keyring = dns.tsigkeyring.from_text({zone.ddns_tsig_rev_name: zone.ddns_tsig_rev_key})

  def get_fwd_update(self):
    return dns.update.Update(self.zone.ddns_domain, keyring=self.fwd_keyring)

  def get_rev_update(self):
    return dns.update.Update(self.zone.ddns_domain, keyring=self.rev_keyring)

  def send_update(self, update):
    response = dns.query.tcp(update, self.zone.ddns_master, timeout=10)
    if response.rcode() != 0:
      raise Exception("DDNS update of {} response was not NOERROR: {}".format(update, response.rcode()))

  def delete_ip_from_pool_record(self, pool, ip):
    updater = self.get_fwd_update()
    updater.delete('{}.'.format(pool.name), 'A', ip)
    self.send_update(updater)
    return True

  def add_ip_to_pool_record(self, pool, ip):
    updater = self.get_fwd_update()
    updater.add('{}.'.format(pool.name), 30, 'A', ip)
    self.send_update(updater)
    return True

  def replace_rev_ptr(self, ptr_record, name):
    updater = self.get_rev_update()
    updater.delete('{}.'.format(ptr_record))
    updater.add('{}.'.format(ptr_record), 30, 'A', name)
    self.send_update(updater)
    return True

  def replace_fwd(self, name, ip):
    updater = self.get_fwd_update()
    updater.delete('{}.'.format(name))
    updater.add('{}.'.format(name), 30, 'A', ip)
    self.send_update(updater)
    return True

  @staticmethod
  def get_rev_zone_and_record(ip):
    """
    Accepts an IPv4 address and calculates the reverse/PTR zone and record
    with the assumption that the reverse namespace is delegated into /24s
    zones: c.b.a.in-addr.arpa.
    :param ip:
    :return: zone, record
    """
    ip_parts = ip.split('.')
    zone = '{}.{}.{}.in-addr.arpa.'.format(
      ip_parts[2],
      ip_parts[1],
      ip_parts[0])
    record = '{}.{}'.format(ip_parts[3], zone)
    return zone, record

  @staticmethod
  def get_records(name, record_type='A'):
    resolver = dns.resolver.Resolver()
    return resolver.query(name, record_type)

  def audit_pool_dns(self, pool, members, resolve_errors=False):
    log = DumbLog()
    pool_ips = pool.get_dns_ips()
    log.msg("{} records present in DNS at time of audit are:".format(pool.name))
    for pool_ip in pool_ips:
      log.msg("   - {}".format(pool_ip))
    log.msg("{} members present in database/ONE at time of audit are:".format(pool.name))
    for m in members:
      log.msg("   - {}: {}".format(m.vm.name, m.vm.ip_address))
    member_ips = [m.vm.ip_address for m in members]
    members_by_ip = {m.vm.ip_address : m for m in members}
    #
    # Audit pool name to ensure all IPs belong to members
    #
    log.msg("*** [ Auditing DNS records to ensure members exist ] ***")
    for pool_ip in pool_ips:
      if pool_ip not in member_ips:
        log.err("Pool record for IP {} does not belong to any member VM".format(pool_ip))
        try:
          if resolve_errors and self.delete_ip_from_pool_record(pool=pool, ip=pool_ip):
            log.msg("Deleted {} record from {} record".format(pool_ip, pool.name))
        except Exception as e:
          log.err("failed to remove {} from pool record {}, error was:  {}".format(
            pool_ip, pool.name, e))
      else:
        log.msg("{} belongs to {} (VM ID={})".format(
          pool_ip,
          members_by_ip[pool_ip].vm.name,
          members_by_ip[pool_ip].vm.id))
    #
    #  Audit members to ensure all IPs exist in pool name
    #
    log.msg("*** [ Auditing members to ensure IPs exist in pool record ] ***")
    for m in members:
      if m.vm.ip_address not in pool_ips:
        log.err("Member {} (IP: {}, VM ID={}) not contained in DNS pool record".format(
          m.vm.name, m.vm.ip_address, m.vm.id))
        try:
          if resolve_errors and self.add_ip_to_pool_record(pool=pool, ip=m.vm.ip_address):
            log.msg("Added missing member IP {} to pool record {}".format(
              m.vm.ip_address, pool.name))
        except Exception as e:
          log.err("failed to add missing member IP {} to pool record {}, error was:  {}".format(
            m.vm.ip_address, pool.name, e))
      else:
        log.msg("Member {} (IP: {}, VM ID={}) present in DNS pool record".format(
          m.vm.name, m.vm.ip_address, m.vm.id))
    #
    # Audit reverse PTR record for exactly 1 expected name
    #
    log.msg("*** [ Auditing PTR records of members ] ***")
    for m in members:
      rev_zone, rev_rec = DdnsAuditor.get_rev_zone_and_record(m.vm.ip_address)
      try:
        names = [rec.to_text() for rec in self.get_records(rev_rec, record_type='PTR')]
        if len(names) == 1 and names[0] == "{}.".format(m.vm.name):
          log.msg("Reverse matches member {} (PTR: {})".format(m.vm.name, rev_rec))
        else:
          log.msg("Reverse doesn't match member {} (PTR: {}), resolved: {}".format(
            m.vm.name, rev_rec, names[0]))
          try:
            if resolve_errors and self.replace_rev_ptr(rev_rec, m.vm.name):
              log.msg("Replaced reverse record {} as PTR to {}".format(rev_rec, m.vm.name))
          except Exception as e:
            log.err("Failed to replace reverse record {} as PTR to {}, error was: {}".format(
              rev_rec, m.vm.name, e))
      except Exception as e:
        log.err("Exception occured resolving reverse PTR for member {} (PTR: {}): {}".format(
          m.vm.name, rev_rec, e))
    #
    # Audit forward member name for exactly 1 expected IP
    #
    log.msg("*** [ Auditing A records of members ] ***")
    for m in members:
      names = [rec.to_text() for rec in self.get_records(m.vm.name)]
      if len(names) == 1 and names[0] == m.vm.ip_address:
        log.msg("Member {} A record matches {}".format(m.vm.name, m.vm.ip_address))
      else:
        log.err("Member {} A record doesn't match {}, resolved: {}".format(
          m.vm.name, m.vm.ip_address, names))
        try:
          if resolve_errors and self.replace_fwd(m.vm.name, m.vm.ip_address):
            log.msg("Replaced forward record {} as A in {}".format(m.vm.name, m.vm.ip_address))
        except Exception as e:
          log.msg("Failed to replace forward record {} as A in {}, error was".format(
            m.vm.name, m.vm.ip_address, e))
    #
    # Return the log, the contains_errors can be used to create a tracking defect ticket
    #
    return log