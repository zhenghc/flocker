# Copyright ClusterHQ Inc.  See LICENSE file for details.

"""
GCE provisioner.

The following resources are helpful to refer to while maintaining this file:
- Rest API: https://cloud.google.com/compute/docs/reference/latest/
- Python Client: https://cloud.google.com/compute/docs/tutorials/python-guide
- Python API: https://google-api-client-libraries.appspot.com/documentation/compute/v1/python/latest/ # noqa
- Python Oauth: https://developers.google.com/identity/protocols/OAuth2ServiceAccount#authorizingrequests # noqa

We store the metadata as a JSON blob in the description of the instance.

A convenient ``jq`` blob for seeing the list of all nodes created by this
provisioner, and unwinding the encoded description is:

    gcloud compute instances list --format=json | jq '.[] |
        select(.tags.items | [.[]?] | map(. == "json-description") | any) |
        setpath(["description"]; .description|fromjson)'
"""

import json

from eliot import start_action
from pyrsistent import PClass, field, pset_field
from textwrap import dedent
from twisted.conch.ssh.keys import Key
from zope.interface import implementer
from googleapiclient import discovery
from oauth2client.client import (
    GoogleCredentials, SignedJwtAssertionCredentials
)

from ..node.agents.gce import wait_for_operation
from ..common import retry_effect_with_timeout

from ._common import IProvisioner, INode
from ._install import provision_for_any_user
from ._effect import sequence
from ._ssh import sudo_from_args, run_remotely

# Defaults for some of the instance construction parameters.
_GCE_DISK_SIZE_GIB = 10
_GCE_INSTANCE_TYPE = u"n1-standard-1"
_GCE_ACCEPTANCE_USERNAME = u"flocker-acceptance"

# The network used must have firewall rules such that the node running
# run_acceptance_test can access the flocker client API and docker running on
# the nodes as well as all incoming ports for some docker containers we spin
# up. This requires rules for:
#
# TCP: 4523 (Flocker)
# TCP: 2376 (Docker)
# TCP: All-incoming (For connecting to docker containers we spin up)
#
# The "default" network in the clusterhq-acceptance project on GCE has this set
# up for instances tagged flocker-acceptance.
_GCE_FIREWALL_TAG = u"allow-incoming-traffic"

# Tag for all instances created by the GCEProvisioner.
_GCE_PROVISIONER_TAG = "flocker-gce-provisioner"

# Tag to indicate that the description is intended to be JSON formatted.
_JSON_DESCRIPTION_TAG = u"json-description"


def _clean_to_gce_name(identifier):
    """
    GCE requires the names of all resources to comply with RFC1035. This
    function takes an identifier which might not comply with RFC1035 and
    attempts to map it into the logical equivalent identifier that does match
    RFC1035.

    :param unicode identifier: The input identifier to be mapped into something
        RFC1035 compliant.

    :returns: An RFC1035 compliant variation of the identifier.
    """
    return unicode(identifier.lower().replace(u'+', u'-').replace(u'/', u'-'))


class _DistributionImageParams(PClass):
    """
    Simple helper to discover the latest available image for a given
    distribution. See the docstring for :func:`get_active_image` for an
    explanation of the GCE image system.

    :ivar unicode project: The name of the project to search for a specific
        image.
    :ivar unicode image_name_prefix: The prefix of the image to find.
    """
    project = field(type=unicode)
    image_name_prefix = field(type=unicode)

    def get_active_image(self, compute):
        """
        Gets a non-deprecated image from a project with a given prefix.

        The images provided by gce go in distribution-specific projects, but
        are publicly accessible by anyone.

        For example, all ubuntu images are in the ``ubuntu-os-cloud`` project.
        In that project there is only 1 non-deprecated image for the various
        ubuntu versions (1 for ubuntu 14.04, 1 for ubuntu 15.10, etc). There
        are also many deprecated versions, which were marked as deprecated when
        the new one was created (for security updates, etc.). All of the 14.04
        images are named ubuntu-1404-trusty-vYYYYMMDD?. So, searching the
        ``ubuntu-os-cloud`` project for a non-deprecated image with the
        ``ubuntu-1404`` prefix is a reasonable way to find the latest ubuntu
        14.04 image.

        The best way to get a list of possible ``image_name_prefix`` values is
        to look at the output from ``gcloud compute images list``

        If you don't have the gcloud executable installed, it can be pip
        installed: ``pip install gcloud``

        project, image_name_prefix examples:
        * ubuntu-os-cloud, ubuntu-1404
        * centos-cloud, centos-7

        :param compute: The Google Compute Engine Service object used to make
            calls to the GCE API.

        :returns: The image resource dict representing the GCE image resource,
            or None if no image found.
        """
        latest_image = None
        page_token = None
        while not latest_image:
            response = compute.images().list(
                project=self.project,
                maxResults=500,
                pageToken=page_token,
                # Filter can be a regex.
                filter='name eq {}.*'.format(self.image_name_prefix)
            ).execute()

            latest_image = next((image for image in response.get('items', [])
                                if 'deprecated' not in image),
                                None)
            page_token = response.get('nextPageToken')
            if not page_token:
                break
        return latest_image


