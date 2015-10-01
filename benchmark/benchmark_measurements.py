from pyrsistent import PClass, field

from twisted.internet.defer import maybeDeferred


class _WallClock(PClass):
    clock = field(mandatory=True)

    def __call__(self, f, *a, **kw):
        def finished(ignored):
            end = self.clock.seconds()
            elapsed = end - start
            return elapsed

        start = self.clock.seconds()
        d = f(*a, **kw)
        d.addCallback(finished)
        return d

_measurements = {
    "wallclock": _WallClock,
}


def get_measurement(clock, name):
    return maybeDeferred(_measurements[name], clock=clock)
