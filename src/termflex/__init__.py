from .glossary import Glossary
from .checker import Checker, TermMatch, RenderedTermMatch
from .lemmatizers import available_backends, backends_for
from .io.io import check_file, process_many, print_report, save_json, summarize

__all__ = ["Glossary", "Checker", "TermMatch", "RenderedTermMatch",
           "check_file", "process_many", "print_report", "save_json",
           "summarize", "available_backends", "backends_for"]
__version__ = "0.0.1"
