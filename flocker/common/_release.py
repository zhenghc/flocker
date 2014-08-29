# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
# -*- test-case-name: flocker.common.test.test_release -*-

"""
Tools for releasing Flocker.
"""
from subprocess import check_output

from twisted.python.filepath import FilePath
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
                'Version components must be integers. '
                'Found {}'.format(version))

        self['major'] = major
        self['minor'] = minor
        self['micro'] = micro

    def postOptions(self):
        """
        Combine the version components into a ``Version`` instance.
        """
        self['version'] = flocker_version(
            self['major'], self['minor'], self['micro'],
            self.get('prerelease')
        )


class IVersionControl(Interface):
    """
    Version control operations for use in the release process.
    """
    def uncommitted():
        """
        Return a list of uncommitted changes.
        """

    def branch(name):
        """
        Create a new branch named ``name``.
        """

    def branches():
        """
        Return a list of branch names.
        """

    def push(name, remote):
        """
        Push the named branch to remote.
        """


@implementer(IVersionControl)
class FakeVersionControl(object):
    """
    A fake version control API for use in tests.
    """
    def __init__(self, root):
        self._root = root
        self._uncommitted = []
        self._branches = {'local': [], 'origin': []}
        self._remote_branches = []

    def uncommitted(self):
        return [self._root.child(f) for f in self._uncommitted]

    def branch(self, name):
        self._branches['local'].append(name)

    def branches(self, remote=None):
        key = 'local'
        if remote:
            key = remote
            if key not in self._branches:
                raise ReleaseError('Unknown remote {}'.format(remote))
        return self._branches[key]

    def push(self, name, remote):
        if remote not in self._branches:
            raise ReleaseError('Unknown remote {}'.format(remote))
        if name not in self.branches():
            raise ReleaseError('Unknown branch {}'.format(name))
        self._branches[remote].append(name)


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
            ['git', 'status', '--porcelain'],
            cwd=self._root.path)
        uncommitted = []
        for line in output.splitlines():
            line = line.strip()
            if line.startswith(('??', 'M')):
                relative_path = line.split()[-1]
                f = self._root.child(relative_path)
                uncommitted.append(f)
        return uncommitted

    def branch(self, name):
        check_output(
            ['git', 'checkout', '--quiet', '-b', name, 'origin/master'],
            cwd=self._root.path)

    def _remotes(self):
        """
        Return a list of remotes.
        """
        return check_output(
            'git remote'.split(), cwd=self._root.path).splitlines()

    def branches(self, remote=None):
        command = ['git', 'branch', '--list']
        prefix = ''
        if remote:
            if remote not in self._remotes():
                raise ReleaseError('Unknown remote {}'.format(remote))
            prefix = '%s/' % (remote,)
            command.extend(['--remote', prefix + '*'])
        output = check_output(command, cwd=self._root.path)
        branches = []
        for line in output.splitlines():
            branch = line.lstrip(' *').split(None, 1)[0][len(prefix):]
            branches.append(branch)
        return branches

    def push(self, name, remote):
        if remote not in self._remotes():
            raise ReleaseError('Unknown remote {}'.format(remote))
        if name not in self.branches():
            raise ReleaseError('Unknown branch {}'.format(name))

        check_output(
            'git push --quiet {} {}'.format(remote, name).split(),
            cwd=self._root.path
        )


class ReleaseError(Exception):
    """
    An general release error.
    """


class ReleaseScript(object):
    """
    Automate the release of Flocker.
    """
    def __init__(self):
        self.options = ReleaseOptions()
        self.vc = VersionControl(FilePath('.'))

    def _branchname(self):
        """
        Return the branchname for the given release.
        """
        version = self.options['version']
        return 'release/%s.%s' % (version.major, version.minor)

    def _checkout(self):
        """
        Checkout a new release branch for major versions or an existing branch
        for patch versions.
        """
        version = self.options['version']
        branchname = self._branchname()
        if version.micro == 0:
            if branchname in self.vc.branches():
                raise ReleaseError(
                    'Existing branch {} found '
                    'but major or minor release {} requested.'.format(
                        branchname, version.base()))
            self.vc.branch(branchname)
            self.vc.push(branchname, 'origin')

        else:
            if branchname not in self.vc.branches():
                raise ReleaseError(
                    'Existing branch {} not found '
                    'for patch release {}'.format(
                        branchname, version.base()))

    def _check_release_notes(self):
        """
        Check for a heading with the expected version in the NEWS file.
        """

    def _check_copyright(self):
        """
        Check that the LICENSE file contains the correct copyright date.
        """

    def _update_versions(self):
        """
        Update versions in various scripts and commit the changes.
        """

    def _force_build(self):
        """
        Force a build for this branch
        """

    def prepare(self):
        """
        Prepare for a release.
        """
        self._checkout()
        self._check_release_notes()
        self._check_copyright()
        self._update_versions()
        self._force_build()

    def main(self, args):
        """
        Parse options and take action.
        """
        # try:
        #     self.options.parseOptions(args)
        # except UsageError as e:
        #     raise SystemExit(e)
        self.prepare()
