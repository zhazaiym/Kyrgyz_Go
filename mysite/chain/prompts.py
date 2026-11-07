"""Compatibility import; implementation lives in ML.prompts."""

import sys
from importlib import import_module

sys.modules[__name__] = import_module('ML.prompts')
