# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

from twisted.python.versions import Version
from twisted.trial.unittest import TestCase

from .._release import flocker_version, ReleaseOptions

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
        expected_version = b'0.2.0'
        options = ReleaseOptions()
        options.parseOptions([expected_version])
        self.assertEqual(expected_version, options['version'])

    def test_prerelease(self):
        """
        ``flocker-release`` accepts a *pre-release* option whose value is the
        pre-release number stored as ``prerelease_version``.
        """
        expected_prerelease_version = '1'
        options = ReleaseOptions()
        options.parseOptions(
            [b'--pre-release=%s' % (expected_prerelease_version,), b'0.2.0']
        )
        self.assertEqual(expected_prerelease_version, options['prerelease_version'])

    def test_structured_version(self):
        """
        """
        
