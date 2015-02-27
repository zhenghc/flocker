from zope.interface import implementer

from characteristic import Attribute, attributes

from twisted.internet.defer import succeed, fail, maybeDeferred
from twisted.internet.task import deferLater
from twisted.internet import reactor

from .._deploy import (
    IDeployer,
    InParallel, Sequentially,
    find_dataset_changes
)
from ...control import Manifestation, NodeState

class _StateChanger(object):
    def __init__(self, function):
        self.function = function

    def __get__(self, oself, type):
        return _BoundStateChanger(self.function.__get__(oself, type))


class _BoundStateChanger(object):
    def __init__(self, method):
        self.method = method

    def __call__(self, *args, **kwargs):
        return _BoundStateChanger(lambda: self.method(*args, **kwargs))

    def run(self, deployer):
        return maybeDeferred(self.method)


def _calculate_necessary_state_changes(hostname,
                                       local_state,
                                       desired_configuration,
                                       current_cluster_state,
                                       backend):
    """
    Calculate dataset state changes necessary to go from current to
    desired state assuming an IaaS block device-like dataset backend
    implementation (such as EBS or OpenStack Cinder).
    """
    current_cluster_state = current_cluster_state.update_node(
        local_state.to_node())
    dataset_changes = find_dataset_changes(
        hostname, current_cluster_state, desired_configuration)

    # TODO Respect leases

    phases = []

    if dataset_changes.resizing:
        phases.append(InParallel(changes=[
            backend.resize_dataset(dataset=dataset)
            for dataset in dataset_changes.resizing]))

    if dataset_changes.going:
        phases.append(InParallel(changes=[
            backend.handoff_dataset(dataset=handoff.dataset,
                                 hostname=handoff.hostname)
            for handoff in dataset_changes.going]))

    if dataset_changes.coming:
        phases.append(InParallel(changes=[
            backend.wait_for_dataset(dataset=dataset)
            for dataset in dataset_changes.coming]))
        phases.append(InParallel(changes=[
            backend.resize_dataset(dataset=dataset)
            for dataset in dataset_changes.coming]))

    if dataset_changes.creating:
        # TODO Could be in parallel with the rest
        phases.append(InParallel(changes=[
            backend.create_dataset(dataset=dataset)
            for dataset in dataset_changes.creating]))

    # deletion

    return Sequentially(changes=phases)

@implementer(IDeployer)
@attributes([
    Attribute("hostname"),
    Attribute("_local_state", default_value=None),
])
class IaaSLikeMemoryDeployer(object):
    def __init__(self, *args, **kwargs):
        super(IaaSLikeMemoryDeployer, self).__init__(*args, **kwargs)
        if self._local_state is None:
            self._local_state = NodeState(
                hostname=self.hostname, running=[], not_running=[]
            )

    def discover_local_state(self):
        return deferLater(reactor, 1, lambda state=self._local_state: state)

    def calculate_necessary_state_changes(self, local_state, configuration,
                                          cluster_state):
        self._cluster_state = cluster_state
        return _calculate_necessary_state_changes(
            local_state, configuration, cluster_state, self
        )

    def _get_manifestation(self, dataset_id):

        manifestations = list(
            manifestation
            for manifestation
            in self._local_state.other_manifestations
            if manifestation.dataset.dataset_id == dataset_id
        )
        if len(manifestations) == 1:
            return manifestations[0]
        return None

    def _add_manifestation(self, manifestation):
        self._local_state = NodeState(
            hostname=self._local_state.hostname, running=[], not_running=[],
            other_manifestations=(
                self._local_state.other_manifestations | {manifestation}
            )
        )

    def _replace_manifestation(self, replacement):
        existing = self._get_manifestation(replacement.dataset.dataset_id)
        self._local_state = NodeState(
            hostname=self._local_state.hostname, running=[], not_running=[],
            other_manifestations=(
                self._local_state.other_manifestations - {existing} | {replacement}
            )
        )

    @_StateChanger
    def _create_dataset(self, dataset):
        print "Creating", dataset
        manifestation = Manifestation(dataset=dataset, primary=True)
        self._add_manifestation(manifestation)

    @_StateChanger
    def _resize_dataset(self, dataset):
        existing = self._get_manifestation(dataset.dataset_id)
        resized = Manifestation(dataset=dataset, primary=existing.primary)
        print "Resizing", existing, "to", resized
        self._replace_manifestation(resized)

    @_StateChanger
    def _handoff_dataset(self, dataset, hostname):
        manifestation = self._get_manifestation(dataset.dataset_id)
        print "Handing off", manifestation, "to", hostname
        replica = Manifestation(dataset=dataset, primary=False)
        self._replace_manifestation(replica)

    @_StateChanger
    def _wait_for_dataset(self, dataset):
        # We can complete a handoff when no one else in the cluster
        # claims a primary manifestation of the dataset.
        for node in self._cluster_state.nodes:
            if node.hostname == self.hostname:
                continue
            for manifestation in node.manifestations():
                if manifestation.dataset.dataset_id == dataset.dataset_id and manifestation.primary:
                    print u"Still waiting for {}".format(manifestation)
                    return fail(Exception("Still waiting"))

        primary = Manifestation(dataset=dataset, primary=True)
        print u"Finished waiting for {}".format(primary)
        self._replace_manifestation(primary)
        return succeed(None)
