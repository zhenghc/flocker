# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
# -*- test-case-name: flocker.common.test.test_release -*-

"""
Tools for releasing Flocker.
"""

from twisted.python.usage import Options
from twisted.python.versions import Version

PACKAGE_NAME = 'Flocker'

def flocker_version(major, minor, micro, prerelease=None):
    """
    Make a ``Version`` with a fixed package name of 'Flocker'.
    """
    return Version(PACKAGE_NAME, major, minor, micro, prerelease)


class ReleaseOptions(Options):
    """
    Command line options for the flocker-release tool.
    """
    synopsis = b'Usage: flocker-release [options] <version>'

    def opt_pre_release(self, version):
        """
        """
        self['prerelease_version'] = version

    def parseArgs(self, version):
        """
        """
        self['version'] = version





