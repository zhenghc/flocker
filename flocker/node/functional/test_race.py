# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests to reproduce Docker race conditions.

Requirements:
 * https://github.com/docker/docker-py

Tests may only fail when repeated.

For example, using `trial`:

  $ trial --until-failure test_race.py
  ...

  Test Pass 7
  flocker.node.functional.test_race
    DockerClientTests
      test_add_and_remove ...                                             [ERROR]

  ===============================================================================
  [ERROR]
  Traceback (most recent call last):
    File "/usr/lib64/python2.7/unittest/case.py", line 369, in run
      testMethod()
    File "/vagrant/flocker/node/functional/test_race.py", line 25, in test_add_and_remove
      client.stop(container=name)
    File "/home/vagrant/.virtualenvs/940/lib/python2.7/site-packages/docker/client.py", line 904, in stop
      self._raise_for_status(res)
    File "/home/vagrant/.virtualenvs/940/lib/python2.7/site-packages/docker/client.py", line 88, in _raise_for_status
      raise errors.APIError(e, response, explanation=explanation)
  docker.errors.APIError: 500 Server Error: Internal Server Error ("Cannot stop container 464635515479: no such process")

  flocker.node.functional.test_race.DockerClientTests.test_add_and_remove
  -------------------------------------------------------------------------------
"""

from random import random
from unittest import TestCase
from docker import Client

BASE_DOCKER_API_URL = u'unix://var/run/docker.sock'


def random_name():
    """Return a short, random name.

    :return name: A random ``unicode`` name.
    """
    return u"%d" % (int(random() * 1e12),)


class DockerClientTests(TestCase):
    def test_add_and_remove(self):
        """
        An added container can be removed without an error.
        """
        client = Client(version="1.15", base_url=BASE_DOCKER_API_URL)
        name = random_name()
        client.create_container(name=name, image=u"busybox")
        client.start(container=name)
        client.stop(container=name)
        client.remove_container(container=name)
