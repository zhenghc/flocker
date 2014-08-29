# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

from twisted.python.filepath import FilePath
from twisted.python.usage import UsageError
from twisted.python.versions import Version
from twisted.trial.unittest import TestCase

from zope.interface.verify import verifyObject

from .._release import (
    flocker_version, ReleaseOptions, FakeVersionControl, IVersionControl,
    VersionControl
)


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
            self.uncommitted = [b'foo']
            setup_environment(self.root, self.api, uncommitted=self.uncommitted)

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
                [self.root.child(f) for f in self.uncommitted],
                self.api.uncommitted()
            )

    return VersionControlTests


def fake_environment(root, api, uncommitted):
    api._uncommitted = uncommitted


class FakeVersionControlTests(
        make_version_control_tests(
            FakeVersionControl,
            setup_environment=fake_environment
        )
):
    """
    Tests for ``FakeVersionControl``.
    """

from subprocess import check_call

def git_working_directory(root, api, uncommitted):
    """
    """
    check_call('git init --quiet {}'.format(root.path).split())
    for f in uncommitted:
        root.child(f).create()


class VersionControlTests(
        make_version_control_tests(
            VersionControl,
            setup_environment=git_working_directory
        )
):
    """
    Tests for ``VersionControl``.
    """
