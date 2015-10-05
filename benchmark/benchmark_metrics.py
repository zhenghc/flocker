from uuid import uuid4
from itertools import cycle

from pyrsistent import PClass, field

from twisted.web.client import ResponseFailed

from twisted.internet.defer import succeed, maybeDeferred

from flocker.testtools import loop_until

# XXX A value I think works on both Cinder and EBS, and the
# docs recommend against passing None; no other purpose here.
MAXIMUM_SIZE = 100 * 2 ** 30


def _report_ssl_error(failure):
    failure.trap(ResponseFailed)
    for reason in failure.value.reasons:
        reason.printTraceback()
    return reason


class _ReadRequest(PClass):
    client = field(mandatory=True)

    def run(self):
        d = self.client.list_datasets_state()
        d.addErrback(_report_ssl_error)
        return d

    def cleanup(self):
        return succeed(None)


class _ReadRequestMetric(PClass):
    client = field(mandatory=True)

    def get_probe(self):
        return _ReadRequest(client=self.client)


class _WriteRequest(PClass):
    client = field(mandatory=True)
    dataset_id = field(mandatory=True)
    primary = field(mandatory=True)

    def run(self):
        return self.client.move_dataset(
            primary=self.primary,
            dataset_id=self.dataset_id,
        )

    def cleanup(self):
        return succeed(None)


class _WriteRequestMetric(PClass):
    client = field(mandatory=True)
    dataset_id = field(mandatory=True)
    some_primaries = field(mandatory=True)

    @classmethod
    def from_client(cls, client):
        some_primaries = iter(cycle([uuid4(), uuid4()]))
        d = client.list_datasets_configuration()

        def create(datasets):
            for a_dataset in datasets:
                return cls(
                    client=client,
                    dataset_id=a_dataset.dataset_id,
                    some_primaries=some_primaries,
                )
            # If necessary, configure a dataset.
            dataset_id = uuid4()
            d = client.create_dataset(
                primary=next(some_primaries),
                dataset_id=dataset_id,
                maximum_size=MAXIMUM_SIZE,
            )
            return d.addCallback(
                lambda ignored: cls.from_client(client)
            )
        d.addCallback(create)
        return d

    def get_probe(self):
        return _WriteRequest(
            client=self.client,
            primary=next(self.some_primaries),
            dataset_id=self.dataset_id,
        )


@classmethod
def pick_primary_node(cls, client):
    d = client.list_nodes()

    def pick_primary(nodes):
        for node in nodes:
            return cls(client=client, primary=node)
        # Cannot proceed if there are no nodes in the cluster!
        raise Exception("Found no cluster nodes; can never converge.")
    d.addCallback(pick_primary)
    return d


class _CreateDatasetConvergence(PClass):
    client = field(mandatory=True)
    primary = field(mandatory=True)
    dataset_id = field(mandatory=True)

    def run(self):
        def dataset_matches(inspecting, expected):
            return (
                expected.dataset_id == inspecting.dataset_id and
                expected.primary == inspecting.primary and
                inspecting.path is not None
            )

        d = self.client.create_dataset(
            primary=self.primary.uuid,
            maximum_size=MAXIMUM_SIZE,
            dataset_id=self.dataset_id,
        )
        d.addCallback(
            loop_until_converged,
            self.client.list_datasets_state,
            dataset_matches,
        )
        return d

    def cleanup(self):
        return self.client.delete_dataset(dataset_id=self.dataset_id)


class _CreateDatasetConvergenceMetric(PClass):
    client = field(mandatory=True)
    primary = field(mandatory=True)

    from_client = pick_primary_node

    def get_probe(self):
        return _CreateDatasetConvergence(
            client=self.client,
            primary=self.primary,
            dataset_id=uuid4(),
        )


class _CreateContainerConvergence(PClass):
    client = field(mandatory=True)
    primary = field(mandatory=True)
    name = field(mandatory=True)
    image = field(mandatory=True)

    def run(self):
        def container_matches(inspecting, expected):
            return expected.serialize() == inspecting.serialize()

        d = self.client.create_container(
            self.primary,
            self.name,
            u"nginx",
        )
        d.addCallback(
            loop_until_converged,
            self.client.list_containers_state,
            container_matches,
        )
        return d

    def cleanup(self):
        return self.client.delete_container(name=self.name)


class _CreateContainerConvergenceMetric(PClass):
    client = field(mandatory=True)
    primary = field(mandatory=True)

    from_client = pick_primary_node

    def get_probe(self):
        # XXX Should involve a dataset, does not; probably does not make much
        # real difference.
        return _CreateContainerConvergence(
            client=self.client,
            primary=self.primary,
            name=unicode(uuid4()),
            image=u"nginx",
        )


def _converged(expected, list_state, state_matches):
    d = list_state()

    def find_match(existing_state):
        return any(
            state_matches(state, expected)
            for state in existing_state
        )
    d.addCallback(find_match)
    return d


def loop_until_converged(expected, list_state, state_matches):
    # XXX reactor
    return loop_until(
        lambda: _converged(expected, list_state, state_matches)
    )


_metrics = {
    "read-request": _ReadRequestMetric,
    "write-request": _WriteRequestMetric.from_client,
    "create-dataset-convergence": _CreateDatasetConvergenceMetric.from_client,
    "create-container-convergence":
        _CreateContainerConvergenceMetric.from_client,
}


def get_metric(client, name):
    return maybeDeferred(_metrics[name], client=client)
