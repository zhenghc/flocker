#!/bin/sh

# Checkout devstack
sudo apt-get -y install git
git clone https://git.openstack.org/openstack-dev/devstack
cd devstack

# Switch to stable Juno branch:
git checkout stable/juno

# Create a stack user:
./tools/create-stack-user.sh

# Switch to stack user
su - stack

# Create config file with default passwords:
echo '[[local|localrc]]' > local.conf
echo ADMIN_PASSWORD=password >> local.conf
echo MYSQL_PASSWORD=password >> local.conf
echo RABBIT_PASSWORD=password >> local.conf
echo SERVICE_PASSWORD=password >> local.conf
echo SERVICE_TOKEN=tokentoken >> local.conf
echo OFFLINE=False >> local.conf

# Start OpenStack:
./stack.sh
