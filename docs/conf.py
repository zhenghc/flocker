# -*- coding: utf-8 -*-
#
# Flocker documentation build configuration file, created by
# sphinx-quickstart on Mon Apr 28 14:54:33 2014.
#
# This file is execfile()d with the current directory set to its containing dir.
#
# Note that not all possible configuration values are present in this
# autogenerated file.
#
# All configuration values have a default; values that are commented out
# serve to show the default.

from twisted.python.filepath import FilePath

import sys
import os

sys.path.insert(0, FilePath(__file__).parent().parent().path)

# Check if we are building on readthedocs
on_rtd = os.environ.get('READTHEDOCS', None) == 'True'

# -- General configuration -----------------------------------------------------

# If your documentation needs a minimal Sphinx version, state it here.
#needs_sphinx = '1.0'

# Add any Sphinx extension module names here, as strings. They can be extensions
# coming with Sphinx (named 'sphinx.ext.*') or your custom ones.
extensions = [
    'sphinx.ext.extlinks',
    'sphinx.ext.intersphinx',
    'sphinx.ext.ifconfig',
    'flocker.provision._sphinx',
    'flocker.docs.version_extensions',
    'sphinx-prompt',
    'sphinxcontrib.httpdomain',
    'flocker.restapi.docs.publicapi',
    'flocker.restapi.docs.hidden_code_block',
    'flocker.docs.bootstrap',
]

if not on_rtd:
    # readthedocs doesn't install dependencies
    extensions.append('sphinxcontrib.spelling')

# Add any paths that contain templates here, relative to this directory.
templates_path = ['_templates']

# The suffix of source filenames.
source_suffix = '.rst'

# The encoding of source files.
#source_encoding = 'utf-8-sig'

# The master toctree document.
master_doc = 'index'

# General information about the project.
project = u'Flocker'
copyright = u'2014, ClusterHQ'

extlinks = {
    'issue': ('https://clusterhq.atlassian.net/browse/FLOC-%s', 'issue '),
}

# The version info for the project you're documenting, acts as replacement for
# |version| and |release|, also used in various other places throughout the
# built documents.
#
from flocker import __version__
from flocker.common.version import get_doc_version, is_release
# The short X.Y version.
version = get_doc_version(__version__)

html_context = {
    # This is used to show the development version warning.
    'is_release': is_release(__version__),
}

# The full version, including alpha/beta/rc tags.
release = version

# The language for content autogenerated by Sphinx. Refer to documentation
# for a list of supported languages.
# We override with our own variant to improve search results slightly.
from sphinx.search.en import SearchEnglish
from sphinx.search import languages as sphinx_languages


class FlockerLanguage(SearchEnglish):
    """
    Workaround for https://bitbucket.org/birkenfeld/sphinx/issue/1529/
    """
    def word_filter(self, word):
        """
        Only omit stop words; default also omits words shorter than 3
        characters which breaks search for "ZFS" since stemming turns that into
        "zf".
        """
        return word not in self.stopwords

# Read The Docs may override the language, which is why we're overriding
# English rather than defining our own language.
sphinx_languages['en'] = FlockerLanguage
language = 'en'

# String specifying a file containing a list of words known to be spelled
# correctly but that do not appear in the language dictionary.
# See:
# http://sphinxcontrib-spelling.readthedocs.org/en/latest/customize.html#input-options
spelling_word_list_filename = 'spelling_wordlist.txt'

if not on_rtd:
    sys.path.insert(0, FilePath(__file__).parent().path)
    from filters import IgnoreWordsFilterFactory
    # Don't spell check the version:
    spelling_filters = [IgnoreWordsFilterFactory(words={version})]
    del sys.path[0]

# There are two options for replacing |today|: either, you set today to some
# non-false value, then it is used:
#today = ''
# Else, today_fmt is used as the format for a strftime call.
#today_fmt = '%B %d, %Y'

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
exclude_patterns = ['_build']

# The reST default role (used for this markup: `text`) to use for all documents.
#default_role = None

# If true, '()' will be appended to :func: etc. cross-reference text.
#add_function_parentheses = True

# If true, the current module name will be prepended to all description
# unit titles (such as .. function::).
#add_module_names = True

# If true, sectionauthor and moduleauthor directives will be shown in the
# output. They are ignored by default.
#show_authors = False

# The name of the Pygments (syntax highlighting) style to use.
pygments_style = 'sphinx'

# A list of ignored prefixes for module index sorting.
#modindex_common_prefix = []


# -- Options for HTML output ---------------------------------------------------

# The HTMLTranslator class
html_translator_class = 'flocker.docs.bootstrap.HTMLWriter'
# The theme to use for HTML and HTML Help pages.  See the documentation for
# a list of builtin themes.
html_theme = 'clusterhq'

# Theme options are theme-specific and customize the look and feel of a theme
# further.  For a list of options available for each theme, see the
# documentation.
#html_theme_options = {}

# Add any paths that contain custom themes here, relative to this directory.
html_theme_path = ['_themes']

# The name for this set of Sphinx documents.  If None, it defaults to
# "<project> v<release> documentation".
#html_title = None

