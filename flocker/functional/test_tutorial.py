# Copyright Hybrid Logic Ltd.  See LICENSE file for details.

"""
Acceptance tests for the Flocker tutorial
"""

from wordish import (
    TestReporter, BlockSelector, ShellSessionParser, CommandRunner)

from twisted.python.filepath import FilePath
from twisted.trial.unittest import TestCase


def assert_wordish(test_case, docfile):
    report = TestReporter()
    filter = BlockSelector(directive='code-block', arg=['console'])
    session = iter(
        ShellSessionParser(
            filter(docfile.open()),
            prompts=['alice@mercury:~/flocker-tutorial$ ']
        )
    )

    with CommandRunner() as run:
        for cmd, expected in session:
            print report.before( cmd, expected )
            print report.after( run( cmd ) )

            if report.last_output.aborted():
                # sole condition if expected.returncode is None if
                # expected returncode is not None and expected!=actual
                # output should bailout. Test and errors should be
                # different.
                print( "Command aborted, bailing out")
                remaining_cmds = [ cmd for cmd, _ in session ]
                if len( remaining_cmds )==0:
                    print( "No remaining command" )
                else:
                    print "Untested command%s:\n\t" % (
                        "s" if len( remaining_cmds )>1 else ""  ),
                    print( "\n\t".join( remaining_cmds ))


docs = FilePath(__file__).parent().parent().parent().child('docs')

class MovingApplicationsTests(TestCase):
    """
    """

    def test_all(self):
        """
        """
        tutorial = docs.child('gettingstarted').child('tutorial').child('moving-applications.rst')

        assert_wordish(self, tutorial)
