What is OpenStack?
------------------
* Set of projects which people usually use to deploy infrastructure as a service solutions.
  For example, it is a back end for Rackspace.
* Supporting openstack's Cinder storage would allow us to support some infrastructure without ZFS.
* This means that you're dealing with disks, instead of the filesystem on top of those disks.

How to interact with it?
------------------------
* We made a start on getting a local environment running with Openstack on Vagrant
* We settled on a more realistic, and easier to get started case of Rackspace nodes
* This meant that we could use apache-libcloud to interact with it
  * libcloud is a library for interacting with > 30 cloud providers so we hoped we could get a lot of benefit with hopefully not too much work
  * However, our initial attempts showed up some libcloud problems, including particularly bad error reporting so we gave up
* We switched to pyrax, a Rackspace API which they say "should work with most OpenStack-based cloud deployments" (though we haven't tried)

What did we do?
---------------
* Wanted the core feature of flocker to work - migrating data from one node to another to work
* Use the acceptance test for this - does what the docs do, and for those who don't know that means:
  * adding some data to Mongo DB on one node,
  * moving mongo DB to another node,
  * checking that the data is still available
* The summary of how we managed this was, when you want to move an application with data:
  * stop the container
  * unmount the device
  * detatch the block device
  * attach it to another node
  * mount it
  * start the container

However, integrating this with Flocker has some challenges, mainly because the code expects a filesystem, and deals with ZFS as one of some possible filesystems.
But block storage works differently - there is no two-phase push for example.
This means that we might have to think about how to avoid downtime during the slow phases of attaching and detaching block devices.
We also had to think about credentials, as cloud providers such as Rackspace require them.

What is necessary
------------------
* We used environment variables for credentials, how should users pass credentials in?
* We ditched ZFS for this, but our code will have to be structured to allow both ZFS and OpenStack.
  What will the user's UI be for choosing which back end they want?
* Hopefully we can switch to libcloud and fix the issues
* How about sending a volume from a node with ZFS to an OpenStack node? Impossible?

Limits of Cloud Block Storage
-----------------------------

* Different cloud providers have different limits.
* For example, rackspace limits volume sizes and maximum numbers of volumes per server.

Discussion
----------

* Where and how to configure Cloud credentials
  * On each Node, in volumes.json?
    That doesn't really make sense because all the Nodes must be part of the same OpenStack cluster and have access to the same OpenStack block devices.
  * Individual ``flocker-deploy`` users supply their own credentials?
    But no audit trail / log of who made changes anyway, so seems pointless.
  * A cluster wide set credentials, for the first version anyway.
    Allows the convergence agent to make all necessary changes on all nodes.

* Slow API calls
  * API calls to attach and detach block devices are not synchronous.
  * The API call returns and you then have to wait (often minutes) before the block appears or disappears inside the node OS.
  * Investigate the cause of the delay.
  * Possible causes:
    * Rackspace moving data behind the scenes.
      Would explain slow re-attachment, but not slow detachment.
    * Slow release and detection of devices by the node operating system.
      Investigate what sort of device is being emulated and whether other users report the same delays.
    * We also noted that the block device could not be detached without first unmounting it.
      Which suggests that Openstack has access to the device usage inside the node OS.

* Cluster Configuration
  * ``flocker-reportstate`` is currently run on each node causing each node to issue the same (slow) Openstack API calls.
    But Openstack block stores are not tied to any particular node so the volume information, in this case, could be retrieved centrally by ``flocker-deploy``.

* List available volumes
  * Each node can do this its self, but that'll cause duplicate API calls.
  * OR the client (flocker-deploy) could make direct OpenStack API calls instead.
  * Supply the found list of volumes to each node as

* Limits of Cloud Block Storage

  http://www.rackspace.com/knowledge_center/article/cloud-block-storage-overview#limits-of-cbs

  - 100 GB to 1 TB / Volume
  - 14 Volumes max / Server - Operating system (OS) dependent - 50 Volumes max
    / region OR 10 TB max/ region (whichever is first) - This is the default
    for all new customers. Customers can request limit increases. Please
    contact Rackspace Support, your Account Manager, or your Service Delivery
    Manager for more information.

* Resizing blocks
  * Appears to be supported by Rackspace.
  * Need to think about whether the filesystem can be resized while mounted.
  * And if not, to modify state changes to include stopping applications, and unmounting before resizing.
  * Shrinking is often not possible but growing a filesystem is usually possible.

* Pushing volumes
  * We don't use this state change in this Openstack spike.
    But it might be a useful place to copy data between cloud regions or between different cloud providers.

* Add meta data for openstack volume.

  Or choose a human readable name for the Openstack volume.

* Duplicate API calls

  Could we only make the calls from  flocker deploy
  - To avoid duplication
  - To avoid redundant authentication
  - To avoid having to send cloud credentials to each node.
