# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
# -*- test-case-name: flocker.common.test.test_release -*-

"""
Tools for releasing Flocker.
"""
from subprocess import check_output

from twisted.python.usage import Options, UsageError
from twisted.python.versions import Version

from zope.interface import Interface, implementer

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

    def opt_pre_release(self, prerelease):
        """
        """
        try:
            self['prerelease'] = int(prerelease)
        except ValueError:
            raise UsageError(
                'Pre-release must be an integer. Found {}'.format(prerelease))


    def parseArgs(self, version):
        """
        """
        try:
            major, minor, micro = [int(v) for v in version.split('.', 2)]
        except ValueError:
            raise UsageError(
                'Version components must be integers. Found {}'.format(version))

        self['major'] = major
        self['minor'] = minor
        self['micro'] = micro

    def postOptions(self):
        """
        Combine the version components into a ``Version`` instance.
        """
        self['version'] = flocker_version(
            self['major'], self['minor'], self['micro'], self.get('prerelease'))


class IVersionControl(Interface):
    """
    """
    def uncommitted():
        """
        Return a list of uncommitted changes.
        """


@implementer(IVersionControl)
class FakeVersionControl(object):
    """
    A fake version control API for use in tests.
    """
    _uncommitted = ()

    def __init__(self, root):
        self._root = root

    def uncommitted(self):
        """
        Return a list of uncommitted changes.
        """
        return [self._root.child(f) for f in self._uncommitted]


@implementer(IVersionControl)
class VersionControl(object):
    """
    A fake version control API for use in tests.
    """
    def __init__(self, root):
        self._root = root

    def uncommitted(self):
        """
        Return a list of uncommitted changes.
        """
        output = check_output(
            ['git', 'status', '--porcelain', self._root.path],
            cwd=self._root.path)
        uncommitted = []
        for line in output.splitlines():
            line = line.strip()
            if line.startswith(('??', 'M')):
                relative_path = line.split()[-1]
                f = self._root.child(relative_path)
                uncommitted.append(f)
        return uncommitted


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
