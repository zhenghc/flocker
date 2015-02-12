from zope.interface import implementer

from characteristic import Attribute, attributes

from twisted.internet.defer import Deferred, succeed

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

    def run(self, deployer):
        return self.method()


@attributes([
    Attribute("hostname"),
    Attribute("resize_dataset"),
    Attribute("handoff_dataset"),
    Attribute("wait_for_dataset"),
    Attribute("create_dataset"),
])
class IaaSLikeDeployer(object):
    def calculate_necessary_state_changes(self, local_state,
                                          desired_configuration,
                                          current_cluster_state):
        dataset_changes = find_dataset_changes(
            self.hostname, current_cluster_state, desired_configuration)

        # TODO Respect leases

        phases = []

        if dataset_changes.resizing:
            phases.append(InParallel(changes=[
                self.resize_dataset(dataset=dataset)
                for dataset in dataset_changes.resizing]))

        if dataset_changes.going:
            phases.append(InParallel(changes=[
                self.handoff_dataset(dataset=handoff.dataset,
                                     hostname=handoff.hostname)
                for handoff in dataset_changes.going]))

        if dataset_changes.coming:
            phases.append(InParallel(changes=[
                self.wait_for_dataset(dataset=dataset)
                for dataset in dataset_changes.coming]))
            phases.append(InParallel(changes=[
                self.resize_dataset(dataset=dataset)
                for dataset in dataset_changes.coming]))

        if dataset_changes.creating:
            # TODO Could be in parallel with the rest
            phases.append(InParallel(changes=[
                self.create_dataset(dataset=dataset)
                for dataset in dataset_changes.creating]))

        return Sequentially(changes=phases)


@implementer(IDeployer)
@attributes([
    Attribute("hostname"),
    Attribute("_local_state", default_value=None),
    Attribute("_waiting", default_factory=dict),
])
class IaaSLikeMemoryDeployer(object):
    def __init__(self, *args, **kwargs):
        super(IaaSLikeMemoryDeployer, self).__init__(*args, **kwargs)
        if self._local_state is None:
            self._local_state = NodeState(
                hostname=self.hostname, running=[], not_running=[]
            )
        self._deployer = IaaSLikeDeployer(
            hostname=self.hostname,
            resize_dataset=self._resize_dataset,
            handoff_dataset=self._handoff_dataset,
            wait_for_dataset=self._wait_for_dataset,
            create_dataset=self._create_dataset,
        )

    def discover_local_state(self):
        return succeed(self._local_state)

    def calculate_necessary_state_changes(self, local_state, configuration,
                                          cluster_state):
        iaas_changes = self._calculate_handoff_completion(cluster_state)
        basic_changes = self._deployer.calculate_necessary_state_changes(
            local_state, configuration, cluster_state,
        )
        return InParallel(changes=[basic_changes] + iaas_changes)

    def _calculate_handoff_completion(self, cluster_state):
        # We can complete a handoff when no one else in the cluster
        # claims a primary manifestation of the dataset.
        changes = []
        for dataset_id in self._waiting:
            found = False
            for node in cluster_state.nodes:
                for manifestation in node.manifestations():
                    if manifestation.dataset_id == dataset_id and manifestation.primary:
                        found = True
            if not found:
                changes.append(self._receive_handoff(dataset_id))
        return changes

    def _get_manifestation(self, dataset_id):
        [existing] = (
            manifestation
            for manifestation
            in self._local_state.other_manifestations
            if manifestation.dataset.dataset_id == dataset_id
        )
        return existing

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
        print "Handing off", dataset, "to", hostname
        replica = Manifestation(dataset=dataset, primary=False)
        self._replace_manifestation(replica)

    @_StateChanger
    def _wait_for_dataset(self, dataset):
        print "Began to wait for", dataset
        result = self._waiting[dataset.dataset_id] = Deferred()
        return result

    @_StateChanger
    def _receive_handoff(self, dataset_id):
        existing = self._get_manifestation(dataset_id)
        primary = Manifestation(dataset=existing.dataset, primary=True)
        print "Finished waiting for", primary
        self._replace_manifestation(primary)
        self._waiting.pop(dataset_id).callback(None)
