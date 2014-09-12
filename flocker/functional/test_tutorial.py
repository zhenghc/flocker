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


documentation_root = FilePath(__file__).parent().parent().parent().child('docs')

def make_documentation_test(document_relative_path):

    document = documentation_root.preauthChild(document_relative_path)

    class WordishTest(TestCase):
        """
        """

        def setUp(self):
            """
            """
            if not document.exists():
                self.fail('Document not found {}'.format(document.path))

        def test_all(self):
            """
            """
            assert_wordish(self, document)

    return WordishTest

class MovingApplicationsTests(
        make_documentation_test(
            'gettingstarted/tutorial/moving-applications.rst')):
    """
    Tests for ``gettingstarted/tutorial/moving-applications.rst``
    """
