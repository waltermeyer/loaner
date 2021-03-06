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

"""Frontend handler test cases."""

import webtest

from loaner.web_app import main as webapp_main
from loaner.web_app.backend.testing import loanertest


class HandlerTestCase(loanertest.TestCase):
  """Base test case class for Request Handlers."""

  def setUp(self):
    super(HandlerTestCase, self).setUp()
    self.testapp = webtest.TestApp(webapp_main.web_app)


def main():
  loanertest.main()


if __name__ == '__main__':
  loanertest.main()
