# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Tests for release tools.
"""

from os import devnull
from subprocess import check_call, check_output, STDOUT, CalledProcessError
from unittest import skipUnless

from twisted.python.filepath import FilePath
from twisted.python.procutils import which
from twisted.python.usage import UsageError
from twisted.python.versions import Version
from twisted.trial.unittest import TestCase

from zope.interface.verify import verifyObject

from ... import __version__

from ...testtools import FakeSysModule, StandardOptionsTestsMixin

from .._release import (
    flocker_version, ReleaseScript, ReleaseOptions, FakeVersionControl,
    IVersionControl, VersionControl, ReleaseError
)

DEBUG = False


_require_installed = skipUnless(which("flocker-release"),
                                "flocker-release not installed")


class FlockerVersionTests(TestCase):
    """
    Tests for ``flocker_version``.
    """
    def test_version(self):
        """
        ``flocker_version`` returns a ``Version`` object.
        """
        self.assertIsInstance(flocker_version(0, 0, 0), Version)

    def test_package(self):
        """
        The returned version has a package name of *Flocker*.
        """
        self.assertEqual('Flocker', flocker_version(0, 0, 0).package)


class StandardOptionsTests(StandardOptionsTestsMixin, TestCase):
    """
    Test that ``ReleaseOptions`` is decorated with
    ``flocker_standard_options``.
    """
    options = ReleaseOptions


class ReleaseOptionsTests(TestCase):
    """
    Tests for ``ReleaseOptions``.
    """
    def test_synopsis(self):
        """
        """
        options = ReleaseOptions()
        self.assertEqual(
            b'Usage: flocker-release [options] <version>',
            str(options).splitlines()[0])

    def test_version(self):
        """
        ``flocker-release`` requires a *version* as the first positional
        argument and stores this as ``version``.
        """
        expected_version = flocker_version(0, 2, 0)
        expected_version_string = b'0.2.0'
        options = ReleaseOptions()
        options.parseOptions([expected_version_string])
        self.assertEqual(expected_version, options['version'])

    def test_version_non_missing_component(self):
        """
        ``UsageError`` is raised if the supplied version is not of the form
        x.y.z.
        """
        options = ReleaseOptions()

        error = self.assertRaises(UsageError, options.parseOptions, ['0.50'])
        self.assertEqual(
            'Version must be of the form x.y.z. Found 0.50', str(error))

    def test_version_non_int(self):
        """
        ``UsageError`` is raised if the supplied version components cannot be
        cast to ``int``.
        """
        options = ReleaseOptions()

        error = self.assertRaises(UsageError, options.parseOptions, ['x.y.z'])
        self.assertEqual(
            'Version components must be integers. Found x.y.z', str(error))

    def test_prerelease(self):
        """
        ``flocker-release`` accepts a *pre-release* option whose value is the
        pre-release number stored as ``prerelease_version``.
        """
        expected_version = flocker_version(0, 2, 0, prerelease=1)
        options = ReleaseOptions()
        options.parseOptions(
            [b'--pre-release=1', b'0.2.0']
        )
        self.assertEqual(expected_version, options['version'])

    def test_prerelease_non_int(self):
        """
        ``UsageError`` is raised if the supplied prerelease cannot be cast to
        ``int``.
        """
        options = ReleaseOptions()

        error = self.assertRaises(
            UsageError,
            options.parseOptions, [b'--pre-release=x', '0.0.0'])
        self.assertEqual(
            'Pre-release must be an integer. Found x', str(error))


def make_version_control_tests(make_api, setup_environment):
    """
    """
    class VersionControlTests(TestCase):
        """
        Tests for the supplied ``api``.
        """
        def setUp(self):
            self.root = FilePath(self.mktemp())
            self.api = make_api(root=self.root)
            self.uncommitted = [
                b'uncommitted_file', b'uncommitted_dir/another_file']
            self.local_branches = [
                b'master', b'local_branch1', b'local_branch2']
            self.origin_branches = [
                b'HEAD', b'master', b'origin_branch1', b'origin_branch2']
            setup_environment(
                self, self.root, self.api,
                uncommitted=self.uncommitted,
                local_branches=self.local_branches,
                origin_branches=self.origin_branches
            )

        def test_interface(self):
            """
            ``api`` provides ``IVersionControl``.
            """
            self.assertTrue(verifyObject(IVersionControl, self.api))

        def test_uncommitted(self):
            """
            ``uncommitted`` returns a list of uncommitted files.
            """
            self.assertEqual(
                set([self.root.preauthChild(f) for f in self.uncommitted]),
                set(self.api.uncommitted())
            )

        def test_branch_new(self):
            """
            ``branch`` creates a new branch from origin master with the
            supplied name.
            """
            expected_branch = b'release/flocker-0.2'
            self.api.branch(expected_branch)
            self.assertIn(expected_branch, self.api.branches())

        def test_branch_current(self):
            """
            ``branch`` returns the name of the current checked out branch.
            """
            expected_branch = b'release/flocker-0.2'
            self.api.branch(expected_branch)
            self.assertIn(expected_branch, self.api.branches())

        def test_branches(self):
            """
            ``branches`` without an argument returns a list of local branch
            names.
            """
            expected_branches = set(self.local_branches)
            actual_branches = set(self.api.branches())
            self.assertEqual(expected_branches, actual_branches)

        def test_branches_remote(self):
            """
            ``branches`` with a remote argument returns a list of local branch
            names in the remote repository.
            """
            expected_branches = set(self.origin_branches)
            actual_branches = set(self.api.branches(remote='origin'))
            self.assertEqual(expected_branches, actual_branches)

        def test_branches_remote_unknown(self):
            """
            ``branches`` with an unknown remote argument raises an exception.
            """
            error = self.assertRaises(
                ReleaseError, self.api.branches, remote='foobar')
            self.assertEqual('Unknown remote foobar', str(error))

        def test_push_remote_unknown(self):
            """
            ``push`` with an unknown remote argument raises an exception.
            """
            self.api.branch('known_branch')
            error = self.assertRaises(
                ReleaseError,
                self.api.push, 'known_branch', remote='unknown_remote')
            self.assertEqual('Unknown remote unknown_remote', str(error))

        def test_push_branch_unknown(self):
            """
            ``push`` with an unknown remote argument raises an exception.
            """
            error = self.assertRaises(
                ReleaseError,
                self.api.push, 'unknown_branch', remote='origin')
            self.assertEqual('Unknown branch unknown_branch', str(error))

        def test_push(self):
            """
            ``push`` creates a remote branch from a local branch.
            """
            expected_branch = b'release/flocker-0.2'
            remote = 'origin'
            self.api.branch(expected_branch)
            self.api.push(expected_branch, remote)
            self.assertIn(expected_branch, self.api.branches(remote=remote))

        def test_checkout(self):
            """
            ``checkout`` checks out the branch with the given ``name``.
            """
            expected_branch = b'release/flocker-0.2'
            self.api.branch(name=expected_branch)
            self.api.checkout(name=expected_branch)
            self.assertEqual(expected_branch, self.api.branch())

        def test_checkout_unknown_branch(self):
            """
            ``checkout`` raises ``ReleaseError`` if there is no branch with the
            given ``name``.
            """
            expected_branch = b'release/flocker-0.2'
            exception = self.assertRaises(
                ReleaseError, self.api.checkout, name=expected_branch)
            self.assertEqual(
                'Unknown branch release/flocker-0.2', str(exception))

    return VersionControlTests


def fake_environment(test, root, api, uncommitted, local_branches,
                     origin_branches):
    """
    Populate a ``FakeVersionControl`` so that it can be tested.
    """
    api._uncommitted = uncommitted
    api._branches['local'] = local_branches
    api._branches['origin'] = origin_branches


class FakeVersionControlTests(
        make_version_control_tests(
            FakeVersionControl,
            setup_environment=fake_environment
        )
):
    """
    Tests for ``FakeVersionControl``.
    """


def git(args, cwd=None):
    with open(devnull, 'w') as discard:
        stdout, stderr = discard, discard
        if DEBUG:
            stdout, stderr = None, None

        check_call(
            [b'git'] + args, cwd=cwd,
            stdout=stdout, stderr=stderr)


def git_working_directory(test, root, api, uncommitted, local_branches,
                          origin_branches):
    """
    Create a git repo and a clone for use in functional tests.
    """
    server_root = FilePath(test.mktemp())
    server_root.createDirectory()

    # Use a local repo to simulate a remote
    git('init --quiet .'.split(), cwd=server_root.path)

    # Create a file and commit it
    server_root.child('README').setContent('README')

    git('add README'.split(), cwd=server_root.path)
    git(['commit', '-m', 'add README'], cwd=server_root.path)

    # Create some branches
    for b in origin_branches:
        if b in (b'HEAD', b'master'):
            continue
        git('branch {}'.format(b).split(), cwd=server_root.path)

    # Checkout the remote to root
    git('clone {} {}'.format(server_root.path, root.path).split())

    # Create some local branches
    for b in local_branches:
        if b in (b'HEAD', b'master'):
            continue
        git('branch {}'.format(b).split(), cwd=root.path)

    # Switch back to master
    git('checkout master'.split(), cwd=root.path)

    for f in uncommitted:
        child = root.preauthChild(f)
        if '/' in f:
            parent = child.parent()
            # Git doesn't track empty directories so add a file.
            parent.makedirs()
            parent.child('first_file_in_directory').create()
            git('add {}'.format(parent.path).split(), cwd=root.path)
            git(
                ['commit', '-am', 'add uncommitted file directories'],
                cwd=root.path)
        child.create()


class VersionControlTests(
        make_version_control_tests(
            VersionControl,
            setup_environment=git_working_directory
        )
):
    """
    Tests for ``VersionControl``.
    """


class ReleaseScriptTests(TestCase):
    """
    Tests for default attributes of ``ReleaseScript``.
    """
    def test_options_default(self):
        """
        ``ReleaseScript._options`` is an instance of ``ReleaseOptions`` by
        default.
        """
        self.assertIsInstance(ReleaseScript().options, ReleaseOptions)

    def test_vc_default(self):
        """
        ``ReleaseScript._vc`` is ``VersionControl`` by default.
        """
        self.assertIsInstance(ReleaseScript().vc, VersionControl)


class ReleaseScriptBranchNameTests(TestCase):
    """
    Tests for ``ReleaseScript._branchname``.
    """
    def test_major(self):
        """
        The branchname for a major release includes the major and minor
        components only.
        """
        script = ReleaseScript()
        script.options.parseOptions([b'1.0.0'])
        self.assertEqual('release/flocker-1.0', script._branchname())

    def test_minor(self):
        """
        The branchname for a minor release includes the major and minor
        components only.
        """
        script = ReleaseScript()
        script.options.parseOptions([b'1.1.0'])
        self.assertEqual('release/flocker-1.1', script._branchname())

    def test_patch(self):
        """
        The branchname for a patch release includes the major and minor
        components only.
        """
        script = ReleaseScript()
        script.options.parseOptions([b'1.1.1'])
        self.assertEqual('release/flocker-1.1', script._branchname())


class ReleaseScriptCheckoutTests(TestCase):
    """
    Tests for ``ReleaseScript._checkout``.
    """
    def test_error_if_uncommitted_changes(self):
        """
        An error is raised if the working directory contains uncommitted
        changes.
        """
        script = ReleaseScript()
        script.options.parseOptions([b'0.2.0'])
        root = FilePath('.')
        script.vc = FakeVersionControl(root)
        script.vc._uncommitted.append('SRPMS')
        error = self.assertRaises(ReleaseError, script._checkout)
        self.assertEqual(
            'Uncommitted changes found: {}'.format(root.child('SRPMS').path),
            str(error)
        )

    def test_first_non_patch_prerelease_existing_branch(self):
        """
        An error is raised if an existing branch is found when a major or minor
        pre-release1 is requested.
        """
        script = ReleaseScript()
        script.options.parseOptions(['--pre-release=1', b'0.2.0'])
        script.vc = FakeVersionControl('.')
        script.vc.branch(script._branchname())
        script.vc.push(script._branchname(), 'origin')
        error = self.assertRaises(ReleaseError, script._checkout)
        self.assertEqual(
            'Existing branch release/flocker-0.2 found '
            'but major or minor first pre-release, 0.2.0pre1 requested.',
            str(error)
        )

    def test_first_non_patch_prerelease_branch_created(self):
        """
        A major or minor first pre-release will result in the creation of a new
        release branch.
        """
        script = ReleaseScript()
        script.options.parseOptions([b'--pre-release=1', b'0.2.0'])
        script.vc = FakeVersionControl('.')
        script._checkout()
        self.assertEqual(script._branchname(), script.vc.branch())

    def test_first_non_patch_prerelease_branch_pushed(self):
        """
        The new branch will be pushed to origin.
        """
        script = ReleaseScript()
        script.options.parseOptions([b'--pre-release=1', b'0.2.0'])
        script.vc = FakeVersionControl('.')
        script._checkout()
        self.assertIn(
            script._branchname(), script.vc.branches(remote='origin'))

    def test_patch_release_missing_branch(self):
        """
        An error is raised if a patch release is requested, but an existing
        branch is not found.
        """
        script = ReleaseScript()
        script.options.parseOptions([b'0.2.1'])
        script.vc = FakeVersionControl('.')
        error = self.assertRaises(ReleaseError, script._checkout)
        self.assertEqual(
            'Existing branch release/flocker-0.2 not found '
            'for release 0.2.1',
            str(error)
        )

    def test_patch_release_existing_branch(self):
        """
        An existing branch is checked out for a patch release.
        """
        script = ReleaseScript()
        script.options.parseOptions([b'0.2.1'])
        script.vc = FakeVersionControl('.')
        branch_name = 'release/flocker-0.2'
        script.vc.branch(name=branch_name)
        script.vc.push(branch_name, 'origin')
        script._checkout()
        self.assertEqual(script._branchname(), script.vc.branch())

    def test_subsequent_prerelease_missing_branch(self):
        """
        An error is raised if a followup pre-release is requested, but an
        existing branch is not found.
        """
        script = ReleaseScript()
        script.options.parseOptions([b'--pre-release=2', b'0.2.0'])
        script.vc = FakeVersionControl('.')
        error = self.assertRaises(ReleaseError, script._checkout)
        self.assertEqual(
            'Existing branch release/flocker-0.2 not found '
            'for release 0.2.0pre2',
            str(error)
        )

    def test_subsequent_prerelease_existing_branch(self):
        """
        An existing branch is checked out for a subsequent pre-release.
        """
        script = ReleaseScript()
        script.options.parseOptions([b'--pre-release=2', b'0.2.0'])
        script.vc = FakeVersionControl('.')
        branch_name = 'release/flocker-0.2'
        script.vc.branch(name=branch_name)
        script.vc.push(branch_name, 'origin')
        script._checkout()
        self.assertEqual(script._branchname(), script.vc.branch())


class ReleaseScriptMainTests(TestCase):
    """
    Tests for ``ReleaseScript.main``.
    """
    def test_usage_error_status(self):
        """
        ``ReleaseScript.main`` raises ``SystemExit`` if the supplied options
        result in a ``UsageError``.
        """
        # Supply an invalid version string to trigger a usage error
        exception = self.assertRaises(
            SystemExit, ReleaseScript().main, [b'x.y.z'])
        self.assertEqual(1, exception.code)

    def test_usage_error_message(self):
        """
        ``ReleaseScript.main`` prints ``UsageError``s to stderr.
        """
        script = ReleaseScript()
        sys_module = FakeSysModule()
        script._sys_module = sys_module
        # Supply an invalid version string to trigger a usage error
        self.assertRaises(
            SystemExit, script.main, [b'x.y.z'])
        self.assertEqual(
            b'ERROR: Version components must be integers. Found x.y.z\n',
            sys_module.stderr.getvalue()
        )

    def test_prepare(self):
        """
        ``ReleaseScript.main`` calls ``prepare`` without any arguments.
        """
        script = ReleaseScript()
        prepare_calls = []
        self.patch(
            script, 'prepare', lambda *a, **kw: prepare_calls.append((a, kw)))
        script.main([b'0.1.0'])
        self.assertEqual([((), {})], prepare_calls)

    def test_release_error_status(self):
        """
        ``ReleaseScript.main`` raises ``SystemExit`` if the prepare method
        raises ``ReleaseError``.
        """
        # Supply a bad
        script = ReleaseScript()

        def failing_prepare():
            raise ReleaseError('fake release failure')
        self.patch(script, 'prepare', failing_prepare)
        exception = self.assertRaises(
            SystemExit, script.main, [b'0.0.1'])
        self.assertEqual(1, exception.code)

    def test_release_error_message(self):
        """
        ``ReleaseScript.main`` raises ``SystemExit`` if the prepare method
        raises ``ReleaseError``.
        """
        # Supply a bad
        script = ReleaseScript()
        sys_module = FakeSysModule()
        script._sys_module = sys_module

        def failing_prepare():
            raise ReleaseError('fake release failure')
        self.patch(script, 'prepare', failing_prepare)
        self.assertRaises(
            SystemExit, script.main, [b'0.0.1'])
        self.assertEqual(
            b'ERROR: fake release failure\n', sys_module.stderr.getvalue())


class ReleaseScriptPrepareTests(TestCase):
    """
    Tests for ``ReleaseScript.prepare``.
    """
    def test_order_of_operations(self):
        """
        ``ReleaseScript.prepare`` calls ``_checkout`` without any arguments.
        """
        script = ReleaseScript()
        calls = []
        self.patch(
            script, '_checkout',
            lambda *a, **kw: calls.append(('_checkout', a, kw)))
        script.prepare()
        self.assertEqual(
            [('_checkout', (), {})],
            calls
        )


class ReleaseScriptFunctionalTests(TestCase):
    """
    Tests for ``flocker-release``.
    """
    @_require_installed
    def setUp(self):
        pass

    def test_version(self):
        """
        ``flocker-release`` command is installed on the system path.
        """
        output = check_output(['flocker-release', '--version'])
        self.assertEqual(b"%s\n" % (__version__,), output)

    def test_error_if_uncommitted_changes(self):
        """
        An error is raised if the working directory contains uncommitted
        changes.
        """
        root = FilePath(self.mktemp())
        git_working_directory(
            test=self, root=root, api=None,
            uncommitted=['SRPMS'], local_branches=[], origin_branches=[])
        exception = self.assertRaises(
            CalledProcessError,
            check_output,
            ['flocker-release', '0.3.0'],
            cwd=root.path, stderr=STDOUT
        )
        self.assertEqual(
            'ERROR: Uncommitted changes found: {}\n'.format(
                root.child('SRPMS').path),
            exception.output
        )

    def test_patch_release_missing_branch(self):
        """
        ``flocker-release`` prints an error message if there isn't an existing
        release branch.
        """
        root = FilePath(self.mktemp())
        api = VersionControl(root=root)
        git_working_directory(
            test=self, root=root, api=api,
            uncommitted=[], local_branches=[], origin_branches=[])
        exception = self.assertRaises(
            CalledProcessError,
            check_output,
            ['flocker-release', '0.3.1'],
            cwd=root.path, stderr=STDOUT
        )
        self.assertEqual(
            b'ERROR: Existing branch release/flocker-0.3 not found '
            b'for release 0.3.1\n',
            exception.output)

    def test_patch_release_existing_branch(self):
        """
        ``flocker-release`` checks out an existing release branch.
        """
        root = FilePath(self.mktemp())
        api = VersionControl(root=root)
        expected_branch = 'release/flocker-0.3'
        git_working_directory(
            test=self, root=root, api=api,
            uncommitted=[], local_branches=[],
            origin_branches=[expected_branch])

        check_call(['flocker-release', '0.3.1'], cwd=root.path)

        self.assertEqual('release/flocker-0.3', api.branch())

    def test_major_prerelease1_existing_branch(self):
        """
        ``flocker-release`` exits with an error message if supplied with a
        major version number and pre-release version 1 and an existing release
        branch is found.
        """
        root = FilePath(self.mktemp())
        api = VersionControl(root=root)
        expected_branch = 'release/flocker-0.3'
        git_working_directory(
            test=self, root=root, api=api,
            uncommitted=[], local_branches=[],
            origin_branches=[expected_branch])

        exception = self.assertRaises(
            CalledProcessError,
            check_output,
            ['flocker-release', '--pre-release=1', '0.3.0'],
            cwd=root.path, stderr=STDOUT
        )

        self.assertEqual(
            b'ERROR: Existing branch release/flocker-0.3 found '
            b'but major or minor first pre-release, 0.3.0pre1 requested.\n',
            exception.output
        )

    def test_major_prerelease1_create_and_push_branch(self):
        """
        ``flocker-release`` creates a release branch and pushes it.
        """
        root = FilePath(self.mktemp())
        api = VersionControl(root=root)
        expected_branch = 'release/flocker-0.3'
        git_working_directory(
            test=self, root=root, api=api,
            uncommitted=[], local_branches=[],
            origin_branches=[])

        check_call(
            ['flocker-release', '--pre-release=1', '0.3.0'],
            cwd=root.path
        )

        self.assertEqual(expected_branch, api.branch())
        self.assertIn(expected_branch, api.branches(remote='origin'))
