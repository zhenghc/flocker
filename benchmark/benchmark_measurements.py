from datetime import datetime, timedelta

from pyrsistent import PClass, field, pset
from characteristic import Attribute, attributes

from twisted.internet.defer import Deferred, maybeDeferred
from twisted.protocols.basic import LineOnlyReceiver

from flocker.common import gather_deferreds
from flocker.common.runner import run_ssh


class _WallClock(PClass):
    clock = field(mandatory=True)
    client = field()

    def __call__(self, f, *a, **kw):
        def finished(ignored):
            end = self.clock.seconds()
            elapsed = end - start
            return elapsed

        start = self.clock.seconds()
        d = f(*a, **kw)
        d.addCallback(finished)
        return d


_GET_CURSOR_COMMAND = [b"journalctl", b"--show-cursor", b"--lines", b"0"]


class _ParseCursor(LineOnlyReceiver):
    def __init__(self):
        self.result = Deferred()

    def lineReceived(self, line):
        prefix = b"-- cursor: "
        if line.startswith(prefix):
            cursor = line[len(prefix):].strip()
            self.result.callback(cursor)


def get_cursor(reactor, node):
    parser = _ParseCursor()
    d = run_ssh(
        reactor,
        b"root",
        node.public_address.exploded,
        _GET_CURSOR_COMMAND,
        handle_stdout=parser.lineReceived,
    )
    d.addCallback(lambda ignored: parser.result)
    return d


def _show_journal_command(units, cursor):
    base = [
        b"journalctl",
        b"--after-cursor", cursor,
        b"--output", b"cat",
    ]
    for unit in units:
        base.extend([b"--unit", unit])
    return base


class _ParseWC(LineOnlyReceiver):
    def __init__(self):
        self.bytes = 0
        self.lines = 0

    def lineReceived(self, line):
        self.bytes += len(line)
        self.lines += 1


def measure_journal(reactor, node, cursor, units):
    parser = _ParseWC()
    # It would be nice to count the bytes and lines remotely instead of
    # transferring all that log data.  That's hard, though!  Maybe later.
    command = _show_journal_command(units, cursor)
    d = run_ssh(
        reactor,
        b"root",
        node.public_address.exploded,
        command,
        handle_stdout=parser.lineReceived,
    )
    d.addCallback(
        lambda ignored: dict(lines=parser.lines, bytes=parser.bytes)
    )
    return d


_FLOCKER_PROCESSES = _JOURNAL_UNITS = pset({
    u"flocker-control",
    u"flocker-dataset-agent",
    u"flocker-container-agent",
})


class _JournalVolume(PClass):
    clock = field(mandatory=True)
    client = field(mandatory=True)

    def __call__(self, f, *a, **kw):
        d = self.client.list_nodes()

        def get_cursors(nodes):
            d = gather_deferreds(list(
                # XXX s/clock/reactor/
                get_cursor(self.clock, node) for node in nodes
            ))
            d.addCallback(lambda cursors: (cursors, nodes))
            return d
        d.addCallback(get_cursors)

        def finished(result, (cursors, nodes)):
            d = gather_deferreds(list(
                measure_journal(
                    self.clock, node, cursor, _JOURNAL_UNITS
                ) for node, cursor in zip(nodes, cursors)
            ))
            d.addCallback(
                lambda measurements: dict(
                    lines=sum(m["lines"] for m in measurements),
                    bytes=sum(m["bytes"] for m in measurements),
                )
            )
            return d

        def run(cursors):
            d = f(*a, **kw)
            d.addCallback(finished, cursors)
            return d
        d.addCallback(run)
        return d


class _CPUTime(PClass):
    user = field(mandatory=True)
    system = field(mandatory=True)


_GET_CPUTIME_COMMAND = [
    # Use system ps to collect the information
    b"ps",
    # Output the command name (truncated) and the cputime of the process
    b"-o",
    # `=` provides a header.  Making all the headers blank prevents the header
    # line from being written.
    b"comm=,cputime=",
    # Output lines for processes with names matching the following (values
    # supplied by invoker)
    b"-C",
]


class _CPUParser(LineOnlyReceiver):
    def __init__(self):
        self.result = _CPUTime(user=timedelta(), system=timedelta())

    def lineReceived(self, line):
        # Lines are like:
        #
        # flocker-control 00:03:41
        # flocker-dataset 00:18:14
        # flocker-contain 01:47:02
        name, formatted_cputime = line.split()
        cputime = (
            datetime.strptime(formatted_cputime, "%H:%M:%S") -
            datetime.strptime("", "")
        )

        # XXX Could keep these separate and track them separately.
        #
        # XXX Could actually measure and track user and system time separately.
        #
        self.result = _CPUTime(
            user=self.result.user + cputime,
            system=self.result.system,
        )


def get_cpu_times(reactor, node, processes):
    parser = _CPUParser()
    print "Getting CPU from", node.public_address.exploded
    d = run_ssh(
        reactor,
        b"root",
        node.public_address.exploded,
        _GET_CPUTIME_COMMAND + [b",".join(processes)],
        handle_stdout=parser.lineReceived,
    )
    d.addCallback(lambda ignored: parser.result)
    return d


def _get_all_cpu_times(clock, nodes, processes):
    return gather_deferreds(list(
        get_cpu_times(clock, node, processes)
        for node in nodes
    ))


@attributes(["clock", "client", "f", "a", "kw",
             # Mutate-y bits.
             Attribute(name="nodes", default_factory=list),
             Attribute(name="before_cpu", default_factory=list),
             Attribute(name="after_cpu", default_factory=list),
         ])
class _CPUMeasurement(object):
    def _marshal_times(self, cpuchange):
        return list(
            dict(
                user=cpu.user.total_seconds(),
                system=cpu.system.total_seconds(),
            )
            for cpu in cpuchange
        )

    def _compute_change(self, ignored, before_cpu, after_cpu):
        for (before, after) in zip(before_cpu, after_cpu):
            yield _CPUTime(
                user=after.user - before.user,
                system=after.system - before.system,
            )

    def _get_all_cpu_times(self, ignored):
        return _get_all_cpu_times(
            self.clock, self.nodes, _FLOCKER_PROCESSES
        )

    def measure(self):
        getting_nodes = self.client.list_nodes()
        getting_nodes.addCallback(self.nodes.extend)

        getting_before_cpu = getting_nodes.addCallback(
            self._get_all_cpu_times
        )
        getting_before_cpu.addCallback(self.before_cpu.extend)

        exercising_system = getting_before_cpu.addCallback(
            lambda ignored: self.f(*self.a, **self.kw)
        )
        getting_after_cpu = exercising_system.addCallback(
            self._get_all_cpu_times
        )
        getting_after_cpu.addCallback(self.after_cpu.extend)

        computing = getting_after_cpu.addCallback(
            self._compute_change, self.before_cpu, self.after_cpu
        )

        marshalling = computing.addCallback(self._marshal_times)
        return marshalling


class _CPU(PClass):
    clock = field(mandatory=True)
    client = field(mandatory=True)

    def __call__(self, f, *a, **kw):
        # Put the mutate-y side-effect-y bits onto a separate object with a
        # limited lifetime.
        return _CPUMeasurement(
            clock=self.clock, client=self.client, f=f, a=a, kw=kw
        ).measure()


_measurements = {
    "wallclock": _WallClock,
    "journal-volume": _JournalVolume,
    "flocker-cpu": _CPU,
    # "flocker-memory": _Memory,
}


def get_measurement(clock, client, name):
    return maybeDeferred(_measurements[name], clock=clock, client=client)