# Parameters to find the active image for a given distribution.
_GCE_DISTRIBUTION_TO_IMAGE_MAP = {
    "centos-7": _DistributionImageParams(
        project=u"centos-cloud",
        image_name_prefix=u"centos-7",
    ),
    "ubuntu-14.04": _DistributionImageParams(
        project=u"ubuntu-os-cloud",
        image_name_prefix=u"ubuntu-1404",
    )
}


class _LoginCredentials(PClass):
    """
    Helper utility to describe a username, public key for GCE to install on a
    VM.

    GCE images have a daemon running in them that read a specific metadata key,
    create users, and install authorized keys for those users. The format is a
    little funny though, so the internal API takes an iterable of these objects
    instead.

    :ivar unicode username: The username of the user to create.
    :ivar unicode public_key: The public key to install in that user's
        authorized_keys.
    """
    username = field(type=unicode)
    public_key = field(type=unicode)


def _create_gce_instance_config(instance_name, project, zone, machine_type,
                                image, login_credentials, disk_size,
                                description, tags, delete_disk_on_terminate,
                                startup_script=None):
    """
    Create a configuration blob to configure a GCE instance.

    :param unicode instance_name: The name of the instance.
    :param unicode project: The name of the gce project to create a
        configuration for.
    :param unicode zone: The name of the gce zone to spin the instance up in.
    :param unicode machine_type: The name of the machine type, e.g.
        'n1-standard-1'.
    :param unicode image: The name of the image to base the disk off of.
    :param login_credentials: An iterable of :class:`_LoginCredentials` to be
        installed on the image.
    :param int disk_size: The size of the disk to create, in GiB.
    :param unicode description: The description to set on the instance.
    :param set tags: A set of unicode tags to apply to the image.
    :param bool delete_disk_on_terminate: Whether to delete the disk when the
        instance terminates or not.
    :param unicode startup_script: An optional startup script to run using the
        GCE startup script runner.

    :return: A dictionary that can be consumed by the `googleapiclient` to
        insert an instance.
    """
    gce_slave_instance_config = {
        u"name": unicode(instance_name),
        u"machineType": (
            u"projects/{}/zones/{}/machineTypes/{}".format(
                project, zone, machine_type)
            ),
        u"disks": [
            {
                u"type": u"PERSISTENT",
                u"boot": True,
                u"mode": u"READ_WRITE",
                u"autoDelete": delete_disk_on_terminate,
                u"initializeParams": {
                    u"sourceImage": unicode(image),
                    u"diskType": (
                        u"projects/{}/zones/{}/diskTypes/pd-standard".format(
                            project, zone)
                    ),
                    u"diskSizeGb": unicode(disk_size)
                }
            }
        ],
        u"networkInterfaces": [
            {
                u"network": (
                    u"projects/{}/global/networks/default".format(project)
                ),
                u"accessConfigs": [
                    {
                        u"name": u"External NAT",
                        u"type": u"ONE_TO_ONE_NAT"
                    }
                ]
            }
        ],
        u"metadata": {
            u"items": [
                {
                    u"key": u"sshKeys",
                    u"value": u"\n".join(list(
                        u"{}:{}".format(x.username, x.public_key)
                        for x in login_credentials
                    ))
                }
            ]
        },
        u"description": description,
        u"serviceAccounts": [
            {
                u"email": u"default",
                u"scopes": [
                    # This gives the image permission to do GCE api calls (like
                    # creating and attaching block devices) with its built-in
                    # service account
                    u"https://www.googleapis.com/auth/compute",
                ]
            },
        ],
        u"tags": {
            u"items": list(
                tag for tag in tags
            )
        }
    }

    if startup_script:
        gce_slave_instance_config[u"metadata"][u"items"].append(
            {
                u"key": u"startup-script",
                u"value": startup_script
            }
        )
    return gce_slave_instance_config


