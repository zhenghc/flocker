# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
# -*- test-case-name: flocker.common.test.test_release -*-

"""
Tools for releasing Flocker.
"""

from twisted.python.usage import Options, UsageError
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
        self['prerelease'] = int(version)

    def parseArgs(self, version):
        """
        """
        major, minor, micro = [int(v) for v in version.split('.', 2)]

        self['major'] = major
        self['minor'] = minor
        self['micro'] = micro

    def postOptions(self):
        """
        Combine the version components into a ``Version`` instance.
        """
        self['version'] = flocker_version(
            self['major'], self['minor'], self['micro'], self.get('prerelease'))


class ReleaseScript(object):
    """
    Automate the release of Flocker.
    """

    options = ReleaseOptions()

    def main(self, args):
        """
        Parse options and take action.
        """
        # try:
        #     self.options.parseOptions(args)
        # except UsageError as e:
        #     raise SystemExit(e)
