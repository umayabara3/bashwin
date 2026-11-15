# -*- coding: utf-8 -*-
"""bashwin - Windows でも動く、純 Python 製の Bash 互換インタープリター。

使い方:
    python -m bashwin script.sh [args...]
    python -m bashwin -c 'echo hello'
    python -m bashwin -n script.sh          # 構文チェックのみ
"""
from .interp import Interp, VERSION  # noqa: F401
from .parser import parse, ParseError  # noqa: F401

__version__ = VERSION
