# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
ZFS APIs.
"""

from __future__ import absolute_import

import os
import string

from subprocess import check_call
import time

from characteristic import attributes, with_cmp, with_repr

from zope.interface import implementer

from eliot import Logger

from twisted.python.filepath import FilePath
from twisted.internet.defer import succeed
from twisted.application.service import Service

from .interfaces import IFilesystem, IStoragePool

from .._model import VolumeSize, VolumeName

import pyrax

import netifaces
import ipaddr


def get_public_ips():
    ips = []
    for interface in netifaces.interfaces():
        interface_addresses = netifaces.ifaddresses(interface)
        ipv4addresses = interface_addresses.get(netifaces.AF_INET, [])
        for address in ipv4addresses:
            ip = ipaddr.IPv4Address(address['addr'])
            if not ip.is_private:
                ips.append(ip)
    return ips


def driver_from_environment():
    # Notes on how to get this working are in https://clusterhq.atlassian.net/browse/FLOC-1147
    username = os.environ.get('OPENSTACK_API_USER')
    api_key = os.environ.get('OPENSTACK_API_KEY')

    ctx = pyrax.create_context(
        id_type="rackspace", username=username, api_key=api_key)
    ctx.authenticate()
    compute = ctx.get_client('compute', 'DFW')
    volume = ctx.get_client('volume', 'DFW')

    return compute, volume


def next_device():
    """
    Can't just use the dataset name as the block device name
    inside the node, nor volume.id nor random_name. You can't
    even leave it blank; auto is not supported.

     Exception: 400 Bad Request The supplied device path (/dev/3e074171-5065-466f-9aa5-9aacdf738b40.default.mongodb-volume-example) is invalid.

    (Pdb++) driver.attach_volume(node=node, volume=volume)
    *** Exception: 400 Bad Request The supplied device path (auto) is invalid.

    (Pdb++) driver.attach_volume(node=node, volume=volume, device='/dev/{}'.format(volume.id))
    *** Exception: 400 Bad Request The supplied device path (/dev/3419c7f5-95ed-490b-9c0a-590992380130) is invalid.
    """
    prefix = '/dev/xvd'
    existing = [path for path in FilePath('/dev').children()
                if path.path.startswith(prefix)
                and len(path.basename()) == 4]
    letters = string.ascii_lowercase
    return prefix + letters[len(existing)]


def random_name():
    """Return a random pool name.

    :return: Random ``bytes``.
    """
    return os.urandom(8).encode("hex")


@implementer(IFilesystem)
@with_cmp(["pool", "dataset"])
@with_repr(["pool", "dataset"])
class Filesystem(object):
    """A ZFS filesystem.

    For now the goal is simply not to pass bytes around when referring to a
    filesystem.  This will likely grow into a more sophisticiated
    implementation over time.
    """
    def __init__(self, pool, dataset, mountpoint=None, size=None,
                 reactor=None):
        """
        :param pool: The filesystem's pool name, e.g. ``b"hpool"``.

        :param dataset: The filesystem's dataset name, e.g. ``b"myfs"``, or
            ``None`` for the top-level filesystem.

        :param twisted.python.filepath.FilePath mountpoint: Where the
            filesystem is mounted.

        :param VolumeSize size: The capacity information for this filesystem.
        """
        self.pool = pool
        self.dataset = dataset
        self._mountpoint = mountpoint
        self.size = size
        if reactor is None:
            from twisted.internet import reactor
        self._reactor = reactor

    @property
    def name(self):
        """The filesystem's full name, e.g. ``b"hpool/myfs"``."""
        if self.dataset is None:
            return self.pool
        return b"%s/%s" % (self.pool, self.dataset)

    def get_path(self):
        return self._mountpoint


def volume_to_dataset(volume):
    """Convert a volume to a dataset name.

    :param flocker.volume.service.Volume volume: The volume.

    :return: Dataset name as ``bytes``.
    """
    return b"%s.%s" % (volume.node_id.encode("ascii"),
                       volume.name.to_bytes())