# A shorter title for the navigation bar.  Default is the same as html_title.
#html_short_title = None

# The name of an image file (relative to this directory) to place at the top
# of the sidebar.
#html_logo = None

# The name of an image file (within the static path) to use as favicon of the
# docs.  This file should be a Windows icon file (.ico) being 16x16 or 32x32
# pixels large.
#html_favicon = None

# Add any paths that contain custom static files (such as style sheets) here,
# relative to this directory. They are copied after the builtin static files,
# so a file named "default.css" will overwrite the builtin "default.css".
html_static_path = ['_static']

# If not '', a 'Last updated on:' timestamp is inserted at every page bottom,
# using the given strftime format.
#html_last_updated_fmt = '%b %d, %Y'

# If true, SmartyPants will be used to convert quotes and dashes to
# typographically correct entities.
#html_use_smartypants = True

# Custom sidebar templates, maps document names to template names.
#html_sidebars = {}

# Additional templates that should be rendered to pages, maps page names to
# template names.
#html_additional_pages = {}

# If false, no module index is generated.
#html_domain_indices = True

# If false, no index is generated.
html_use_index = False

# If true, the index is split into individual pages for each letter.
#html_split_index = False

# If true, links to the reST sources are added to the pages.
#html_show_sourcelink = True

# If true, "Created using Sphinx" is shown in the HTML footer. Default is True.
#html_show_sphinx = True

# If true, "(C) Copyright ..." is shown in the HTML footer. Default is True.
#html_show_copyright = True

# If true, an OpenSearch description file will be output, and all pages will
# contain a <link> tag referring to it.  The value of this option must be the
# base URL from which the finished HTML is served.
#html_use_opensearch = ''

# This is the file name suffix for HTML files (e.g. ".xhtml").
#html_file_suffix = None

# Output file base name for HTML help builder.
htmlhelp_basename = 'Flockerdoc'


# -- Options for LaTeX output --------------------------------------------------

latex_elements = {
# The paper size ('letterpaper' or 'a4paper').
#'papersize': 'letterpaper',

# The font size ('10pt', '11pt' or '12pt').
#'pointsize': '10pt',

# Additional stuff for the LaTeX preamble.
#'preamble': '',
}

# Grouping the document tree into LaTeX files. List of tuples
# (source start file, target name, title, author, documentclass [howto/manual]).
latex_documents = [
  ('index', 'Flocker.tex', u'Flocker Documentation',
   u'ClusterHQ', 'manual'),
]

# The name of an image file (relative to this directory) to place at the top of
# the title page.
#latex_logo = None

# For "manual" documents, if this is true, then toplevel headings are parts,
# not chapters.
#latex_use_parts = False

# If true, show page references after internal links.
#latex_show_pagerefs = False

# If true, show URL addresses after external links.
#latex_show_urls = False

# Documents to append as an appendix to all manuals.
#latex_appendices = []

# If false, no module index is generated.
#latex_domain_indices = True


# -- Options for manual page output --------------------------------------------

# One entry per manual page. List of tuples
# (source start file, name, description, authors, manual section).
man_pages = [
    ('index', 'flocker', u'Flocker Documentation',
     [u'ClusterHQ'], 1)
]

# If true, show URL addresses after external links.
#man_show_urls = False


# -- Options for Texinfo output ------------------------------------------------

# Grouping the document tree into Texinfo files. List of tuples
# (source start file, target name, title, author,
#  dir menu entry, description, category)
texinfo_documents = [
  ('index', 'Flocker', u'Flocker Documentation',
   u'ClusterHQ', 'Flocker', 'Data-oriented Docker clustering.',
   'Miscellaneous'),
]

# Documents to append as an appendix to all manuals.
#texinfo_appendices = []

# If false, no module index is generated.
#texinfo_domain_indices = True

# How to display URL addresses: 'footnote', 'no', or 'inline'.
#texinfo_show_urls = 'footnote'


# Example configuration for intersphinx: refer to the Python standard library.
intersphinx_mapping = {'http://docs.python.org/': None}

# Don't check anchors because many websites use #! for AJAX magic
# http://sphinx-doc.org/config.html#confval-linkcheck_anchors
linkcheck_anchors = False

linkcheck_ignore = [
    # Don't check links to tutorial IPs
    r'http://172\.16\.255\.',
    # Example comparisons between branches
    r'https://github.com/ClusterHQ/flocker/compare/\S+',
    # Some Amazon EC2 links require a login and so
    # "HTTP Error 401: Unauthorized" is given.
    r'https://console.aws.amazon.com/cloudfront/home',
    r'https://console.aws.amazon.com/ec2/v2/home\S+',
    # Internal ClusterHQ documents need a login to see
    r'https://docs.google.com/a/clusterhq.com/\S+',
    # Example Flocker GUI local URL
    r'http://localhost/client/#/nodes/list',

    # The following link checks fail because of a TLS handshake error.
    # The link checking should be fixed and these ignores should be removed.
    # See https://clusterhq.atlassian.net/browse/FLOC-1156.
    r'https://docs.clusterhq.com/',
    r'https://docs.staging.clusterhq.com/',
    r'https://docs.docker.com/\S+',
]
