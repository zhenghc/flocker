from pyrsistent import PClass, field

from twisted.web.client import ResponseFailed


class _ReadRequest(PClass):
    client = field(mandatory=True)

    def _ssl_error(self, failure):
        failure.trap(ResponseFailed)
        for reason in failure.value.reasons:
            reason.printTraceback()
        return reason

    def run(self):
        d = self.client.list_datasets_state()
        d.addErrback(self._ssl_error)
        return d


_metrics = {
    "read-request": _ReadRequest,
}


def get_metric(client, name):
    return maybeDeferred(_metrics[name], client=client)
