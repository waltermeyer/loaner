# Copyright 2018 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS-IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""A model representing a device."""

import collections
import datetime
import logging

from google.appengine.ext import deferred
from google.appengine.ext import ndb

from loaner.web_app import constants
from loaner.web_app.backend.clients import directory
from loaner.web_app.backend.lib import events
from loaner.web_app.backend.models import base_model
from loaner.web_app.backend.models import config_model

_GUEST_MODE_DISABLED_MSG = (
    'Cannot enable Guest mode because the administrator has disabled it.')
_DEVICE_NOT_ENROLLED_MSG = 'Device %s is not enrolled in the application.'
_DEVICE_DAMAGED_MSG = (
    'Unable to check Device %s into a shelf because it was reported damaged.')
_DIRECTORY_INFO_INCOMPLETE_MSG = (
    'The information retrieved from the directory API was incomplete, please '
    'try again later.')
_FAILED_TO_MOVE_DEVICE_MSG = 'Failed to move Device %s to OU %s because %s.'
_NOT_ASSIGNED_MSG = (
    "Can't perform action because Device isn't assigned to anyone.")
_ALREADY_DISABLED_MSG = (
    'This device is alread disabled, correcting the local status: %s.')
_UNASSIGNED_DEVICE = (
    'This action is not allowed because the device is not assigned.')


class Error(Exception):
  """Base class for exceptions."""


class AssignmentError(Error):
  """Error raised when assignment fails."""


class DeviceCreationError(Error):
  """Error raised when the app fails to create a device."""


class ExtendError(Error):
  """Error raised when you cannot extend a device's due date."""


class EnableGuestError(Error):
  """Error raised when the guest OU move fails."""


class GuestNotAllowedError(Error):
  """Error raised if someone attempts to enable guest but is not allowed."""


class DeviceIdentifierError(Error):
  """Raised when there is a problem getting a device using the supplied info."""


class DeviceNotEnrolledError(Error):
  """Raised when the device is not enrolled into the application."""


class UnableToMoveToShelfError(Error):
  """Raised when a device can not be moved into a shelf."""


class FailedToUnenrollError(Error):
  """Raised when a device failed to be unenrolled."""


class UnableToMoveToDefaultOUError(Error):
  """Raised when moving a device to the default OU fails."""


class ReturnDatesCalculationError(Error):
  """Raised when trying to calculate return dates to an unassigned device."""


class UnassignedDeviceError(Error):
  """Raised when a device is not assigned during an assignment error."""


ReturnDates = collections.namedtuple('ReturnDates', ['min', 'max', 'default'])


class Reminder(base_model.BaseModel):
  """Datastore model representing a seen reminder.

  Attributes:
    level: Int to indicate if a reminder is due, overdue, or massively overdue.
    time:  DateTimeProperty at which the Device's borrower was reminded.
    count: IntegerProperty that indicates the number of reminders seen.
  """
  level = ndb.IntegerProperty(required=True)
  time = ndb.DateTimeProperty()
  count = ndb.IntegerProperty()


