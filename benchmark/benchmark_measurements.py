from pyrsistent import PClass, field


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
    return _measurements[name](clock=clock)
