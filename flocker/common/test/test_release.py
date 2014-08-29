# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

from twisted.python.usage import UsageError
from twisted.python.versions import Version
from twisted.trial.unittest import TestCase

from zope.interface.verify import verifyObject

from .._release import (
    flocker_version, ReleaseOptions, FakeVersionControl, IVersionControl)


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


def make_version_control_tests(api):
    """
    """
    class VersionControlTests(TestCase):
        """
        Tests for the supplied ``api``.
        """
        def test_interface(self):
            """
            ``api`` provides ``IVersionControl``.
            """
            self.assertTrue(verifyObject(IVersionControl, api))

    return VersionControlTests


class FakeVersionControlTests(make_version_control_tests(FakeVersionControl())):
    """
    Tests for ``FakeVersionControl``.
    """