class GCEInstance(PClass):
    """
    Representation of a GCE instance, with all of the information to do
    cloud-level interactions.

    :ivar unicode address: The public IP address of the instance.
    :ivar unicode private_address: The network internal IP address of the
        instance.
    :ivar unicode project: The project the instance a member of.
    :ivar unicode zone: The zone the instance is in.
    :ivar unicode name: The GCE name of the instance used to identify the
        instance.
    :ivar compute: A Google Compute Engine Service that can be used to make
        calls to the GCE API.
    """
    address = field(type=bytes, mandatory=True)
    private_address = field(type=bytes, mandatory=True)
    project = field(type=unicode, mandatory=True)
    zone = field(type=unicode, mandatory=True)
    name = field(type=unicode, mandatory=True)
    tags = pset_field(item_type=unicode)
    compute = field(mandatory=True)

    def destroy(self):
        """
        Destroy this instance, and block until it has completed.
        """
        with start_action(
            action_type=u"flocker:provision:gce:destroy",
            instance_id=self.name,
        ):
            operation = self.compute.instances().delete(
                project=self.project,
                zone=self.zone,
                instance=self.name
            ).execute()
            wait_for_operation(self.compute, operation, timeout_steps=[1]*60)


@implementer(INode)
class GCENode(PClass):
    """
    ``INode`` implementation for GCE. This encompasses cloud-level interactions
    as well as the ability to SSH into the node, and execute
    distribution-specific commands.

    :ivar GCEInstance instance: The GCE instance to use for underlying
        cloud operations.
    :ivar bytes distribution: The OS distribution of the instance.
    :ivar bytes username: The preferred username to access the instance as.
    """
    instance = field(type=GCEInstance, mandatory=True)
    username = field(type=bytes, mandatory=True)
    distribution = field(type=bytes, mandatory=True)

    @property
    def address(self):
        return self.instance.address

    @property
    def private_address(self):
        return self.instance.private_address

    @property
    def name(self):
        return self.instance.name

    def get_default_username(self):
        return self.username

    def provision(self, package_source, variants):
        commands = []
        sed_str = (
            r"s/^\(PermitRootLogin *no\)/"
            r"\n"
            r"# Commented out by flocker provisioner:\n"
            r"#\1\n"
            r"/"
        )

        # On GCE, the centos image is configured to not allow root to ssh on.
        # Enable the configuration and restart the daemon on that system.
        if self.distribution.startswith("centos"):
            username = self.get_default_username()
            enable_root_ssh = sequence([
                sudo_from_args(
                    ['sed', sed_str, '-i.backup', '/etc/ssh/sshd_config']
                ),
                sudo_from_args(['systemctl', 'restart', 'sshd']),
            ])
            commands.append(retry_effect_with_timeout(
                run_remotely(
                    username=username,
                    address=self.address,
                    commands=enable_root_ssh,
                ),
                30
            ))

        commands.append(provision_for_any_user(self, package_source, variants))
        return sequence(commands)

    def destroy(self):
        return self.instance.destroy()

    def reboot(self):
        """
        I think this is never called, and can probably be removed. If it were
        to be implemented it would look something like the following:

            operation = self.compute.instances().reset(
                project=self.project,
                zone=self.zone,
                instance=self.name
            ).execute()
            wait_for_operation(self.compute, operation, timeout_steps=[1]*60)

        But, as that is untested, it will remain unimplemented.
        """
        raise NotImplementedError(
            "GCE does not have reboot implemented because it has "
            "experimentally been determined to not be needed.")