@implementer(IStoragePool)
@with_repr(["_name"])
@with_cmp(["_name", "_mount_root"])
class StoragePool(Service):
    """
    A ZFS storage pool.

    Remotely owned filesystems are mounted read-only to prevent changes
    (divergence which would break ``zfs recv``).  This is done by having the
    root dataset be ``readonly=on`` - which is inherited by all child datasets.
    Locally owned datasets have this overridden with an explicit
    ```readonly=off`` property set on them.
    """
    logger = Logger()

    def __init__(self, reactor, name, mount_root):
        """
        :param reactor: A ``IReactorProcess`` provider.
        :param bytes name: The pool's name.
        :param FilePath mount_root: Directory where filesystems should be
            mounted.
        """
        self._reactor = reactor
        self._name = name
        self._mount_root = mount_root

    def create(self, volume):
        # (Pdb++) filesystem
        # <Filesystem(pool='flocker', dataset='3e074171-5065-466f-9aa5-9aacdf738b40.default.mongodb-volume-example')>
        # (Pdb++) filesystem.get_path()
        # FilePath('/flocker/3e074171-5065-466f-9aa5-9aacdf738b40.default.mongodb-volume-example')

        filesystem = self.get(volume)
        mount_path = filesystem.get_path().path
        device_path = next_device()

        compute_driver, volume_driver = driver_from_environment()
        # Create Openstack block
        # create_volume(size, name, location=None, snapshot=None)
        # Figure out how to convert volume.size into a supported Rackspace disk size, in GB.
        # Hard code it for now.
        openstack_volume = volume_driver.create(name=volume.name.to_bytes(), size=100)
        # Attach to this node.
        # We need to know what the current node IP is here, or supply
        # current node as an attribute of OpenstackStoragePool
        public_ips = get_public_ips()
        all_nodes = compute_driver.servers.list()
        for node in all_nodes:
            if ipaddr.IPv4Address(node.accessIPv4) in public_ips:
                break
        else:
            raise Exception('Current node not listed. IPs: {}, Nodes: {}'.format(public_ips, all_nodes))

        openstack_volume.attach_to_instance(instance=node, mountpoint=device_path)

        # Wait for the device to appear
        while True:
            if FilePath(device_path).exists():
                break
            else:
                time.sleep(0.5)

        # Format with ext4
        # Don't bother partitioning...I don't think it's necessary these days.
        command = ['mkfs.ext4', device_path]
        check_call(command)
        # Create the mount directory
        mount_path_filepath = FilePath(mount_path)
        if not mount_path_filepath.exists():
            mount_path_filepath.makedirs()
        # Mount (zfs automounts, I think, but we'll need to do it ourselves.)
        command = ['mount', device_path, mount_path]
        check_call(command)

        # Return the filesystem
        return succeed(filesystem)

    def change_owner(self, volume, new_volume):
        new_filesystem = self.get(new_volume)
        return succeed(new_filesystem)

    def get(self, volume):
        dataset = volume_to_dataset(volume)
        mount_path = self._mount_root.child(dataset)
        return Filesystem(
            self._name, dataset, mount_path, volume.size)

    def enumerate(self):
        listing = _list_filesystems(self._reactor, pool=self)

        def listed(filesystems):
            result = set()
            for entry in filesystems:
                filesystem = Filesystem(
                    self._name, entry.dataset, FilePath(entry.mountpoint),
                    VolumeSize(maximum_size=entry.refquota))
                result.add(filesystem)
            return result

        return listing.addCallback(listed)


@attributes(["dataset", "mountpoint", "refquota"], apply_immutable=True)
class _DatasetInfo(object):
    """
    :ivar bytes dataset: The name of the ZFS dataset to which this information
        relates.
    :ivar bytes mountpoint: The value of the dataset's ``mountpoint`` property
        (where it will be auto-mounted by ZFS).
    :ivar int refquota: The value of the dataset's ``refquota`` property (the
        maximum number of bytes the dataset is allowed to have a reference to).
    """


def _list_filesystems(reactor, pool):
    """Get a listing of all filesystems on a given pool.

    :param pool: A `flocker.volume.filesystems.interface.IStoragePool`
        provider.
    :return: A ``Deferred`` that fires with an iterator, the elements
        of which are ``tuples`` containing the name and mountpoint of each
        filesystem.
    """
    compute_driver, volume_driver = driver_from_environment()
    volumes = volume_driver.list()

    def listed():
        for openstack_volume in volumes:
            # Use VolumeName.from_bytes here instead??
            namespace, dataset_id = openstack_volume.name.split('.', 1)
            volume_name = VolumeName(namespace=namespace, dataset_id=dataset_id)
            flocker_volume = pool.volume_service.get(volume_name)
            mountpoint = flocker_volume.get_filesystem().get_path().path
            refquota = openstack_volume.size * 1024 * 1024
            # Maybe use volume_name here??
            yield _DatasetInfo(dataset=openstack_volume.name, mountpoint=mountpoint, refquota=refquota)

    return succeed(listed())
