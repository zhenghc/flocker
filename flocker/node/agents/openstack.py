class OpenStackDeployer(object):
    def __init__(self, ...):
        self._deployer = IaaSLikeDeployer(
            hostname=self.hostname,
            resize_dataset=self._resize_dataset,
            handoff_dataset=self._handoff_dataset,
            wait_for_dataset=self._wait_for_dataset,
            create_dataset=self._create_dataset,
        )

    def _resize_dataset(self, dataset):
        openstack_api_call(dataset...)


    def discover_local_state(self):
        ... check mounts ...
        return NodeState(manifestations=openstack_api_call(self.hostname))
