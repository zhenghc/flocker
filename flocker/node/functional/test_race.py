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
