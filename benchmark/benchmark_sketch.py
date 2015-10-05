from pprint import pprint
from json import dump
from platform import node, platform
from datetime import datetime
from os import environ, getcwd

from twisted.python.components import proxyForInterface
from twisted.python.filepath import FilePath
from twisted.internet.task import cooperate
from twisted.internet.defer import maybeDeferred

from flocker import __version__ as flocker_client_version
from flocker.apiclient import (
    IFlockerAPIV1Client, FakeFlockerClient, FlockerClient,
)
from flocker.common import gather_deferreds

from benchmark_metrics import get_metric
from benchmark_measurements import get_measurement


def sample(measure, operation):
    samples = []

    def once(i):
        print("Starting sample #{i}".format(i=i))
        d = maybeDeferred(operation.get_probe)

        def got_probe(probe):
            d = measure(probe.run)
            d.addCallbacks(
                lambda interval: samples.append(
                    dict(success=True, value=interval)
                ),
                lambda reason: samples.append(
                    dict(success=False, reason=reason.getTraceback()),
                ),
            )
            d.addCallback(lambda ignored: probe.cleanup())
            return d
        d.addCallback(got_probe)
        return d
    task = cooperate(once(i) for i in range(3))
    return task.whenDone().addCallback(lambda ignored: samples)


def record_samples(samples, version, metric_name, measurement_name):
    timestamp = datetime.now().isoformat()
    artifact = dict(
        client=dict(
            flocker_version=flocker_client_version,
            date=timestamp,
            working_directory=getcwd(),
            username=environ[b"USER"],
            nodename=node(),
            platform=platform(),
        ),
        server=dict(
            flocker_version=version,
        ),
        measurement=measurement_name,
        metric_name=metric_name,
        samples=samples,
    )
    print("Measurements of {} for {} against {}:".format(
        measurement_name, metric_name, version,
    ))
    pprint(samples)
    filename = "samples-{timestamp}.json+flocker-benchmark".format(
        timestamp=timestamp
    )
    with open(filename, "w") as f:
        dump(artifact, f)


class FastConvergingFakeFlockerClient(
    proxyForInterface(IFlockerAPIV1Client)
):
    def create_dataset(self, *a, **kw):
        result = self.original.create_dataset(*a, **kw)
        self.original.synchronize_state()
        return result

    def move_dataset(self, *a, **kw):
        result = self.original.move_dataset(*a, **kw)
        self.original.synchronize_state()
        return result

    def delete_dataset(self, *a, **kw):
        result = self.original.delete_dataset(*a, **kw)
        self.original.synchronize_state()
        return result

    def create_container(self, *a, **kw):
        result = self.original.create_container(*a, **kw)
        self.original.synchronize_state()
        return result

    def delete_container(self, *a, **kw):
        result = self.original.delete_container(*a, **kw)
        self.original.synchronize_state()
        return result


def driver(reactor, control_service_address=None, cert_directory=b"certs",
           metric_name=b"read-request", measurement_name=b"wallclock"):
    if control_service_address:
        cert_directory = FilePath(cert_directory)
        client = FlockerClient(
            reactor,
            host=control_service_address,
            port=4523,
            ca_cluster_path=cert_directory.child(b"cluster.crt"),
            cert_path=cert_directory.child(b"user.crt"),
            key_path=cert_directory.child(b"user.key"),
        )
    else:
        client = FastConvergingFakeFlockerClient(FakeFlockerClient())

    metric = get_metric(client=client, name=metric_name)
    measurement = get_measurement(
        clock=reactor, client=client, name=measurement_name,
    )
    version = client.version()

    d = gather_deferreds((metric, measurement, version))

    def got_parameters((metric, measurement, version)):
        d = sample(measurement, metric)
        d.addCallback(
            record_samples,
            version[u"flocker"],
            metric_name,
            measurement_name
        )
        return d

    d.addCallback(got_parameters)
    return d

