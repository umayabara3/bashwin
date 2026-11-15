# -*- coding: utf-8 -*-
"""AST ノード定義。

パーサ(parser.py)が生成し、インタープリター(interp.py)と
トランスパイラー(ps_transpile.py)の両方が同じ木を読む。
"""


class _N(object):
    __slots__ = ()

    def __repr__(self):
        return '%s(%s)' % (type(self).__name__, ', '.join(
            '%s=%r' % (k, getattr(self, k, None)) for k in self.__slots__))


# ---------------------------------------------------------------- word parts
class Lit(_N):
    """クォートされていないリテラル(ブレース/チルダ/グロブの対象)。DQ 内では引用済み扱い。"""
    __slots__ = ('text',)

    def __init__(self, text):
        self.text = text


class Esc(_N):
    """バックスラッシュでエスケープされた1文字(引用済みリテラル)。"""
    __slots__ = ('text',)

    def __init__(self, text):
        self.text = text


class SQ(_N):
    """シングルクォート文字列( $'...' のデコード結果も含む)。"""
    __slots__ = ('text',)

    def __init__(self, text):
        self.text = text


class DQ(_N):
    """ダブルクォート。parts は Lit / Param / CmdSub / Arith。"""
    __slots__ = ('parts',)

    def __init__(self, parts):
        self.parts = parts


class Param(_N):
    """パラメータ展開 $x ${x...}。"""
    __slots__ = ('name', 'index', 'op', 'arg', 'arg2', 'length', 'indirect')

    def __init__(self, name):
        self.name = name
        self.index = None      # None | '@' | '*' | Word
        self.op = None         # None | ':-' '-' ':=' '=' ':?' '?' ':+' '+' '#' '##' '%' '%%'
        #                        '/' '//' '/#' '/%' 'substr' '^' '^^' ',' ',,' '@Q' ... 'prefix'
        self.arg = None        # Word
        self.arg2 = None       # Word
        self.length = False    # ${#x}
        self.indirect = False  # ${!x}


class CmdSub(_N):
    """コマンド置換 $(...) / `...`。"""
    __slots__ = ('node',)

    def __init__(self, node):
        self.node = node


class Arith(_N):
    """算術展開 $((...))。word は式テキスト(展開を含みうる)。"""
    __slots__ = ('word',)

    def __init__(self, word):
        self.word = word


class ProcSub(_N):
    """プロセス置換 <(...) / >(...)。"""
    __slots__ = ('kind', 'node')

    def __init__(self, kind, node):
        self.kind = kind
        self.node = node


class Word(_N):
    __slots__ = ('parts', 'assign')

    def __init__(self, parts):
        self.parts = parts
        self.assign = None     # (name, indexWord|None, append, Word|ArrayLit) 代入形の語のみ


class ArrayLit(_N):
    """配列リテラル (a b [k]=v)。elems は (keyWord|None, valueWord)。"""
    __slots__ = ('elems',)

    def __init__(self, elems):
        self.elems = elems


# ---------------------------------------------------------------- commands
class Redir(_N):
    __slots__ = ('fd', 'op', 'target', 'heredoc_quoted')

    def __init__(self, fd, op, target):
        self.fd = fd           # int | None
        self.op = op           # '<' '>' '>>' '>|' '<>' '<&' '>&' '&>' '&>>' '<<' '<<-' '<<<'
        self.target = target   # Word (ヒアドキュメントは本文 Word)
        self.heredoc_quoted = False


class Simple(_N):
    __slots__ = ('assigns', 'words', 'redirs', 'line')

    def __init__(self, assigns, words, redirs, line):
        self.assigns = assigns  # [(name, indexWord|None, append, Word|ArrayLit)]
        self.words = words
        self.redirs = redirs
        self.line = line


class Pipeline(_N):
    __slots__ = ('cmds', 'negate', 'stderr_too')

    def __init__(self, cmds, negate, stderr_too):
        self.cmds = cmds
        self.negate = negate
        self.stderr_too = stderr_too  # 各 '|' が '|&' か


class AndOr(_N):
    __slots__ = ('first', 'rest')

    def __init__(self, first, rest):
        self.first = first
        self.rest = rest        # [(op, pipeline)]


class List(_N):
    __slots__ = ('items', 'breaks')

    def __init__(self, items, breaks=None):
        self.items = items      # [(node, is_async)]
        self.breaks = breaks    # 各要素の直後が改行/EOF か(トップレベルの「行」境界の判定用)


class If(_N):
    __slots__ = ('clauses', 'else_body', 'redirs')

    def __init__(self, clauses, else_body):
        self.clauses = clauses  # [(cond List, body List)]
        self.else_body = else_body
        self.redirs = []


class While(_N):
    __slots__ = ('cond', 'body', 'until', 'redirs')

    def __init__(self, cond, body, until):
        self.cond = cond
        self.body = body
        self.until = until
        self.redirs = []


class For(_N):
    __slots__ = ('var', 'words', 'body', 'redirs')

    def __init__(self, var, words, body):
        self.var = var
        self.words = words      # None => "$@"
        self.body = body
        self.redirs = []


class CFor(_N):
    __slots__ = ('init', 'cond', 'step', 'body', 'redirs')

    def __init__(self, init, cond, step, body):
        self.init = init        # Word | None
        self.cond = cond
        self.step = step
        self.body = body
        self.redirs = []


class Case(_N):
    __slots__ = ('word', 'items', 'redirs')

    def __init__(self, word, items):
        self.word = word
        self.items = items      # [(patterns [Word], body List, terminator)]
        self.redirs = []


class Group(_N):
    __slots__ = ('body', 'redirs')

    def __init__(self, body):
        self.body = body
        self.redirs = []


class Subshell(_N):
    __slots__ = ('body', 'redirs')

    def __init__(self, body):
        self.body = body
        self.redirs = []


class FuncDef(_N):
    __slots__ = ('name', 'body', 'line')

    def __init__(self, name, body, line):
        self.name = name
        self.body = body
        self.line = line


class Cond(_N):
    """[[ ... ]]。expr は ('or',a,b) ('and',a,b) ('not',a) ('unary',op,Word)
    ('binary',op,Word,Word) ('word',Word) の入れ子タプル。"""
    __slots__ = ('expr', 'redirs', 'line')

    def __init__(self, expr, line):
        self.expr = expr
        self.redirs = []
        self.line = line


class ArithCmd(_N):
    """(( ... ))。"""
    __slots__ = ('word', 'redirs', 'line')

    def __init__(self, word, line):
        self.word = word
        self.redirs = []
        self.line = line
