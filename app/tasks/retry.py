from datetime import datetime
from time import sleep
import logging

class RetryException(Exception):
  pass

class retry(object):
  """
  Decorator that allows functions to be retried if an exception is raised
  """
  def __init__(self,
               initial_delay_seconds=0,
               delay_seconds=0,
               max_attempts=None,
               delay_multiplier=None,
               exception=Exception,
               max_lifetime_seconds=None):
    """
    :param initial_delay_seconds: seconds to wait before initial attempt
    :param delay_seconds: seconds to wait before retrying
    :param max_attempts: max number of attempts to make
    :param delay_multiplier: multiplier to delay_seconds applied after each failure
    :param exception: the exception that will allow a retry attempt
    :param max_lifetime_seconds: limits the duration allowed for retries
    :return:
    """
    self.initial_delay_seconds = initial_delay_seconds
    self.delay_seconds = delay_seconds
    self.max_attempts = max_attempts
    self.delay_multiplier = delay_multiplier
    self.exception = exception
    self.max_lifetime_seconds = max_lifetime_seconds
  def __call__(self, f):
    def wrapped_f(*args, **kwargs):
      logging.info("rety function {}() called with "
                   "initial delay: {}, "
                   "delay: {}, "
                   "max attempts: {}, "
                   "delay multiplier: {}, "
                   "excpetion: {}, "
                   "lifetime: {}".format(f.__name__,
                                         self.initial_delay_seconds,
                                         self.delay_seconds,
                                         self.max_attempts if self.max_attempts is None else 'unlimited',
                                         self.delay_multiplier,
                                         self.exception,
                                         self.max_lifetime_seconds if self.max_lifetime_seconds is None else 'unlimited'))
      start_time = datetime.utcnow()
      attempt_num = 1
      while self.max_attempts is None or attempt_num <= self.max_attempts:
        delay = None
        if attempt_num == 1:
          delay = 0 if self.initial_delay_seconds is None else self.initial_delay_seconds
        elif attempt_num ==  2 or self.delay_multiplier is None:
          delay = self.delay_seconds
        else:
          delay = self.delay_seconds * (self.delay_multiplier ** (attempt_num - 2))
        if self.max_lifetime_seconds is not None:
          now = datetime.utcnow()
          sec_elapsed_after_wait = (now - start_time).seconds
          if sec_elapsed_after_wait > self.max_lifetime_seconds:
            raise RetryException("Cannot wait to attempt try {}/{} as delay of {} "
                                 "would be {} seconds over our max lifetime of {} "
                                 "since we started at {} and it's now {}".format(
              attempt_num,
              self.max_attempts,
              delay,
              sec_elapsed_after_wait - self.max_lifetime_seconds,
              self.max_lifetime_seconds,
              start_time,
              now))
        sleep(delay)
        try:
          result = f(*args, **kwargs)
          logging.info("{} attempt {}/{} succeeded".format(
            f.__name__,
            attempt_num,
            self.max_attempts if self.max_attempts is not None else 'unlimited'))
          return result
        except self.exception as e:
          logging.warning("{} attempt {}/{} failed: {}".format(
            f.__name__,
            attempt_num,
            self.max_attempts if self.max_attempts is not None else 'unlimited',
            e))
          if self.max_attempts is not None and attempt_num == self.max_attempts:
            raise e
        finally:
          attempt_num += 1
      return f(*args, **kwargs)
    return wrapped_f