class Device(base_model.BaseModel):
  """Datastore model representing a device.

  Attributes:
    serial_number: str, unique serial number used to identify the device.
    asset_tag: str, unique org-specific identifier for the device.
    enrolled: bool, indicates the enrollment status of the device.
    device_model: int, identifies the model name of the device.
    due_date: datetime, the date that device is due for return.
    last_know_healthy: datetime, the date to indicate the last known healthy
        status.
    shelf: ndb.key, The shelf key the device is placed on.
    assigned_user: str, The email of the user who is assigned to the device.
    assignment_date: datetime, The date the device was assigned to a user.
    current_ou: str, The current organizational unit the device belongs to.
    ou_change_date: datetime, The date the organizational unit was changed.
    locked: bool, indicates whether or not the device is locked.
    lost: bool, indicates whether or not the device is lost.
    mark_pending_return_date: datetime, The date a user marked device returned.
    chrome_device_id: str, a unique device ID.
    last_heartbeat: datetime, the date of the last time the device checked in.
    damaged: bool, indicates the if the device is damaged.
    damaged_reason: str, A string denoting the reason for being reported as
        damaged.
    last_reminder: Reminder, Level, time, and count of the last reminder
        the device had.
    next_reminder: Reminder, Level, time, and count of the next reminder.
  """
  serial_number = ndb.StringProperty(required=True)
  asset_tag = ndb.StringProperty()
  enrolled = ndb.BooleanProperty(default=True)
  device_model = ndb.StringProperty()
  due_date = ndb.DateTimeProperty()
  last_known_healthy = ndb.DateTimeProperty()
  shelf = ndb.KeyProperty(kind='Shelf')
  assigned_user = ndb.StringProperty()
  assignment_date = ndb.DateTimeProperty()
  current_ou = ndb.StringProperty()
  ou_changed_date = ndb.DateTimeProperty()
  locked = ndb.BooleanProperty(default=False)
  lost = ndb.BooleanProperty(default=False)
  mark_pending_return_date = ndb.DateTimeProperty()
  max_extend_date = ndb.DateTimeProperty()
  chrome_device_id = ndb.StringProperty()
  last_heartbeat = ndb.DateTimeProperty()
  damaged = ndb.BooleanProperty(default=False)
  damaged_reason = ndb.StringProperty()
  last_reminder = ndb.StructuredProperty(Reminder)
  next_reminder = ndb.StructuredProperty(Reminder)
  return_date = ndb.DateTimeProperty()

  @property
  def is_assigned(self):
    return bool(self.assigned_user)

  @property
  def is_on_shelf(self):
    return bool(self.shelf)

  @property
  def identifier(self):
    if config_model.Config.get('use_asset_tags'):
      return self.asset_tag or self.serial_number
    else:
      return self.serial_number

  @property
  def guest_enabled(self):
    return self.current_ou == constants.ORG_UNIT_DICT['GUEST']

  @classmethod
  def list_by_user(cls, user):
    """Returns a list of devices assigned to a user.

    Args:
      user: str, the user's email address.

    Returns:
      A query of devices assigned to the user.
    """
    return cls.query(cls.assigned_user == user).fetch()

  @classmethod
  def enroll(cls, serial_number, user_email, asset_tag=None):
    """Enrolls a new device.

    Args:
      serial_number: str, serial number of the device.
      user_email: str, email address of the user making the request.
      asset_tag: str, optional, asset tag of the device.

    Returns:
      The enrolled device object.

    Raises:
      DeviceCreationError: raised when moving the device's OU fails or when the
          directory API responds with incomplete information or if the device is
          not found in the directory API.
    """
    directory_client = directory.DirectoryApiClient(user_email)
    device = cls.get(serial_number=serial_number)
    now = datetime.datetime.utcnow()
    was_lost_or_locked = False

    if device:
      logging.info('Previous device found, re-enrolling.')

      if device.locked:
        was_lost_or_locked = True
        device.unlock(user_email)
      if device.lost:
        was_lost_or_locked = True
        device.lost = False

      try:
        device.move_to_default_ou(user_email=user_email)
      except UnableToMoveToDefaultOUError as err:
        raise DeviceCreationError(str(err))
      device.enrolled = True
      device.asset_tag = asset_tag
      device.last_known_healthy = now
      device.mark_pending_return_date = None
    else:
      try:
        dir_device = directory_client.get_chrome_device_by_serial(serial_number)
      except directory.DeviceDoesNotExistError as err:
        raise DeviceCreationError(str(err))

      if dir_device[
          directory.ORG_UNIT_PATH] != constants.ORG_UNIT_DICT['DEFAULT']:
        try:
          directory_client.move_chrome_device_org_unit(
              device_id=dir_device[directory.DEVICE_ID],
              org_unit_path=constants.ORG_UNIT_DICT['DEFAULT'])
        except directory.DirectoryRPCError as err:
          raise DeviceCreationError(
              _FAILED_TO_MOVE_DEVICE_MSG % (
                  serial_number, constants.ORG_UNIT_DICT['DEFAULT'],
                  str(err)))

      try:
        device = cls(
            serial_number=serial_number,
            asset_tag=asset_tag,
            device_model=dir_device.get(directory.MODEL),
            last_known_healthy=now,
            current_ou=constants.ORG_UNIT_DICT['DEFAULT'],
            ou_changed_date=now,
            chrome_device_id=dir_device[directory.DEVICE_ID])
      except KeyError:
        raise DeviceCreationError(_DIRECTORY_INFO_INCOMPLETE_MSG)

    logging.info('Enrolling device %s', serial_number)
    device.put()
    device.stream_to_bq(user_email, 'Enrolling device.')

    if was_lost_or_locked:
      events.raise_event('device_enroll_lost_or_locked', device=device)
    else:
      events.raise_event('device_enroll', device=device)
    return device

  def unenroll(self, user_email):
    """Unenrolls a device, removing it from the Grab n Go program.

    This moves the device to the root Chrome OU, however it does not change its
    losr or locked attributes, nor does it unlock it if it's locked (i.e.,
    disabled in the Directory API).

    Args:
      user_email: str, email address of the user making the request.

    Returns:
      The unenrolled device.

    Raises:
      FailedToUnenrollError: raised when moving the device's OU fails.
    """
    unenroll_ou = config_model.Config.get('unenroll_ou')
    directory_client = directory.DirectoryApiClient(user_email)
    try:
      directory_client.move_chrome_device_org_unit(
          device_id=self.chrome_device_id, org_unit_path=unenroll_ou)
    except directory.DirectoryRPCError as err:
      raise FailedToUnenrollError(
          _FAILED_TO_MOVE_DEVICE_MSG % (self.identifier, unenroll_ou, str(err)))
    self.enrolled = False
    self.due_date = None
    self.shelf = None
    self.assigned_user = None
    self.assignment_date = None
    self.current_ou = unenroll_ou
    self.ou_changed_date = datetime.datetime.utcnow()
    self.mark_pending_return_date = None
    self.last_reminder = None
    self.next_reminder = None

    self.put()
    self.stream_to_bq(user_email, 'Unenrolling device.')
    events.raise_event('device_unenroll', device=self)
    return self

  @classmethod
  def create_unenrolled(cls, device_id, user_email):
    """Creates a Device but leave it unenrolled from the Grab n Go program.

    Args:
      device_id: str, a Chrome Device ID to pass to the directory API.
      user_email: str, email address of the user making the request.

    Returns:
      The newly created device.

    Raises:
      DeviceCreationError: if the Directory API doesn't find this device in the
        org or the info retrieved from the Directory API is incomplete.
    """
    directory_client = directory.DirectoryApiClient(user_email)
    directory_info = directory_client.get_chrome_device(device_id)
    if not directory_info:
      raise DeviceCreationError('Device ID not found in org.')
    try:
      device = cls(
          serial_number=directory_info[directory.SERIAL_NUMBER],
          enrolled=False,
          device_model=directory_info.get(directory.MODEL),
          current_ou=directory_info[directory.ORG_UNIT_PATH],
          chrome_device_id=directory_info[directory.DEVICE_ID])
    except KeyError:
      raise DeviceCreationError(_DIRECTORY_INFO_INCOMPLETE_MSG)

    device.put()
    return device

  @classmethod
  def get(
      cls, asset_tag=None, chrome_device_id=None, serial_number=None,
      urlkey=None, unknown_identifier=None):
    """Retrieves a device object using one of several device identifiers.

    Args:
      asset_tag: str, the asset tag of the device.
      chrome_device_id: str, the Chrome device ID of a device.
      serial_number: str, the serial number of a device.
      urlkey: str, the URL-safe key of a device.
      unknown_identifier: str, either an asset tag or serial number of the
          device, and this function will attempt both.

    Returns:
      A device model, or None if one cannot be found.

    Raises:
      DeviceIdentifierError: if there is no device identifier supplied, or if an
          invalid URL-safe key is supplied.
    """
    if asset_tag:
      return cls.query(cls.asset_tag == asset_tag).get()
    elif chrome_device_id:
      return cls.query(cls.chrome_device_id == chrome_device_id).get()
    elif serial_number:
      return cls.query(cls.serial_number == serial_number).get()
    elif urlkey:
      # Decoding a malformed URL-safe key can fail in multiple ways.
      try:
        return ndb.Key(urlsafe=urlkey).get()
      except Exception as e:  # pylint: disable=broad-except
        raise DeviceIdentifierError(
            '{error_type} Exception raised for Device URL-safe key ({urlkey}): '
            '{error}'.format(
                error_type=str(type(e)), urlkey=urlkey, error=str(e)))
    elif unknown_identifier:
      return (
          cls.query(cls.serial_number == unknown_identifier).get() or
          cls.query(cls.asset_tag == unknown_identifier).get())
    else:
      raise DeviceIdentifierError('No identifier supplied to get device.')

  @classmethod
  def list_devices(
      cls, enrolled=True, keys_only=False, page_size=100, next_cursor=None,
      **kwargs):
    """Returns a list of devices using given filters.

    Args:
      enrolled: bool, set True if only active devices should be queried,
          else False if only inactive.
      keys_only: bool, set True if only device keys should be returned.
      page_size: int, the number of devices to query for.
      next_cursor: datastore_query.Cursor, set when next page of results need to
          be queried.
      **kwargs: in which each kwarg name is the name of a Device property by
          which to filter the query, and its value is the filter value (str,
          int, etc.).

    Returns:
      A tuple consisting of a list of device keys, Cursor, and a bool.
    """
    # pylint: disable=g-explicit-bool-comparison
    query = cls.query(cls.enrolled == enrolled)
    # pylint: enable=g-explicit-bool-comparison
    for filters, filter_values in kwargs.items():
      if not isinstance(filter_values, (list, tuple)):
        filter_values = (filter_values,)
      for value in filter_values:
        query = query.filter(ndb.GenericProperty(filters) == value)
    return query.fetch_page(
        keys_only=keys_only, page_size=page_size, start_cursor=next_cursor)

  def calculate_return_dates(self):
    """Calculates minimum, maximum, and default return dates for a loan.

    Returns:
      A ReturnDates NamedTuple of datetimes.

    Raises:
      ReturnDatesCalculationError: When trying to calculate return dates for a
          device that has not been assigned.
    """
    if not self.is_assigned:
      raise ReturnDatesCalculationError(_NOT_ASSIGNED_MSG)
    loan_duration = config_model.Config.get(
        'loan_duration')
    min_loan_duration = config_model.Config.get(
        'minimum_loan_duration')
    max_loan_duration = config_model.Config.get(
        'maximum_loan_duration')
    min_loan_date = self.assignment_date + datetime.timedelta(
        days=min_loan_duration)
    default_date = self.assignment_date + datetime.timedelta(days=loan_duration)
    max_loan_date = self.assignment_date + datetime.timedelta(
        days=max_loan_duration)

    return ReturnDates(min_loan_date, max_loan_date, default_date)

  def lock(self, user_email):
    """Disables a device via the Directory API.

    Args:
      user_email: string, email address of the user making the request.
    """
    logging.info(
        'Contacting Directory to lock (disable) Device %s.',
        self.identifier)
    client = directory.DirectoryApiClient(user_email)
    try:
      client.disable_chrome_device(self.chrome_device_id)
    except directory.DeviceAlreadyDisabledError as err:
      logging.error(_ALREADY_DISABLED_MSG, err)
    else:
      self.stream_to_bq(user_email, 'Disabling device.')
    self.locked = True
    self.put()

  def unlock(self, user_email):
    """Re-enables a device via the Directory API.

    Args:
      user_email: str, email address of the user making the request.
    """
    logging.info(
        'Contacting Directory to unlock (re-enable) Device %s.',
        self.identifier)
    client = directory.DirectoryApiClient(user_email)
    client.reenable_chrome_device(self.chrome_device_id)
    self.locked = False
    self.move_to_default_ou(user_email=user_email)
    self.stream_to_bq(user_email, 'Re-enabling disabled device.')

  def loan_assign(self, user_email):
    """Assigns a device to a user.

    Args:
      user_email: str, email address of the user to whom the device should be
          assigned.

    Returns:
      The key of the datastore record.

    Raises:
      AssignmentError: if the device is not enrolled.
    """
    if not self.enrolled:
      raise AssignmentError('Cannot assign an unenrolled device.')

    if self.assigned_user and self.assigned_user != user_email:
      self._loan_return(user_email)

    self.assigned_user = user_email
    self.assignment_date = datetime.datetime.utcnow()
    self.mark_pending_return_date = None
    self.shelf = None
    self.due_date = self.calculate_return_dates().default
    self.move_to_default_ou(user_email=user_email)
    self.put()
    self.stream_to_bq(user_email, 'Beginning new loan.')
    events.raise_event('device_loan_assign', device=self)
    return self.key

  def resume_loan(self, user_email, message='Resuming loan.'):
    """Resumes a loan if it has been marked pending return.

    Args:
      user_email: str, email address of the user initiating the resume.
      message: str, the optional string to stream to bigquery.
    """
    if self.mark_pending_return_date:
      self.mark_pending_return_date = None
      self.put()
      self.stream_to_bq(user_email, message)

  def loan_resumes_if_late(self, user_email):
    """Resumes a loan on a device if it was marked returned, but later used.

    This allows a user who has marked their device returned to keep using it
    for the return_grace_period, but beyond that it restores the loan, with any
    ongoing reminders and consequences that entails.

    Args:
      user_email: str, email address of the user initiating the return.
    """
    if self.mark_pending_return_date:
      time_since = datetime.datetime.utcnow() - self.mark_pending_return_date
      if time_since.total_seconds() / 60.0 > config_model.Config.get(
          'return_grace_period'):
        self.resume_loan(
            user_email, message='Resuming loan, since use continued.')

  def loan_extend(self, user_email, extend_date_time):
    """Requests an extension to the provided date.

    Args:
      user_email: str, user_email of the user requesting the extension.
      extend_date_time: DateTime, the requested date to extend to.

    Raises:
      ExtendError: If the date is out of an acceptable range.
      UnassignedDeviceError: if the device is not assigned, guest mode should
          not be allowed.
    """
    if not self.is_assigned:
      raise UnassignedDeviceError(_UNASSIGNED_DEVICE)
    extend_date = extend_date_time.date()
    if extend_date < datetime.date.today():
      raise ExtendError('Extension date cannot be in the past.')
    return_dates = self.calculate_return_dates()
    if (return_dates.min.date() <= extend_date) and (
        extend_date <= return_dates.max.date()):
      self.due_date = datetime.datetime.combine(
          extend_date, return_dates.default.time())
    else:
      raise ExtendError('Extension date outside allowable date range.')
    self.put()
    self.stream_to_bq(user_email, 'Extending loan.')

  def _loan_return(self, user_email):
    """Returns a device in a loan.

    Args:
      user_email: str, user_email of the user initiating the return.

    Returns:
      The key of the datastore record.
    """
    events.raise_event('device_loan_return', device=self)
    if self.lost:
      self.lost = False
    if self.locked:
      self.unlock(user_email)
    self.assigned_user = None
    self.assignment_date = None
    self.due_date = None
    self.mark_pending_return_date = None
    self.move_to_default_ou(user_email=user_email)
    self.last_reminder = None
    self.next_reminder = None
    self.put()
    self.stream_to_bq(user_email, 'Marking device as returned.')
    return self.key

  def record_heartbeat(self):
    """Records a heartbeat for a device."""
    now = datetime.datetime.utcnow()
    self.last_heartbeat = now
    self.last_known_healthy = now
    self.put()

  def mark_pending_return(self, user_email):
    """Marks a device as returned, as reported by the user.

    Args:
      user_email: str, The email of the acting user.

    Raises:
      UnassignedDeviceError: if the device is not assigned, guest mode should
          not be allowed.
    """
    if not self.is_assigned:
      raise UnassignedDeviceError(_UNASSIGNED_DEVICE)
    self.mark_pending_return_date = datetime.datetime.utcnow()
    self.move_to_default_ou(user_email=user_email)
    self.stream_to_bq(user_email, 'Marking device as Pending Return.')
    self.put()

  def set_last_reminder(self, reminder_level):
    """Records the last_reminder for a loaned device, overwriting existing one.

    Args:
      reminder_level: int, the level of the reminder, matching the reminder
          rule's reminder_level.
    """
    count = 0
    if self.last_reminder and self.last_reminder.level == reminder_level:
      count = self.last_reminder.count or 0
    self.last_reminder = Reminder(
        level=reminder_level, time=datetime.datetime.utcnow(), count=count + 1)
    self.put()

  def set_next_reminder(self, reminder_level, delay_delta):
    """Sets the next_reminder for a loaned device, overwriting existing one.

    Args:
      reminder_level: int, the level of the reminder, matching the reminder
          rule's reminder_level.
      delay_delta: datetime.timedelta, noting time to wait until the reminder
          should happen, which this method will record as a UTC datetime.
    """
    reminder_time = datetime.datetime.utcnow() + delay_delta
    self.next_reminder = Reminder(level=reminder_level, time=reminder_time)
    self.put()

  def mark_damaged(self, user_email, damaged_reason=None):
    """Marks a device as damaged.

    Args:
      user_email: string, the user that marked the device as damaged.
      damaged_reason: string, the reason the device is considered damaged.
    """
    if not damaged_reason:
      damaged_reason = 'No reason provided'
    self.damaged = True
    self.damaged_reason = damaged_reason
    self.move_to_default_ou(user_email=user_email)
    self.stream_to_bq(
        user_email, 'Marking device as damaged, reason: {reason}'.format(
            reason=damaged_reason))
    self.put()

  def mark_lost(self, user_email):
    """Marks a device as lost.

    Args:
      user_email: str, The email of the acting user.
    """
    self.lost = True
    self.assigned_user = None
    self.assignment_date = None
    self.due_date = None
    self.last_reminder = None
    self.next_reminder = None
    self.move_to_default_ou(user_email=user_email)
    self.lock(user_email)
    self.stream_to_bq(user_email, 'Marking device lost and locking it.')

  def enable_guest_mode(self, user_email):
    """Moves a device into guest mode if allowed.

    Args:
      user_email: str, The email of the acting user.

    Raises:
      GuestNotAllowedError: when the allow_guest_mode config is not True.
      EnableGuestError: if there is an RPC error in the Directory API, or the
          allow_guest_mode setting is not True.
      UnassignedDeviceError: if the device is not assigned, guest mode should
          not be allowed.
    """
    if not self.is_assigned:
      raise UnassignedDeviceError(_UNASSIGNED_DEVICE)
    if config_model.Config.get('allow_guest_mode'):
      directory_client = directory.DirectoryApiClient(user_email)
      guest_ou = constants.ORG_UNIT_DICT['GUEST']

      try:
        directory_client.move_chrome_device_org_unit(
            device_id=self.chrome_device_id,
            org_unit_path=guest_ou)
      except directory.DirectoryRPCError as err:
        raise EnableGuestError(str(err))
      else:
        self.current_ou = guest_ou
        self.ou_changed_date = datetime.datetime.utcnow()
        self.stream_to_bq(user_email, 'Moving device into Guest Mode.')
        self.put()
        if config_model.Config.get('timeout_guest_mode'):
          countdown = datetime.timedelta(
              hours=config_model.Config.get(
                  'guest_mode_timeout_in_hours')).total_seconds()
          deferred.defer(
              self._disable_guest_mode, user_email, _countdown=countdown)
    else:
      raise GuestNotAllowedError(_GUEST_MODE_DISABLED_MSG)

  def _disable_guest_mode(self, user_email):
    """Moves a device back to the default OU if still assigned.

    Args:
      user_email: str, The email of the acting user.
    """
    if self.assigned_user == user_email:
      self.move_to_default_ou(user_email=user_email)
      self.put()

  def move_to_default_ou(self, user_email):
    """Corrects the current ou to be default during user actions.

    Args:
      user_email: str, The email of the acting user.
    Raises:
      UnableToMoveToDefaultOUError: when the directory api call fails to move
          the device into the default OU.
    """
    if self.current_ou != constants.ORG_UNIT_DICT['DEFAULT']:
      directory_client = directory.DirectoryApiClient(user_email=user_email)

      try:
        directory_client.move_chrome_device_org_unit(
            device_id=self.chrome_device_id,
            org_unit_path=constants.ORG_UNIT_DICT['DEFAULT'])
      except directory.DirectoryRPCError as err:
        raise UnableToMoveToDefaultOUError(
            _FAILED_TO_MOVE_DEVICE_MSG % (
                self.identifier, constants.ORG_UNIT_DICT['DEFAULT'], str(err)))
      else:
        self.current_ou = constants.ORG_UNIT_DICT['DEFAULT']
        self.ou_changed_date = datetime.datetime.utcnow()

  def device_audit_check(self):
    """Checks a device to make sure it passes all prechecks for audit.

    Raises:
      DeviceNotEnrolledError: when a device is not enrolled in the application.
      UnableToMoveToShelfError: when a deivce can not be checked into a shelf.
    """
    if not self.enrolled:
      raise DeviceNotEnrolledError(_DEVICE_NOT_ENROLLED_MSG % self.identifier)
    if self.damaged:
      raise UnableToMoveToShelfError(_DEVICE_DAMAGED_MSG % self.identifier)

  def move_to_shelf(self, shelf, user_email):
    """Checks a device into a shelf.

    Args:
      shelf: shelf_model.Shelf obj, the shelf to check device into.
      user_email: str, the email of the user taking the action.

    Raises:
      UnableToMoveToShelfError: when a deivce can not be checked into a shelf.
    """
    if not shelf.enabled:
      raise UnableToMoveToShelfError(
          'Unable to check device {} to shelf. Shelf {} is not '
          'active.'.format(self.identifier, shelf.location))
    devices_on_shelf_count = len(self.list_devices(shelf=shelf.key))
    if devices_on_shelf_count >= shelf.capacity:
      raise UnableToMoveToShelfError(
          'Unable to check device {} to shelf. The shelf {} has '
          'reached capacity. Shelf capactiy: {} Current shelf capacity: '
          '{}'.format(
              self.serial_number, shelf.location, shelf.capacity,
              devices_on_shelf_count))
    logging.info(
        'Checking device %s into shelf %s.', self.identifier, shelf.location)
    self.shelf = shelf.key
    self.last_known_healthy = datetime.datetime.utcnow()
    self._loan_return(user_email=user_email)
    self.stream_to_bq(
        user_email, 'Placing device: {} on shelf: {}'.format(
            self.identifier, shelf.location))

  def remove_from_shelf(self, shelf, user_email):
    """Removes a device's associated shelf.

    Args:
      shelf: shelf_model.Shelf obj, the shelf to remove device from.
      user_email: str, the email of the user taking the action.
    """
    if self.shelf:
      if self.shelf.get().location is shelf.location:
        self.shelf = None
        self.put()
        self.stream_to_bq(
            user_email, 'Removing device: {} from shelf: {}'.format(
                self.identifier, shelf.location))
