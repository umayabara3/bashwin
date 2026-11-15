# -*- coding: utf-8 -*-
"""制御フロー用の例外。"""


class ExitEx(Exception):
    def __init__(self, status):
        Exception.__init__(self, status)
        self.status = status


class ReturnEx(Exception):
    def __init__(self, status):
        Exception.__init__(self, status)
        self.status = status


class BreakEx(Exception):
    def __init__(self, levels):
        Exception.__init__(self, levels)
        self.levels = levels


class ContinueEx(Exception):
    def __init__(self, levels):
        Exception.__init__(self, levels)
        self.levels = levels


class PipeClosed(Exception):
    """書き込み先パイプが閉じられた(SIGPIPE 相当)。"""


class ExpandError(Exception):
    def __init__(self, msg, status=1, fatal=False):
        Exception.__init__(self, msg)
        self.msg = msg
        self.status = status
        self.fatal = fatal      # True: 非対話シェルを終了させる(${x:?} や set -u)


class RedirError(Exception):
    pass


class TopLevelAbort(Exception):
    """展開エラー時の bash の挙動(現在の「行」の残りを捨ててトップレベルへ戻る)を表す。"""

    def __init__(self, status=1):
        Exception.__init__(self, status)
        self.status = status
