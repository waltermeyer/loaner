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

"""Tests for backend.clients.directory."""

from googleapiclient import errors
import mock

from loaner.web_app.backend.clients import directory
from loaner.web_app.backend.testing import loanertest


class FakeResponse(object):
  """The response object provided during a HttpError."""

  def __init__(self, reason, status):
    self.reason = reason
    self.status = status


class DirectoryClientTest(loanertest.TestCase):
  """Test for the Directory API Client library."""

  def setUp(self):  # pylint: disable=arguments-differ
    super(DirectoryClientTest, self).setUp()
    self.patcher_build = mock.patch('__main__.directory.build')
    self.patcher_creds = mock.patch(
        '__main__.directory.service_account.Credentials')
    self.mock_build = self.patcher_build.start()
    self.mock_creds = self.patcher_creds.start()
    self.addCleanup(self.patcher_build.stop)
    self.addCleanup(self.patcher_creds.stop)
    self.user_email = loanertest.USER_EMAIL
    self.device_id = 'unique_id'
    self.org_unit_path = 'org_unit_path'
    self.org_unit_name = 'newUnit'
    self.org_unit_description = 'This is a test description'
    self.parent_org_unit_path = 'Grab n Go/Default'
    self.serial_number = 'serial_number'
    self.group_key = 'new_group_key'
    self.fake_org_unit = {
        'name': 'Default',
        'orgUnitPath': '/Grab n Go/Default',
        'orgUnitId': 'id:96bcx6hg424f4g3',
        'parentOrgUnitPath': '/Grab n Go',
        'parentOrgUnitId': 'id:12gfd5xf313d3f3',
        'blockInheritance': False
    }
    self.new_org_unit = {
        'kind': 'admin#directory#orgUnit',
        'etag': '\"YDi4yMhknQ5-kwx7j9TvuWFtG36H/Dr2t19CyYA1ek28eR05U9ZBjG4\"',
        'name': 'newUnit',
        'description': 'This is a test description',
        'orgUnitPath': '/Grab n Go/Default/newUnit',
        'orgUnitId': 'id:96bc49gur24f4g3',
        'parentOrgUnitPath': '/Grab n Go/Default',
        'parentOrgUnitId': 'id:g9el45xf313d3f3',
        'blockInheritance': False
    }
    self.mock_client = self.mock_build.return_value

  def test_create_directory_api_client(self):
    directory.DirectoryApiClient(user_email=self.user_email)
    assert self.mock_creds.from_service_account_file.called

  def test_create_directory_api_client_no_auth(self):
    with self.assertRaises(directory.UnauthorizedUserError):
      directory.DirectoryApiClient()

  def test_get_chrome_device(self):
    mock_chromeosdevices = mock.Mock()
    self.mock_client.chromeosdevices = mock_chromeosdevices

    mock_get = mock.Mock()
    mock_chromeosdevices.return_value.get = mock_get

    mock_execute = mock.Mock()
    mock_execute.return_value = loanertest.TEST_DIR_DEVICE1
    mock_get.return_value.execute = mock_execute

    directory_client = directory.DirectoryApiClient(user_email=self.user_email)
    self.assertEqual(
        loanertest.TEST_DIR_DEVICE1,
        directory_client.get_chrome_device(self.device_id))

  def test_get_chrome_device_fail(self):

    def raise_error():
      raise errors.HttpError(FakeResponse('Does not exist', 404), 'NOT USED.')

    self.mock_client.chromeosdevices.side_effect = raise_error

    directory_client = directory.DirectoryApiClient(user_email=self.user_email)
    self.assertEqual(None, directory_client.get_chrome_device(self.device_id))

  @mock.patch('__main__.directory.logging.error')
  def test_get_chrome_device_error(self, mock_log_error):

    def raise_error():
      raise errors.HttpError(FakeResponse('Does not exist', 400), 'NOT USED.')

    self.mock_client.chromeosdevices.side_effect = raise_error

    with self.assertRaises(directory.DirectoryRPCError):
      directory_client = directory.DirectoryApiClient(
          user_email=self.user_email)
      directory_client.get_chrome_device(self.device_id)
      mock_log_error.assert_called_once_with('You lose')

  def test_get_chrome_device_by_serial(self):
    mock_chromeosdevices = mock.Mock()
    self.mock_client.chromeosdevices = mock_chromeosdevices

    mock_list = mock.Mock()
    mock_chromeosdevices.return_value.list = mock_list

    mock_execute = mock.Mock()
    mock_list.return_value.execute = mock_execute

    mock_execute.return_value = {
        'chromeosdevices': [loanertest.TEST_DIR_DEVICE1]
    }

    directory_client = directory.DirectoryApiClient(user_email=self.user_email)
    self.assertEqual(
        loanertest.TEST_DIR_DEVICE1,
        directory_client.get_chrome_device_by_serial(
            self.serial_number))

  @mock.patch('__main__.directory.logging.error')
  def test_get_chrome_device_by_serial_rpc_error(self, mock_log_error):

    def raise_error():
      raise errors.HttpError(FakeResponse('Does not exist', 400), 'NOT USED.')

    self.mock_client.chromeosdevices.side_effect = raise_error

    with self.assertRaises(directory.DirectoryRPCError):
      directory_client = directory.DirectoryApiClient(
          user_email=self.user_email)
      directory_client.get_chrome_device_by_serial(self.serial_number)
      mock_log_error.assert_called_once_with('You lose')

  @mock.patch('__main__.directory.logging.error')
  def test_get_chrome_device_by_serial_key_error(self, mock_log_error):

    self.mock_client.chromeosdevices.side_effect = KeyError

    with self.assertRaisesRegexp(
        directory.DeviceDoesNotExistError,
        directory._NO_DEVICE_MSG % self.serial_number):
      directory_client = directory.DirectoryApiClient(
          user_email=self.user_email)
      directory_client.get_chrome_device_by_serial(self.serial_number)
      mock_log_error.assert_called_once_with(
          directory._NO_DEVICE_MSG, self.serial_number)

  def test_get_org_unit(self):
    mock_orgunits = mock.Mock()
    self.mock_client.orgunits = mock_orgunits

    mock_get = mock.Mock()
    mock_orgunits.return_value.get = mock_get

    mock_execute = mock.Mock()
    mock_execute.return_value = self.fake_org_unit
    mock_get.return_value.execute = mock_execute

    directory_client = directory.DirectoryApiClient(user_email=self.user_email)
    self.assertEqual(
        self.fake_org_unit, directory_client.get_org_unit(self.org_unit_path))

  def test_get_org_unit_fail(self):

    def raise_error():
      raise errors.HttpError(FakeResponse('Does not exist', 404), 'NOT USED.')

    self.mock_client.orgunits.side_effect = raise_error

    directory_client = directory.DirectoryApiClient(user_email=self.user_email)
    self.assertEqual(None, directory_client.get_org_unit(self.org_unit_path))

  @mock.patch('__main__.directory.logging.error')
  def test_get_org_unit_error(self, mock_log_error):

    def raise_error():
      raise errors.HttpError(FakeResponse('Does not exist', 400), 'NOT USED.')

    self.mock_client.orgunits.side_effect = raise_error

    with self.assertRaises(directory.DirectoryRPCError):
      directory_client = directory.DirectoryApiClient(
          user_email=self.user_email)
      directory_client.get_org_unit(self.org_unit_path)
      mock_log_error.assert_called_once_with('You lose')

  @mock.patch('__main__.directory.logging.info')
  def test_insert_org_unit(self, mock_log_info):
    mock_orgunits = mock.Mock()
    self.mock_client.orgunits = mock_orgunits

    mock_insert = mock.Mock()
    mock_orgunits.return_value.insert = mock_insert

    mock_execute = mock.Mock()
    mock_execute.return_value = self.new_org_unit
    mock_insert.return_value.execute = mock_execute

    directory_client = directory.DirectoryApiClient(user_email=self.user_email)
    self.assertEqual(
        self.new_org_unit, directory_client.insert_org_unit(
            name=self.org_unit_name,
            parent_org_unit_path=self.parent_org_unit_path,
            description=self.org_unit_description))
    self.assertEqual(2, mock_log_info.call_count)

  @mock.patch('__main__.directory.logging.error')
  def test_insert_org_unit_error(self, mock_log_error):

    def raise_error():
      raise errors.HttpError(FakeResponse('Does not exist', 400), 'NOT USED.')

    self.mock_client.orgunits.side_effect = raise_error

    with self.assertRaises(directory.DirectoryRPCError):
      directory_client = directory.DirectoryApiClient(
          user_email=self.user_email)
      directory_client.insert_org_unit(self.org_unit_name)
      mock_log_error.assert_called_once_with('You lose')

  @mock.patch('__main__.directory.logging.info')
  def test_move_chrome_device_org_unit(self, mock_log_info):
    mock_chromeosdevices = mock.Mock()
    self.mock_client.chromeosdevices = mock_chromeosdevices

    mock_move_devices_to_ou = mock.Mock()
    mock_chromeosdevices.return_value.moveDevicesToOu = mock_move_devices_to_ou

    mock_execute = mock.Mock()
    mock_move_devices_to_ou.return_value.execute = mock_execute

    directory_client = directory.DirectoryApiClient(user_email=self.user_email)
    directory_client.move_chrome_device_org_unit(
        self.device_id, self.org_unit_path)
    mock_execute.assert_called_once()
    self.assertEqual(2, mock_log_info.call_count)

  @mock.patch('__main__.directory.logging.error')
  def test_move_chrome_device_org_unit_error(self, mock_log_error):

    def raise_error():
      raise errors.HttpError(FakeResponse('Does not exist', 400), 'NOT USED.')

    self.mock_client.chromeosdevices.side_effect = raise_error

    with self.assertRaises(directory.DirectoryRPCError):
      directory_client = directory.DirectoryApiClient(
          user_email=self.user_email)
      directory_client.move_chrome_device_org_unit(
          self.device_id, self.org_unit_path)
      mock_log_error.assert_called_once_with('You lose')

  @mock.patch('__main__.directory.logging.info')
  def test_disable_chrome_device(self, mock_log_info):
    mock_chromeosdevices = mock.Mock()
    self.mock_client.chromeosdevices = mock_chromeosdevices

    mock_action = mock.Mock()
    mock_chromeosdevices.return_value.action = mock_action

    mock_execute = mock.Mock()
    mock_action.return_value.execute = mock_execute

    directory_client = directory.DirectoryApiClient(user_email=self.user_email)
    directory_client.disable_chrome_device(self.device_id)
    mock_execute.assert_called_once()
    self.assertEqual(2, mock_log_info.call_count)

  @mock.patch('__main__.directory.logging.error')
  def test_disable_chrome_device_error(self, mock_log_error):

    def raise_error():
      raise errors.HttpError(FakeResponse('Does not exist', 400), 'NOT USED.')

    self.mock_client.chromeosdevices.side_effect = raise_error

    with self.assertRaises(directory.DirectoryRPCError):
      directory_client = directory.DirectoryApiClient(
          user_email=self.user_email)
      directory_client.disable_chrome_device(self.device_id)
      mock_log_error.assert_called_once_with('You lose')

  def test_disable_already_diabled_chrome_device_error(self):

    def raise_error():
      raise errors.HttpError(FakeResponse('Does not exist', 412), 'NOT USED.')

    self.mock_client.chromeosdevices.side_effect = raise_error

    with self.assertRaises(directory.DeviceAlreadyDisabledError):
      directory_client = directory.DirectoryApiClient(
          user_email=self.user_email)
      directory_client.disable_chrome_device(self.device_id)

  @mock.patch('__main__.directory.logging.info')
  def test_reenable_chrome_device(self, mock_log_info):
    mock_chromeosdevices = mock.Mock()
    self.mock_client.chromeosdevices = mock_chromeosdevices

    mock_action = mock.Mock()
    mock_chromeosdevices.return_value.action = mock_action

    mock_execute = mock.Mock()
    mock_action.return_value.execute = mock_execute

    directory_client = directory.DirectoryApiClient(user_email=self.user_email)
    directory_client.reenable_chrome_device(self.device_id)
    mock_execute.assert_called_once()
    self.assertEqual(2, mock_log_info.call_count)

  @mock.patch('__main__.directory.logging.error')
  def test_reenable_chrome_device_error(self, mock_log_error):

    def raise_error():
      raise errors.HttpError(FakeResponse('Does not exist', 400), 'NOT USED.')

    self.mock_client.chromeosdevices.side_effect = raise_error

    with self.assertRaises(directory.DirectoryRPCError):
      directory_client = directory.DirectoryApiClient(
          user_email=self.user_email)
      directory_client.reenable_chrome_device(self.device_id)
      mock_log_error.assert_called_once_with('You lose')

  def test_users_in_group(self):
    mock_members = mock.Mock()
    self.mock_client.members = mock_members

    mock_list = mock.Mock()
    mock_members.return_value.list = mock_list

    mock_execute = mock.Mock()
    fake_members = {'members': [], 'nextPageToken': 'pageToken'}
    mock_execute.return_value = fake_members
    mock_list.return_value.execute = mock_execute

    directory_client = directory.DirectoryApiClient(user_email=self.user_email)
    self.assertEqual(
        fake_members, directory_client.users_in_group(self.group_key))

  @mock.patch('__main__.directory.logging.error')
  def test_users_in_group_url_error(self, mock_log_error):

    def raise_error():
      raise errors.HttpError(FakeResponse('Does not exist', 400), 'NOT USED.')

    self.mock_client.members.side_effect = raise_error

    with self.assertRaises(directory.DirectoryRPCError):
      directory_client = directory.DirectoryApiClient(
          user_email=self.user_email)
      directory_client.users_in_group(self.group_key)
      mock_log_error.assert_called_once_with('You lose')

  def test_user_name(self):
    mock_users = mock.Mock()
    self.mock_client.users = mock_users

    mock_get = mock.Mock()
    mock_users.return_value.get = mock_get

    mock_execute = mock.Mock()
    fake_given_name = {'name': {'givenName': 'Dare Devil'}}
    mock_execute.return_value = fake_given_name
    mock_get.return_value.execute = mock_execute

    directory_client = directory.DirectoryApiClient(user_email=self.user_email)
    self.assertEqual(
        fake_given_name['name']['givenName'],
        directory_client.given_name(loanertest.USER_EMAIL))

  @mock.patch('__main__.directory.logging.error')
  def test_user_name_url_error(self, mock_log_error):

    def raise_error():
      raise errors.HttpError(FakeResponse('Does not exist', 400), 'NOT USED.')

    self.mock_client.users.side_effect = raise_error

    with self.assertRaises(directory.DirectoryRPCError):
      directory_client = directory.DirectoryApiClient(
          user_email=self.user_email)
      directory_client.given_name(loanertest.USER_EMAIL)
      mock_log_error.assert_called_once_with('You lose')

  @mock.patch('__main__.directory.logging.info')
  def test_user_name_key_error(self, mock_log_info):

    def raise_error():
      raise KeyError('No given name.')

    self.mock_client.users.side_effect = raise_error

    with self.assertRaises(directory.GivenNameDoesNotExistError):
      directory_client = directory.DirectoryApiClient(
          user_email=self.user_email)
      directory_client.given_name(loanertest.USER_EMAIL)
      mock_log_info.assert_called_once()


if __name__ == '__main__':
  loanertest.main()
