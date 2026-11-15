# -*- coding: utf-8 -*-
"""PowerShell 変換可能性の判定(互換用の入口)。

判定器と生成器は bashwin.ps_emit に一本化した。判定は「生成の空回し」なので、
判定結果と実際に変換できるかどうかが食い違うことはない。
"""
from __future__ import unicode_literals

from .ps_emit import check, check_file  # noqa: F401
