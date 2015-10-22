from random import randrange
import time

from twisted.internet import reactor
from twisted.internet.task import LoopingCall, deferLater

from twisted.web.client import getPage
from twisted.trial.unittest import TestCase

from flocker.common import gather_deferreds


def url_requester():
    while True:
        url = "http://localhost:8080?{}".format(randrange(10 ** 6))
        yield getPage(url)


class RateMeasurer(object):
    rate = 0
    _five_second_count = 0
    _last_time = 0

    def new_sample(self):
        now = int(time.time())
        if now - self._last_time > 5:
            self.rate = self._five_second_count / 5
            self._last_time = now
            self._five_second_count = 0
        self._five_second_count += 1


class LoadGenerator(object):
    def __init__(self, url_requester, rate_measurer, req_per_sec):
        self.url_requester = url_requester
        self._rate_measurer = rate_measurer

        def sample_and_return(result):
            self._rate_measurer.new_sample()
            return result

        def request_and_measure():
            for d in url_requester:
                d.addCallback(sample_and_return)
                yield d

        self.url_requester = request_and_measure()
        self.req_per_sec = req_per_sec
        self._loops = []
        self._starts = []

    def start(self):
        for i in range(self.req_per_sec):
            loop = LoopingCall(
                self.url_requester.next,
            )
            self._loops.append(loop)
            started = loop.start(interval=1)
            self._starts.append(started)

    def stop(self):
        for loop in self._loops:
            loop.stop()
        return gather_deferreds(self._starts)


class TestResponseTime(TestCase):
    def setUp(self):
        self.rate_measurer = RateMeasurer()
        self.load_generator = LoadGenerator(
            url_requester(),
            self.rate_measurer,
            req_per_sec=10,
        )
        self.load_generator.start()

    def tearDown(self):
        return self.load_generator.stop()

    def test_foo(self):
        def do_assert():
            self.assertEqual(10, self.rate_measurer.rate)
        return deferLater(reactor, 10, do_assert)
