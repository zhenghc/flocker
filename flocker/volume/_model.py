# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
# -*- test-case-name: flocker.volume.test.test_service -*-

"""
Record types for representing volume models.
"""

from characteristic import attributes


@attributes(["maximum_size"], apply_immutable=True)
class VolumeSize(object):
    """
    A data volume's size.

    :ivar int maximum_size: The upper bound on the amount of data that can be
        stored on this volume, in bytes.  May also be ``None`` to indicate no
        particular upper bound is required (when representing desired
        configuration) or known (when representing deployed configuration).
    """


@attributes(["namespace", "dataset_id"])
class VolumeName(object):
    """
    The volume and its copies' name within the cluster.

    :ivar unicode namespace: The namespace of the volume,
        e.g. ``u"default"``. Must not include periods.

    :ivar unicode dataset_id: The unique id of the dataset. It is not
        expected to be meaningful to humans. Since volume ids must match
        Docker container names, the characters used should be limited to
        those that Docker allows for container names (``[a-zA-Z0-9_.-]``).
    """
    def __init__(self):
        """
        :raises ValueError: If a period is included in the namespace.
        """
        if u"." in self.namespace:
            raise ValueError(
                "Periods not allowed in namespace: %s"
                % (self.namespace,))

    @classmethod
    def from_bytes(cls, name):
        """
        Create ``VolumeName`` from its byte representation.

        :param bytes name: The name, output of ``VolumeName.to_bytes``
            call in past.

        :raises ValueError: If parsing the bytes failed.

        :return: Corresponding ``VolumeName``.
        """
        namespace, identifier = name.split(b'.', 1)
        return VolumeName(namespace=namespace.decode("ascii"),
                          dataset_id=identifier.decode("ascii"))

    def to_bytes(self):
        """
        Convert the name to ``bytes``.

        :return: ``VolumeName`` encoded as bytes that can be read by
            ``VolumeName.from_bytes``.
        """
        return b"%s.%s" % (self.namespace.encode("ascii"),
                           self.dataset_id.encode("ascii"))