@implementer(IProvisioner)
class GCEProvisioner(PClass):
    """
    A provisioner that can create instances on GCE.

    :ivar unicode zone: The zone in which instances will be provisioned.
    :ivar unicode project: The project under which instances will be
        provisioned.
    :ivar Key ssh_public_key: The public ssh key that will transferred to the
        instance for access.
    :ivar compute: A Google Compute Engine Service that can be used to make
        calls to the GCE API.
    """

    zone = field(type=unicode)
    project = field(type=unicode)
    ssh_public_key = field(type=Key)
    compute = field()

    def get_ssh_key(self):
        return self.ssh_public_key

    def _gce_instance_from_instance_resource(self, instance_resource):
        """
        Constructs a :class:`GCEInstance` from the instance_resource dict
        returned from the API.

        :param dict instance_resource: The instance resource dict returned from
            the GCE API.

        :returns GCEInstance: The :class:`GCEInstance` that corresponds to the
            given instance resource dict.
        """
        network_interface = instance_resource["networkInterfaces"][0]
        return GCEInstance(
            address=bytes(network_interface["accessConfigs"][0]["natIP"]),
            private_address=bytes(network_interface["networkIP"]),
            project=self.project,
            zone=self.zone,
            name=instance_resource['name'],
            tags=instance_resource['tags'].get('items', []),
            compute=self.compute
        )

    def _gce_node_from_instance_resource(self, instance_resource):
        """
        Constructs a :class:`GCENode` from an instance_resource.
        """
        instance = self._gce_instance_from_instance_resource(instance_resource)

        if _JSON_DESCRIPTION_TAG not in instance.tags:
            raise ValueError(
                "Could not create a ``GCENode`` from instance resource"
                "{instance} because the {tag} tag was not present.".format(
                    instance=str(instance_resource), tag=_JSON_DESCRIPTION_TAG)
            )

        # XXX: If you get KeyErrors or JSON parsing errors from this code, it
        # probably means you are trying to create a :class:``GCENode`` object
        # from a GCE instance that was not created by this version of this
        # software.
        description_blob = json.loads(instance_resource["description"])
        return GCENode(
            instance=instance,
            username=bytes(description_blob["username"]),
            distribution=bytes(description_blob["distribution"])
        )

    def create_node(self, name, distribution, metadata={}):
        instance_name = _clean_to_gce_name(name)
        ssh_key = unicode(self.ssh_public_key.toString('OPENSSH'))
        username = _GCE_ACCEPTANCE_USERNAME
        config = _create_gce_instance_config(
            instance_name=instance_name,
            project=self.project,
            zone=self.zone,
            machine_type=_GCE_INSTANCE_TYPE,
            image=(
                _GCE_DISTRIBUTION_TO_IMAGE_MAP[distribution].get_active_image(
                    self.compute)["selfLink"]
            ),
            # The acceptance tests expect to be able to ssh in as root, but on
            # CentOS that is by default turned off, so we must also enable
            # sshing in as a different user to enable root ssh.
            login_credentials=[
                _LoginCredentials(
                    username=username,
                    public_key=ssh_key
                ),
                _LoginCredentials(
                    username=u"root",
                    public_key=ssh_key
                ),
            ],
            disk_size=_GCE_DISK_SIZE_GIB,
            description=json.dumps({
                u"description-format": u"v2",
                u"created-by-python": u"flocker.provision._gce.GCEProvisioner",
                u"name": name,
                u"distribution": distribution,
                u"username": username,
                u"metadata": metadata
            }),
            tags=set([_GCE_PROVISIONER_TAG,
                      _JSON_DESCRIPTION_TAG,
                      _GCE_FIREWALL_TAG]),
            delete_disk_on_terminate=True,
            startup_script=dedent("""\
                #!/bin/sh
                sed -i '/Defaults *requiretty/d' /etc/sudoers
                """),
        )

        operation = self.compute.instances().insert(
            project=self.project,
            zone=self.zone,
            body=config
        ).execute()

        operation_result = wait_for_operation(
            self.compute, operation, timeout_steps=[1]*60)

        if not operation_result:
            raise ValueError(
                "Timed out waiting for creation of VM: {}".format(
                    instance_name
                )
            )

        instance_resource = self.compute.instances().get(
            project=self.project, zone=self.zone, instance=instance_name
        ).execute()

        return self._gce_node_from_instance_resource(instance_resource)

    def _list_all_nodes(self):
        """
        Returns all nodes in the given project and zone that were created by
        this script.

        :returns: An iterable of :class:`GCEInstance` instances.
        """
        unfiltered_results = []
        next_page = None
        while True:
            response = self.compute.instances.list(
                zone=self.zone, project=self.project, page_token=next_page)
            unfiltered_results += list(
                self._gce_node_from_instance_resource(resource)
                for resource in response.items)
            next_page = response.get('nextPageToken')
            if not next_page:
                break
        return list(instance for instance in unfiltered_results
                    if _GCE_PROVISIONER_TAG in instance.tags)

    def get_nodes(self, filters):
        # XXX: Only returns nodes if filters contains an array of ip_addresses.
        ip_addresses = filters.get('ip_address', [])
        if not ip_addresses:
            return []
        return list(gce_node for gce_node in self._list_all_nodes()
                    if gce_node.address in ip_addresses)


def gce_provisioner(
    zone, project, ssh_public_key, gce_credentials=None
):
    """
    Create an :class:`IProvisioner` for provisioning nodes on GCE.

    :param unicode zone: The name of the zone in which to provision instances.
    :param unicode project: The name of the project in which to provision
        instances.
    :param unicode ssh_public_key: The public key that will be put on the VM
        for ssh access.
    :param dict gce_credentials: A dict that has the same content as the json
        blob generated by the GCE console when you add a key to a service
        account. The service account must have permissions to spin up VMs in
        the specified project.

    :return: An class:`IProvisioner` provider for GCE instances.
    """
    key = Key.fromString(bytes(ssh_public_key))
    if gce_credentials is not None:
        credentials = SignedJwtAssertionCredentials(
            gce_credentials['client_email'],
            gce_credentials['private_key'],
            scope=[
                u"https://www.googleapis.com/auth/compute",
            ]
        )
    else:
        credentials = GoogleCredentials.get_application_default()
    compute = discovery.build('compute', 'v1', credentials=credentials)

    return GCEProvisioner(
        zone=unicode(zone),
        project=unicode(project),
        ssh_public_key=key,
        compute=compute,
    )
