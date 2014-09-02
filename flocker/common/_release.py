# Copyright Hybrid Logic Ltd.  See LICENSE file for details.
# -*- test-case-name: flocker.common.test.test_release -*-

"""
Tools for releasing Flocker.
"""
if __name__ == '__main__':
    from flocker.common._release import flocker_release_main
    flocker_release_main()

import sys
from subprocess import check_output

from twisted.python.filepath import FilePath
from twisted.python.usage import Options, UsageError
from twisted.python.versions import Version

from zope.interface import Interface, implementer

from flocker.common.script import flocker_standard_options

PACKAGE_NAME = 'Flocker'


def flocker_version(major, minor, micro, prerelease=None):
    """
    Make a ``Version`` with a fixed package name of 'Flocker'.
    """
    return Version(PACKAGE_NAME, major, minor, micro, prerelease)


class VersionError(Exception):
    """
    Raised when version parsing fails.
    """


def flocker_version_from_string(version_string):
    """
    Parse a version string into a structured ``Version`` object.
    """
    raw_version_string = version_string
    prerelease = None
    parts = version_string.split('pre', 1)
    if len(parts) == 2:
        version_string, prerelease_version_string = parts
        try:
            prerelease = int(prerelease_version_string)
        except ValueError:
            raise VersionError(
                'Pre-release must be an integer. '
                'Found {}'.format(raw_version_string))

    parts = version_string.split('.', 2)
    if len(parts) != 3:
        raise VersionError(
            'Version must be of the form x.y.z. '
            'Found {}'.format(raw_version_string))
    try:
        major, minor, micro = [int(v) for v in parts]
    except ValueError:
        raise VersionError(
            'Version components must be integers. '
            'Found {}'.format(raw_version_string))

    return flocker_version(major, minor, micro, prerelease=prerelease)
    

@flocker_standard_options
class ReleaseOptions(Options):
    """
    Command line options for the flocker-release tool.
    """
    synopsis = b'Usage: flocker-release [options] <version>'

    def opt_pre_release(self, prerelease):
        """
        Specify the pre-release version.
        """
        try:
            self['prerelease'] = int(prerelease)
        except ValueError:
            raise UsageError(
                'Pre-release must be an integer. Found {}'.format(prerelease))

    def parseArgs(self, version_string):
        """
        Parse the version string.
        """
        self['version_string'] = version_string

    def postOptions(self):
        """
        Combine the version components into a ``Version`` instance.
        """
        try:
            self['version'] = flocker_version_from_string(
                self['version_string'])
        except VersionError as e:
            raise UsageError(str(e))


class IVersionControl(Interface):
    """
    Version control operations for use in the release process.
    """
    def uncommitted():
        """
        Return a list of uncommitted changes.
        """

    def branch(name=None):
        """
        Return the current branch name or create a new branch if ``name`` is
        supplied.
        """

    def branches():
        """
        Return a list of branch names.
        """

    def push(name, remote):
        """
        Push the named branch to remote.
        """

    def checkout(name):
        """
        Checkout the branch with ``name``.
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
        self._current_branch = 'master'

    def uncommitted(self):
        return [self._root.preauthChild(f) for f in self._uncommitted]

    def branch(self, name=None):
        if name is not None:
            self._branches['local'].append(name)
        return self._current_branch

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

    def checkout(self, name):
        if name not in self.branches() + self.branches(remote='origin'):
            raise ReleaseError('Unknown branch {}'.format(name))
        self._current_branch = name


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
                f = self._root.preauthChild(relative_path)
                uncommitted.append(f)
        return uncommitted

    def branch(self, name=None):
        if name is not None:
            check_output(
                ['git', 'branch', '--quiet', name, 'origin/master'],
                cwd=self._root.path)
        output = check_output('git branch --list'.split(), cwd=self._root.path)
        for line in output.splitlines():
            if line.startswith('*'):
                return line.lstrip('* ')

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

    def checkout(self, name):
        if name not in self.branches() + self.branches(remote='origin'):
            raise ReleaseError('Unknown branch {}'.format(name))
        check_output(
            'git checkout --quiet {}'.format(name).split(),
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
        self._sys_module = sys

    def _branchname(self):
        """
        Return the branchname for the given release.
        """
        version = self.options['version']
        return 'release/flocker-%s.%s' % (version.major, version.minor)

    def _checkout(self):
        """
        Checkout a new release branch for major versions or an existing branch
        for patch versions.
        """
        uncommitted = self.vc.uncommitted()
        if uncommitted:
            raise ReleaseError(
                'Uncommitted changes found: {}'.format(
                    ','.join(f.path for f in uncommitted)))
        version = self.options['version']
        branchname = self._branchname()
        if version.micro == 0 and version.prerelease == 1:
            # Only create and push a release branch if this is the first
            # pre-release of a major or minor release. Fail if an existing
            # branch is found.
            if branchname in self.vc.branches(remote='origin'):
                raise ReleaseError(
                    'Existing branch {} found '
                    'but major or minor first pre-release, '
                    '{} requested.'.format(
                        branchname, version.base()))
            self.vc.branch(branchname)
            self.vc.push(branchname, 'origin')
        else:
            if branchname not in self.vc.branches(remote='origin'):
                raise ReleaseError(
                    'Existing branch {} not found '
                    'for release {}'.format(
                        branchname, version.base()))
        self.vc.checkout(branchname)

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

    def main(self, argv=None):
        """
        Parse options and take action.
        """
        try:
            self.options.parseOptions(argv)
        except UsageError as e:
            self._sys_module.stderr.write(
                b'ERROR: %s\n' % (unicode(e).encode('utf8'),))
            raise SystemExit(1)
        try:
            self.prepare()
        except ReleaseError as e:
            self._sys_module.stderr.write(
                b'ERROR: %s\n' % (unicode(e).encode('utf8'),))
            raise SystemExit(1)


flocker_release_main = ReleaseScript().main
