# -*- coding: utf-8 -*-
"""実行エンジン。AST を直接たどって実行する。

fork が無い Windows を前提にした構造:
  * サブシェル / パイプラインの各段 / コマンド置換 / バックグラウンドは、
    インタープリター状態の複製(clone)を別スレッドで動かして実現する。
  * そのため cwd・環境変数・fd 表はプロセス全体ではなく Interp ごとに持つ。
  * 外部コマンドだけが本物の子プロセスになる(subprocess.Popen)。
"""
from __future__ import unicode_literals

import errno
import os
import random
import re
import stat
import subprocess
import sys
import tempfile
import threading
import time

from . import osdep, pattern
from .arith import Evaluator
from .errors import (ExitEx, ReturnEx, BreakEx, ContinueEx, PipeClosed, ExpandError,
                     RedirError, TopLevelAbort)
from .expand import ExpandMixin, shell_quote
from .nodes import (Lit, Word, ArrayLit, Simple, Pipeline, AndOr, List, If, While, For,
                    CFor, Case, Group, Subshell, FuncDef, Cond, ArithCmd)
from .parser import parse, ParseError

VERSION = '0.2.0'

# set -e (errexit) と ERR トラップの判定対象になる構文
_ERREXIT_NODES = frozenset((Simple, Cond, ArithCmd, Subshell, Pipeline))
IS_WIN = osdep.IS_WIN
DECL_BUILTINS = frozenset(('declare', 'typeset', 'local', 'export', 'readonly'))
_VALID_NAME = re.compile(r'[A-Za-z_][A-Za-z0-9_]*$')
_DYNAMIC = frozenset(('RANDOM', 'SECONDS', 'LINENO', 'EPOCHSECONDS', 'EPOCHREALTIME',
                      'BASHPID', 'FUNCNAME', 'BASH_SOURCE', 'BASHWIN_RAWSTATUS',
                      'BASH_SUBSHELL'))
_ARITH_CMP = {'-eq': lambda a, b: a == b, '-ne': lambda a, b: a != b,
              '-lt': lambda a, b: a < b, '-le': lambda a, b: a <= b,
              '-gt': lambda a, b: a > b, '-ge': lambda a, b: a >= b}


class Var(object):
    __slots__ = ('value', 'exported', 'readonly', 'integer', 'assoc', 'case')

    def __init__(self, value=None, exported=False):
        self.value = value      # None | str | dict(添字配列: int->str / 連想配列: str->str)
        self.exported = exported
        self.readonly = False
        self.integer = False
        self.assoc = False
        self.case = None

    def copy(self):
        v = Var.__new__(Var)
        val = self.value
        v.value = dict(val) if type(val) is dict else val
        v.exported = self.exported
        v.readonly = self.readonly
        v.integer = self.integer
        v.assoc = self.assoc
        v.case = self.case
        return v


class AssignArg(str):
    """declare/local/export 等に渡す「代入形の引数」。name/append/value 属性を持つ。"""


class Job(object):
    def __init__(self, jid):
        self.id = jid
        self.status = 0
        self.done = threading.Event()
        self.started = threading.Event()
        self.proc = None
        self.thread = None
        self.killed = False


class Root(object):
    """1 プロセス内で共有する状態。"""

    def __init__(self, name='bashwin'):
        self.pid = os.getpid()
        self.start = time.time()
        self.encoding = os.environ.get('BASHWIN_ENCODING') or 'utf-8'
        self.prefer_external = os.environ.get('BASHWIN_PREFER_EXTERNAL', '') not in ('', '0')
        self.name = name
        self.tmpfiles = []
        self.pending_signals = []
        self.lock = threading.Lock()
        self.job_seq = 0
        self.children = {}
        self.keep = []
        self.raw_status = 0
        self.rng = random.Random()
        self.killed = set()

    def cleanup(self):
        for p in self.tmpfiles:
            try:
                os.unlink(p)
            except OSError:
                pass
        self.tmpfiles = []


def _open_std(fd, mode):
    try:
        return open(fd, mode, buffering=0, closefd=False)
    except (OSError, ValueError):
        return open(os.devnull, mode, buffering=0)


class Interp(ExpandMixin):
    def __init__(self, env=None, argv0='bashwin', args=(), cwd=None, fds=None, root=None):
        self.root = root or Root(argv0)
        self.scopes = [{}]
        self.funcs = {}
        self.pos = list(args)
        self.argv0 = argv0
        self.opts = {'errexit': False, 'nounset': False, 'xtrace': False, 'pipefail': False,
                     'noglob': False, 'igncr': IS_WIN, 'allexport': False, 'verbose': False,
                     'noclobber': False}
        self.shopts = {}
        self.cwd = cwd or osdep.unix_path(os.getcwd())
        self.fds = fds if fds is not None else {0: _open_std(0, 'rb'), 1: _open_std(1, 'wb'),
                                                 2: _open_std(2, 'wb')}
        self.traps = {}
        self.last_status = 0
        self.last_bg = None
        self.cond_depth = 0
        self.func_stack = []
        self.fscopes = []
        self.inherited_traps = {}
        self.source_stack = []
        self.lineno = 0
        self.loop_depth = 0
        self.in_trap = False
        self.arith = Evaluator(self)
        self._cs_status = None
        self.is_subshell = False
        self.jobs = {}
        self.job_id = 0
        self.on_spawn = None
        self._optpos = 0
        self.dirstack = []
        g = self.scopes[0]
        for k, v in (os.environ if env is None else env).items():
            if _VALID_NAME.match(k):
                g[k] = Var(v, True)
        if 'IFS' in g:
            del g['IFS']
        g['IFS'] = Var(' \t\n')
        g['PWD'] = Var(self.cwd, True)
        if 'HOME' not in g:
            g['HOME'] = Var(osdep.default_home(), True)
        if 'PATH' not in g:
            g['PATH'] = Var(os.defpath, True)
        for k, v in (('OPTIND', '1'), ('PS4', '+ '), ('BASHWIN_VERSION', VERSION),
                     ('BASH_VERSION', '5.2.0(1)-bashwin'),
                     ('OSTYPE', 'windows' if IS_WIN else sys.platform),
                     ('HOSTNAME', _hostname()), ('PPID', str(_ppid()))):
            if k not in g:
                g[k] = Var(v)

    # ================================================================= clone
    def clone(self):
        c = object.__new__(Interp)
        c.root = self.root
        c.scopes = [dict([(k, v.copy()) for k, v in sc.items()]) for sc in self.scopes]
        c.funcs = dict(self.funcs)
        c.pos = list(self.pos)
        c.argv0 = self.argv0
        c.opts = dict(self.opts)
        c.shopts = dict(self.shopts)
        c.cwd = self.cwd
        c.fds = dict(self.fds)
        c.traps = {}
        c.last_status = self.last_status
        c.last_bg = self.last_bg
        c.cond_depth = self.cond_depth
        c.func_stack = list(self.func_stack)
        idx = dict((id(sc), k) for k, sc in enumerate(self.scopes))
        c.fscopes = [c.scopes[idx[id(fs)]] for fs in self.fscopes if id(fs) in idx]
        c.inherited_traps = dict(self.traps) if self.traps else dict(self.inherited_traps)
        c.source_stack = list(self.source_stack)
        c.lineno = self.lineno
        c.loop_depth = 0
        c.in_trap = False
        c.arith = Evaluator(c)
        c._cs_status = None
        c.is_subshell = True
        c.jobs = {}
        c.job_id = self.job_id
        c.on_spawn = None
        c._optpos = 0
        c.dirstack = list(self.dirstack)
        return c

    # ================================================================= variables
    def find(self, name):
        scopes = self.scopes
        if len(scopes) == 1:
            return scopes[0].get(name)
        for sc in reversed(scopes):
            v = sc.get(name)
            if v is not None:
                return v
        return None

    def _dynamic(self, name):
        if name == 'RANDOM':
            return str(self.root.rng.randint(0, 32767))
        if name == 'SECONDS':
            return str(int(time.time() - self.root.start))
        if name == 'LINENO':
            return str(self.lineno)
        if name == 'EPOCHSECONDS':
            return str(int(time.time()))
        if name == 'EPOCHREALTIME':
            return '%.6f' % time.time()
        if name == 'BASHPID':
            return str(self.root.pid)
        if name == 'FUNCNAME':
            return self.func_stack[-1] if self.func_stack else None
        if name == 'BASH_SOURCE':
            return self.source_stack[-1] if self.source_stack else self.root.name
        if name == 'BASHWIN_RAWSTATUS':
            return str(self.root.raw_status)
        if name == 'BASH_SUBSHELL':
            return '1' if self.is_subshell else '0'
        return None

    def getvar(self, name):
        v = self.find(name)
        if v is None:
            if name in _DYNAMIC:
                return self._dynamic(name)
            return None
        val = v.value
        if type(val) is dict:
            return val.get('0' if v.assoc else 0)
        return val

    def setvar(self, name, value, scope=None):
        v = self.find(name) if scope is None else scope.get(name)
        if v is None:
            if name == 'SECONDS':
                try:
                    self.root.start = time.time() - int(value)
                except ValueError:
                    pass
                return None
            if name == 'RANDOM':
                self.root.rng.seed(value)
                return None
            v = Var()
            if self.opts['allexport']:
                v.exported = True
            (self.scopes[0] if scope is None else scope)[name] = v
        elif v.readonly:
            raise ExpandError('%s: readonly variable' % name)
        if v.integer:
            value = str(self.arith_word(value))
        if v.case is not None:
            value = value.lower() if v.case == 'l' else value.upper()
        if type(v.value) is dict:
            v.value['0' if v.assoc else 0] = value
        else:
            v.value = value
        return v

    def _array_var(self, name):
        v = self.find(name)
        if v is None:
            v = Var({})
            self.scopes[0][name] = v
        elif v.readonly:
            raise ExpandError('%s: readonly variable' % name)
        if type(v.value) is not dict:
            v.value = {} if v.value is None else {('0' if v.assoc else 0): v.value}
        return v

    def _key(self, v, idx):
        if v.assoc:
            return self.expand_str(idx) if isinstance(idx, Word) else str(idx)
        k = self.arith_word(idx) if isinstance(idx, (Word, str)) else int(idx)
        if k < 0:
            d = v.value if type(v.value) is dict else {}
            k = (max(d) + 1 if d else 0) + k
            if k < 0:
                raise ExpandError('bad array subscript')
        return k

    def set_elem(self, name, idx, value, append=False):
        v = self._array_var(name)
        k = self._key(v, idx)
        if append:
            value = v.value.get(k, '') + value
        if v.integer:
            value = str(self.arith_word(value))
        v.value[k] = value

    def get_elem(self, name, idx):
        v = self.find(name)
        if v is None:
            if name in _DYNAMIC and name in ('FUNCNAME', 'BASH_SOURCE'):
                k = self.arith_word(idx) if isinstance(idx, (Word, str)) else int(idx)
                st = self.func_stack if name == 'FUNCNAME' else self.source_stack
                if name == 'BASH_SOURCE' and not st:
                    return self.root.name if k == 0 else None
                return st[-1 - k] if 0 <= k < len(st) else None
            return None
        if type(v.value) is not dict:
            if v.assoc:
                return None
            k = self.arith_word(idx) if isinstance(idx, (Word, str)) else int(idx)
            return v.value if k == 0 else None
        try:
            return v.value.get(self._key(v, idx))
        except ExpandError:
            return None

    def array_values(self, name):
        v = self.find(name)
        if v is None:
            if name == 'FUNCNAME':
                return list(reversed(self.func_stack))
            return []
        val = v.value
        if type(val) is dict:
            if v.assoc:
                return list(val.values())
            return [val[k] for k in sorted(val)]
        return [] if val is None else [val]

    def array_keys(self, name):
        v = self.find(name)
        if v is None:
            return []
        val = v.value
        if type(val) is dict:
            if v.assoc:
                return list(val.keys())
            return [str(k) for k in sorted(val)]
        return [] if val is None else ['0']

    def assign_array(self, name, pairs, append=False, assoc=False, scope=None):
        v = self.find(name) if scope is None else scope.get(name)
        if v is None:
            v = Var({})
            (self.scopes[0] if scope is None else scope)[name] = v
        if v.readonly:
            raise ExpandError('%s: readonly variable' % name)
        if assoc:
            v.assoc = True
        if not append or type(v.value) is not dict:
            old = v.value
            v.value = {}
            if append and old is not None and type(old) is not dict:
                v.value['0' if v.assoc else 0] = old
        d = v.value
        if v.assoc:
            pend = None
            for k, val in pairs:
                if k is None:
                    if pend is None:
                        pend = val
                    else:
                        d[pend] = val
                        pend = None
                else:
                    d[k] = val
            if pend is not None:
                d[pend] = ''
        else:
            nxt = (max(d) + 1) if d else 0
            for k, val in pairs:
                if k is not None:
                    nxt = self.arith_word(k)
                d[nxt] = val
                nxt += 1

    def eval_array_lit(self, lit):
        pairs = []
        for key, w in lit.elems:
            if key is None:
                tmp = []
                self._expand_word(w, tmp)
                for s in tmp:
                    pairs.append((None, s))
            else:
                pairs.append((self.expand_str(key), self.expand_str(w)))
        return pairs

    def unsetvar(self, name):
        cur = self.fscopes[-1] if self.fscopes else None
        for sc in reversed(self.scopes):
            v = sc.get(name)
            if v is not None:
                if v.readonly:
                    raise ExpandError('%s: cannot unset: readonly variable' % name)
                if sc is cur:
                    # 現在の関数のローカル変数は「未設定のローカル」として残る(外側は見えない)
                    v.value = None
                    v.assoc = False
                else:
                    del sc[name]
                return True
        return False

    def declare_local(self, name):
        """現在の関数スコープに変数を作って返す(関数外ならグローバル)。"""
        scope = self.fscopes[-1] if self.fscopes else self.scopes[0]
        v = scope.get(name)
        if v is None:
            outer = self.find(name)
            v = Var()
            if outer is not None and outer.exported:
                v.exported = True
            scope[name] = v
        return v, scope

    def all_var_names(self):
        names = set()
        for sc in self.scopes:
            names.update(sc.keys())
        return names

    def export_env(self):
        env = {}
        for sc in self.scopes:
            for k, v in sc.items():
                if v.exported and type(v.value) is str:
                    env[k] = v.value
                elif k in env:
                    del env[k]
        return env

    def option_flags(self):
        s = 'hB'
        for o, c in (('errexit', 'e'), ('noglob', 'f'), ('nounset', 'u'), ('xtrace', 'x'),
                     ('allexport', 'a'), ('verbose', 'v'), ('noclobber', 'C')):
            if self.opts[o]:
                s += c
        return s

    # arith.Evaluator から呼ばれる
    def arith_is_assoc(self, name):
        v = self.find(name)
        return v is not None and v.assoc

    def arith_get(self, name, key):
        if key is None:
            return self.getvar(name)
        v = self.find(name)
        if v is None:
            return None
        if type(v.value) is dict:
            if not v.assoc and key < 0 and v.value:
                key = max(v.value) + 1 + key
            return v.value.get(key)
        return v.value if key == 0 else None

    def arith_set(self, name, key, val):
        if key is None:
            self.setvar(name, str(val))
        else:
            self.set_elem(name, key if self.arith_is_assoc(name) else int(key), str(val))

    def do_assign(self, a, tmp_scope=None):
        name, idx, append, value = a
        if type(value) is ArrayLit:
            self.assign_array(name, self.eval_array_lit(value), append)
            return
        val = self.expand_str(value, assign=True)
        if tmp_scope is not None:
            tmp_scope[name] = Var(val, True)
        elif idx is not None:
            self.set_elem(name, idx, val, append)
        elif append:
            v = self.find(name)
            if v is not None and type(v.value) is dict:
                self.set_elem(name, '0' if v.assoc else 0, val, True)
            elif v is not None and v.integer:
                self.setvar(name, '(%s)+(%s)' % (v.value or 0, val))
            else:
                self.setvar(name, (self.getvar(name) or '') + val)
        else:
            self.setvar(name, val)

    # ================================================================= I/O
    def enc(self, s):
        return s.encode(self.root.encoding, 'surrogateescape')

    def dec(self, b):
        return b.decode(self.root.encoding, 'surrogateescape')

    def write_fd(self, fd, data):
        f = self.fds.get(fd)
        if f is None:
            return
        try:
            mv = memoryview(data)
            while len(mv):
                n = f.write(mv)
                if n is None:
                    n = 0
                mv = mv[n:]
        except BrokenPipeError:
            raise PipeClosed()
        except OSError as e:
            if e.errno in (errno.EPIPE, errno.EINVAL, errno.EBADF):
                raise PipeClosed()
            raise
        except ValueError:
            raise PipeClosed()

    def out(self, s):
        self.write_fd(1, s.encode(self.root.encoding, 'surrogateescape'))

    def out_bytes(self, b):
        self.write_fd(1, b)

    def err(self, s):
        try:
            self.write_fd(2, s.encode(self.root.encoding, 'surrogateescape'))
        except PipeClosed:
            pass

    def errmsg(self, msg):
        if self.lineno:
            self.err('%s: line %d: %s\n' % (self.root.name, self.lineno, msg))
        else:
            self.err('%s: %s\n' % (self.root.name, msg))

    def read_all(self, fd=0):
        f = self.fds.get(fd)
        if f is None:
            return b''
        chunks = []
        while True:
            try:
                b = f.read(65536)
            except OSError:
                break
            if not b:
                break
            chunks.append(b)
        return b''.join(chunks)

    def read_line(self, f, delim=b'\n'):
        """1 行読む。(delim を除いたバイト列, delim を見つけたか) を返す。

        同じ入力を後続のコマンドも読めるよう、読み過ぎない:
        通常ファイルはまとめ読みして seek で戻し、パイプ等は 1 バイトずつ読む。
        """
        try:
            regular = stat.S_ISREG(os.fstat(f.fileno()).st_mode)
        except (OSError, ValueError, AttributeError):
            regular = False
        if regular:
            buf = b''
            while True:
                chunk = f.read(4096)
                if not chunk:
                    return buf, False
                k = chunk.find(delim)
                if k >= 0:
                    extra = len(chunk) - k - 1
                    if extra:
                        f.seek(-extra, 1)
                    return buf + chunk[:k], True
                buf += chunk
        out = bytearray()
        while True:
            try:
                c = f.read(1)
            except OSError:
                c = b''
            if not c:
                return bytes(out), False
            if c == delim:
                return bytes(out), True
            out += c

    def abspath(self, p):
        if not p:
            return ''
        if IS_WIN:
            p = osdep.map_virtual(p)
            if p == 'NUL':
                return os.devnull
        elif p == '/dev/null':
            return p
        return os.path.join(self.cwd, p)

    def open_file(self, path, op):
        """リダイレクト先を開く。(file, 自分で閉じるべきか) を返す。"""
        if path in ('/dev/stdin', '/dev/fd/0'):
            return self.fds.get(0), False
        if path in ('/dev/stdout', '/dev/fd/1'):
            return self.fds.get(1), False
        if path in ('/dev/stderr', '/dev/fd/2'):
            return self.fds.get(2), False
        if path == '/dev/null':
            real = os.devnull
        elif path == '/dev/tty' and IS_WIN:
            real = 'CON'
        else:
            real = self.abspath(path)
        try:
            if op == '<':
                f = open(real, 'rb', buffering=0)
            elif op == '>>' or op == '&>>':
                f = open(real, 'ab', buffering=0)
                try:
                    f.seek(0, 2)   # Windows: 子プロセスに渡すハンドルの位置を末尾にしておく
                except OSError:
                    pass
            elif op == '<>':
                f = os.fdopen(os.open(real, os.O_RDWR | os.O_CREAT | getattr(os, 'O_BINARY', 0),
                                      0o666), 'r+b', 0)
            else:
                if self.opts['noclobber'] and op == '>' and os.path.isfile(real):
                    raise RedirError('%s: cannot overwrite existing file' % path)
                f = open(real, 'wb', buffering=0)
        except OSError as e:
            raise RedirError('%s: %s' % (path, e.strerror or e))
        return f, True

    def _data_file(self, data):
        f = tempfile.TemporaryFile(buffering=0)
        mv = memoryview(data)
        while len(mv):
            n = f.write(mv)
            mv = mv[n:]
        f.seek(0)
        return f

    def push_redirs(self, redirs):
        if not redirs:
            return None
        saved = self.fds
        fds = dict(saved)
        opened = []
        try:
            for r in redirs:
                op = r.op
                if op == '<<' or op == '<<-':
                    f = self._data_file(self.enc(self.expand_str(r.target)))
                    opened.append(f)
                    fds[0 if r.fd is None else r.fd] = f
                elif op == '<<<':
                    f = self._data_file(self.enc(self.expand_str(r.target) + '\n'))
                    opened.append(f)
                    fds[0 if r.fd is None else r.fd] = f
                elif op == '<&' or op == '>&':
                    t = self.expand_str(r.target)
                    fd = r.fd if r.fd is not None else (0 if op == '<&' else 1)
                    if t == '-':
                        fds.pop(fd, None)
                    elif t.isdigit():
                        src = int(t)
                        if src not in fds:
                            raise RedirError('%s: Bad file descriptor' % t)
                        fds[fd] = fds[src]
                    elif t.endswith('-') and t[:-1].isdigit():
                        src = int(t[:-1])
                        if src not in fds:
                            raise RedirError('%s: Bad file descriptor' % t[:-1])
                        fds[fd] = fds.pop(src)
                    elif op == '>&' and r.fd is None:
                        f, own = self.open_file(t, '>')
                        if own:
                            opened.append(f)
                        fds[1] = fds[2] = f
                    else:
                        raise RedirError('%s: ambiguous redirect' % t)
                elif op == '&>' or op == '&>>':
                    f, own = self.open_file(self.expand_str(r.target), op)
                    if own:
                        opened.append(f)
                    fds[1] = fds[2] = f
                else:
                    f, own = self.open_file(self.expand_str(r.target), op)
                    if own:
                        opened.append(f)
                    fds[r.fd if r.fd is not None else (0 if op in ('<', '<>') else 1)] = f
        except Exception:
            for f in opened:
                try:
                    f.close()
                except OSError:
                    pass
            raise
        self.fds = fds
        return (saved, opened)

    def pop_redirs(self, tok):
        if tok is None:
            return
        self.fds = tok[0]
        for f in tok[1]:
            try:
                f.close()
            except OSError:
                pass

    # ================================================================= execution
    def run(self, node):
        tp = type(node)
        if tp is Simple:
            st = self.run_simple(node)
        else:
            try:
                rd = getattr(node, 'redirs', None)
                if rd:
                    tok = self.push_redirs(rd)
                    try:
                        st = self._handlers[tp](self, node)
                    finally:
                        self.pop_redirs(tok)
                else:
                    st = self._handlers[tp](self, node)
            except ExpandError as e:
                self.errmsg(e.msg)
                if e.fatal:
                    raise ExitEx(e.status or 1)
                if tp is not ArithCmd and tp is not CFor:
                    self.last_status = e.status
                    raise TopLevelAbort(e.status)
                st = e.status
            except RedirError as e:
                self.errmsg(str(e))
                st = 1
        self.last_status = st
        return st

    def run_item(self, node):
        """リストの 1 要素を実行し、errexit / ERR トラップの判定を行う。"""
        tp = type(node)
        st = self.run(node)
        # errexit の判定対象は「単純コマンド・[[ ]]・(( ))・サブシェル・パイプライン」だけ。
        # if/for/while/case/{ } は、中の失敗が -e 無視の文脈(&& の左辺など)で起きて
        # 非 0 を返しても、それ自体では終了しない(bash と同じ)。
        if st != 0 and tp in _ERREXIT_NODES and self.cond_depth == 0 \
                and not (tp is Pipeline and node.negate):
            self.on_error(st)
        return st

    def on_error(self, st):
        t = self.traps.get('ERR')
        if t and not self.in_trap:
            self.run_trap(t)
        if self.opts['errexit']:
            raise ExitEx(st)

    def run_list(self, node):
        st = 0
        for item, is_async in node.items:
            if is_async:
                st = self.run_async(item)
                self.last_status = st
            else:
                st = self.run_item(item)
        return st

    def run_andor(self, node):
        self.cond_depth += 1
        try:
            st = self.run(node.first)
        finally:
            self.cond_depth -= 1
        rest = node.rest
        last = len(rest) - 1
        for k, (op, pl) in enumerate(rest):
            if (op == '&&') == (st == 0):
                if k == last:
                    st = self.run_item(pl)
                else:
                    self.cond_depth += 1
                    try:
                        st = self.run(pl)
                    finally:
                        self.cond_depth -= 1
        return st

    def run_pipeline(self, node):
        cmds = node.cmds
        n = len(cmds)
        if n == 1:
            self.cond_depth += 1
            try:
                st = self.run(cmds[0])
            finally:
                self.cond_depth -= 1
            return 0 if st else 1
        statuses = [0] * n
        threads = []
        prev_r = None
        for k, cmd in enumerate(cmds):
            sub = self.clone()
            if node.negate:
                sub.cond_depth += 1
            w = None
            r = None
            if prev_r is not None:
                sub.fds[0] = prev_r
            if k < n - 1:
                rfd, wfd = os.pipe()
                r = os.fdopen(rfd, 'rb', 0)
                w = os.fdopen(wfd, 'wb', 0)
                sub.fds[1] = w
                if node.stderr_too[k]:
                    sub.fds[2] = w
            t = threading.Thread(target=_stage, args=(sub, cmd, statuses, k, prev_r, w))
            t.start()
            threads.append(t)
            prev_r = r
        for t in threads:
            t.join()
        self.assign_array('PIPESTATUS', [(None, str(s)) for s in statuses])
        st = statuses[-1]
        if self.opts['pipefail']:
            for s in reversed(statuses):
                if s:
                    st = s
                    break
        if node.negate:
            st = 0 if st else 1
        return st

    def _expand_decl(self, words):
        """declare/local/export/readonly: 代入形の語は分割・グロブしない。"""
        argv = [words[0].parts[0].text]
        for w in words[1:]:
            a = w.assign
            if a is None:
                self._expand_word(w, argv)
                continue
            name, idx, append, value = a
            if type(value) is ArrayLit:
                arg = AssignArg(name + '=(...)')
                arg.value = self.eval_array_lit(value)
            else:
                val = self.expand_str(value, assign=True)
                arg = AssignArg(name + '=' + val)
                arg.value = val
            arg.name = name
            arg.append = append
            arg.index = idx
            argv.append(arg)
        return argv

    def run_simple(self, node):
        self.lineno = node.line
        if self.root.pending_signals:
            self.check_signals()
        if self.job_id and self.job_id in self.root.killed:
            raise ExitEx(143)
        self._cs_status = None
        words = node.words
        try:
            if words:
                w0 = words[0].parts
                if len(w0) == 1 and type(w0[0]) is Lit and w0[0].text in DECL_BUILTINS \
                        and w0[0].text not in self.funcs:
                    argv = self._expand_decl(words)
                else:
                    argv = self.expand_words(words)
            else:
                argv = []
            if not argv:
                tok = self.push_redirs(node.redirs)
                try:
                    for a in node.assigns:
                        self.do_assign(a)
                        if self.opts['xtrace']:
                            self.err('%s%s=%s\n' % (self.getvar('PS4') or '', a[0],
                                                    shell_quote(self.getvar(a[0]) or '')))
                finally:
                    self.pop_redirs(tok)
                return self._cs_status if self._cs_status is not None else 0
            return self.exec_argv(argv, node.assigns, node.redirs)
        except ExpandError as e:
            self.errmsg(e.msg)
            if e.fatal:
                raise ExitEx(e.status or 1)
            # bash 互換: 展開エラーは現在の行の残りを捨ててトップレベルへ戻る
            self.last_status = e.status
            raise TopLevelAbort(e.status)
        except RedirError as e:
            self.errmsg(str(e))
            return 1

    def lookup_builtin(self, name):
        from . import shbuiltins
        b = shbuiltins.BUILTINS.get(name)
        if b is not None:
            return b
        from . import applets
        if name in applets.REGISTRY:
            if self.root.prefer_external and self.find_command(name):
                return None
            return applets.get(name)
        return None

    def exec_argv(self, argv, assigns=(), redirs=(), nofunc=False):
        name = argv[0]
        if self.opts['xtrace']:
            self.err((self.getvar('PS4') or '') + ' '.join([shell_quote(a) for a in argv]) + '\n')
        fn = None if nofunc else self.funcs.get(name)
        if name == 'exec' and fn is None:
            return self._do_exec(argv, assigns, redirs)
        tok = self.push_redirs(redirs)
        tmp = None
        try:
            b = None if fn is not None else self.lookup_builtin(name)
            if fn is not None or b is not None:
                if assigns:
                    tmp = {}
                    for a in assigns:
                        if type(a[3]) is ArrayLit:
                            self.do_assign(a)
                        else:
                            self.do_assign(a, tmp)
                    self.scopes.append(tmp)
                if fn is not None:
                    return self.call_function(fn, argv)
                return self.call_builtin(b, argv)
            env = self.export_env()
            if assigns:
                t2 = {}
                for a in assigns:
                    if type(a[3]) is not ArrayLit:
                        self.do_assign(a, t2)
                for k, v in t2.items():
                    env[k] = v.value
            return self.run_external(argv, env)
        finally:
            if tmp is not None:
                for i in range(len(self.scopes) - 1, -1, -1):
                    if self.scopes[i] is tmp:
                        del self.scopes[i]
                        break
            self.pop_redirs(tok)

    def call_builtin(self, b, argv):
        try:
            return b(self, argv) or 0
        except ExpandError as e:
            self.errmsg('%s: %s' % (argv[0], e.msg))
            if e.fatal:
                raise ExitEx(e.status or 1)
            return e.status or 1
        except OSError as e:
            if isinstance(e, BrokenPipeError):
                raise PipeClosed()
            self.errmsg('%s: %s' % (argv[0], e.strerror or e))
            return 1

    def _do_exec(self, argv, assigns, redirs):
        if len(argv) == 1:
            tok = self.push_redirs(redirs)
            if tok is not None:
                self.root.keep.extend(tok[1])
            for a in assigns:
                self.do_assign(a)
            return 0
        st = self.exec_argv(argv[1:], assigns, redirs, nofunc=True)
        raise ExitEx(st)

    def call_function(self, fn, argv):
        if len(self.func_stack) >= 1000:
            self.errmsg('%s: maximum function nesting level exceeded (1000)' % fn.name)
            return 1
        saved_pos = self.pos
        saved_loop = self.loop_depth
        self.pos = list(argv[1:])
        fscope = {}
        self.scopes.append(fscope)
        self.fscopes.append(fscope)
        self.func_stack.append(fn.name)
        try:
            return self.run(fn.body)
        except ReturnEx as r:
            return r.status
        finally:
            self.func_stack.pop()
            self.fscopes.pop()
            for i in range(len(self.scopes) - 1, -1, -1):
                if self.scopes[i] is fscope:
                    del self.scopes[i]
                    break
            self.pos = saved_pos
            self.loop_depth = saved_loop

    def find_command(self, name):
        return osdep.find_command(name, self.getvar('PATH') or '', self.cwd,
                                  self.getvar('PATHEXT'))

    def run_external(self, argv, env=None):
        path = self.find_command(argv[0])
        if path is None:
            if ('/' in argv[0]) and os.path.isdir(self.abspath(argv[0])):
                self.errmsg('%s: Is a directory' % argv[0])
                return 126
            self.errmsg('%s: %s' % (argv[0], 'No such file or directory' if '/' in argv[0]
                                    else 'command not found'))
            return 127
        if env is None:
            env = self.export_env()
        return self.spawn(path, argv, env)

    def spawn(self, path, argv, env):
        spec = osdep.launch_spec(path, argv)
        if spec[0] == 'script':
            return self.run_script_file(path, argv, env)
        stdin = self.fds.get(0)
        stdout = self.fds.get(1)
        stderr = self.fds.get(2)
        nul = None
        if stdin is None or stdout is None or stderr is None:
            nul = open(os.devnull, 'r+b', buffering=0)
            stdin = nul if stdin is None else stdin
            stdout = nul if stdout is None else stdout
            stderr = nul if stderr is None else stderr
        cwd = self.cwd.replace('/', '\\') if IS_WIN else self.cwd
        try:
            try:
                if spec[0] == 'cmdline' or IS_WIN:
                    p = subprocess.Popen(spec[1], stdin=stdin, stdout=stdout, stderr=stderr,
                                         cwd=cwd, env=env)
                else:
                    p = subprocess.Popen([argv[0]] + spec[1][1:], executable=spec[1][0],
                                         stdin=stdin, stdout=stdout, stderr=stderr,
                                         cwd=cwd, env=env)
            except OSError as e:
                if e.errno == errno.ENOEXEC:
                    return self.run_script_file(path, argv, env)
                self.errmsg('%s: %s' % (argv[0], e.strerror or e))
                return 127 if e.errno == errno.ENOENT else 126
        finally:
            if nul is not None:
                nul.close()
        self.root.children[p] = self.job_id
        cb = self.on_spawn
        if cb is not None:
            self.on_spawn = None
            cb(p)
        try:
            rc = p.wait()
        finally:
            self.root.children.pop(p, None)
        self.root.raw_status = rc
        return osdep.norm_status(rc)

    def run_script_file(self, path, argv, env):
        """別プロセス相当としてスクリプトをプロセス内実行する(export 済み環境だけ渡す)。"""
        child = Interp(env=env, argv0=argv[0], args=argv[1:], cwd=self.cwd,
                       fds=dict(self.fds), root=self.root)
        child.job_id = self.job_id
        child.is_subshell = True
        saved_name = self.root.name
        try:
            return child.run_file(path)
        finally:
            self.root.name = saved_name

    # ----------------------------------------------------------------- subshells
    def run_isolated(self, node):
        """clone した Interp 上で node を実行し、制御例外を終了コードに畳む。"""
        try:
            try:
                st = self.run_item(node)
            except ExitEx as e:
                st = e.status
            except ReturnEx as e:
                st = e.status
            except (BreakEx, ContinueEx):
                st = self.last_status
            except TopLevelAbort as e:
                st = e.status
            except PipeClosed:
                st = 141
            return self._run_exit_trap(st)
        except PipeClosed:
            return 141
        except TopLevelAbort as e:
            return e.status

    def run_isolated_code(self, code):
        """コード文字列を(この Interp 上で)サブシェル相当として実行する。"""
        try:
            node = parse(code)
        except ParseError as e:
            self.err('%s: line %d: %s\n' % (self.root.name, e.line, e.msg))
            return 2
        return self.run_isolated(node)

    def command_subst_code(self, code):
        try:
            node = parse(code)
        except ParseError as e:
            self.err('%s: line %d: %s\n' % (self.root.name, e.line, e.msg))
            return ''
        return self.command_subst(node)

    def _run_exit_trap(self, st):
        t = self.traps.pop('EXIT', None)
        if t:
            self.last_status = st
            try:
                self.run_trap(t)
            except ExitEx as e:
                st = e.status
            except (ReturnEx, BreakEx, ContinueEx):
                pass
        return st

    def command_subst(self, node):
        items = node.items
        if len(items) == 1 and type(items[0][0]) is Simple:
            s = items[0][0]
            if not s.words and not s.assigns and len(s.redirs) == 1 and s.redirs[0].op == '<':
                path = self.expand_str(s.redirs[0].target)
                try:
                    with open(self.abspath(path), 'rb') as f:
                        data = f.read()
                except OSError as e:
                    self.errmsg('%s: %s' % (path, e.strerror or e))
                    self._cs_status = 1
                    return ''
                self._cs_status = 0
                return self._cs_text(data)
        sub = self.clone()
        if not self.shopts.get('inherit_errexit'):
            sub.opts['errexit'] = False
        rfd, wfd = os.pipe()
        r = os.fdopen(rfd, 'rb', 0)
        w = os.fdopen(wfd, 'wb', 0)
        sub.fds[1] = w
        chunks = []

        def reader():
            while True:
                try:
                    b = r.read(65536)
                except OSError:
                    break
                if not b:
                    break
                chunks.append(b)

        t = threading.Thread(target=reader)
        t.start()
        try:
            st = sub.run_isolated(node)
        finally:
            w.close()
            t.join()
            r.close()
        self._cs_status = st
        self.last_status = st
        return self._cs_text(b''.join(chunks))

    def _cs_text(self, data):
        text = self.dec(data)
        if '\0' in text:
            text = text.replace('\0', '')
        if self.opts['igncr'] and '\r' in text:
            text = text.replace('\r\n', '\n')
        return text.rstrip('\n')

    def process_subst(self, p):
        if p.kind != '<':
            raise ExpandError('>(...) process substitution is not supported')
        fd, path = tempfile.mkstemp(prefix='bashwin-ps-')
        self.root.tmpfiles.append(path)
        f = os.fdopen(fd, 'wb', 0)
        sub = self.clone()
        sub.fds[1] = f
        try:
            sub.run_isolated(p.node)
        finally:
            f.close()
        return osdep.unix_path(path)

    def run_async(self, node):
        sub = self.clone()
        nul = open(os.devnull, 'rb', buffering=0)
        sub.fds[0] = nul
        with self.root.lock:
            self.root.job_seq += 1
            jid = self.root.job_seq
        job = Job(jid)
        sub.job_id = jid

        def on_spawn(p):
            job.proc = p
            job.started.set()

        def target():
            try:
                job.status = sub.run_isolated(node)
            finally:
                job.started.set()
                job.done.set()
                nul.close()

        if type(node) is Simple:
            sub.on_spawn = on_spawn
        t = threading.Thread(target=target)
        t.daemon = True
        job.thread = t
        t.start()
        pid = 100000 + jid
        if type(node) is Simple:
            job.started.wait(5)
            if job.proc is not None:
                pid = job.proc.pid
        self.jobs[str(pid)] = job
        self.last_bg = str(pid)
        return 0

    # ----------------------------------------------------------------- compound
    def run_if(self, node):
        for cond, body in node.clauses:
            self.cond_depth += 1
            try:
                c = self.run(cond)
            finally:
                self.cond_depth -= 1
            if c == 0:
                return self.run(body)
        if node.else_body is not None:
            return self.run(node.else_body)
        return 0

    def _loop_body(self, body):
        """(status, 'break'|'continue'|None) を返す。多段 break は再送出。"""
        try:
            return self.run(body), None
        except BreakEx as b:
            if b.levels > 1:
                raise BreakEx(b.levels - 1)
            return self.last_status, 'break'
        except ContinueEx as c:
            if c.levels > 1:
                raise ContinueEx(c.levels - 1)
            return self.last_status, 'continue'

    def run_while(self, node):
        st = 0
        self.loop_depth += 1
        try:
            while True:
                self.cond_depth += 1
                try:
                    c = self.run(node.cond)
                finally:
                    self.cond_depth -= 1
                if (c == 0) == node.until:
                    break
                st, ctl = self._loop_body(node.body)
                if ctl == 'break':
                    st = 0
                    break
                if ctl == 'continue':
                    st = 0
        finally:
            self.loop_depth -= 1
        return st

    def run_for(self, node):
        values = self.expand_words(node.words) if node.words is not None else list(self.pos)
        st = 0
        self.loop_depth += 1
        try:
            for v in values:
                self.setvar(node.var, v)
                st, ctl = self._loop_body(node.body)
                if ctl == 'break':
                    st = 0
                    break
                if ctl == 'continue':
                    st = 0
        finally:
            self.loop_depth -= 1
        return st

    def run_cfor(self, node):
        if node.init is not None:
            self.arith_word(node.init)
        st = 0
        self.loop_depth += 1
        try:
            while True:
                if node.cond is not None and self.arith_word(node.cond) == 0:
                    break
                st, ctl = self._loop_body(node.body)
                if ctl == 'break':
                    st = 0
                    break
                if ctl == 'continue':
                    st = 0
                if node.step is not None:
                    self.arith_word(node.step)
        finally:
            self.loop_depth -= 1
        return st

    def run_case(self, node):
        word = self.expand_str(node.word)
        nocase = bool(self.shopts.get('nocasematch'))
        st = 0
        fall = False
        for pats, body, term in node.items:
            matched = fall
            if not matched:
                for p in pats:
                    if pattern.match_segs(self.expand_pattern(p), word, nocase):
                        matched = True
                        break
            if not matched:
                continue
            st = self.run(body)
            if term == ';;':
                break
            fall = term == ';&'
        return st

    def run_group(self, node):
        return self.run(node.body)

    def run_subshell(self, node):
        return self.clone().run_isolated(node.body)

    def run_funcdef(self, node):
        self.funcs[node.name] = node
        return 0

    def run_cond(self, node):
        self.lineno = node.line
        return 0 if self.eval_cond(node.expr) else 1

    def run_arithcmd(self, node):
        self.lineno = node.line
        return 0 if self.arith_word(node.word) != 0 else 1

    def eval_cond(self, e):
        k = e[0]
        if k == 'or':
            return self.eval_cond(e[1]) or self.eval_cond(e[2])
        if k == 'and':
            return self.eval_cond(e[1]) and self.eval_cond(e[2])
        if k == 'not':
            return not self.eval_cond(e[1])
        if k == 'word':
            return self.expand_str(e[1]) != ''
        from . import shbuiltins
        if k == 'unary':
            return shbuiltins.test_unary(self, e[1], self.expand_str(e[2]))
        op = e[1]
        lhs = self.expand_str(e[2])
        nocase = bool(self.shopts.get('nocasematch'))
        if op in ('==', '=', '!='):
            m = pattern.match_segs(self.expand_pattern(e[3]), lhs, nocase)
            return m if op != '!=' else not m
        if op == '=~':
            src = self.expand_regex(e[3])
            try:
                m = re.search(src, lhs, re.IGNORECASE if nocase else 0)
            except re.error:
                raise ExpandError('invalid regular expression: %s' % src, status=2)
            if m:
                groups = [m.group(0)] + [g if g is not None else '' for g in m.groups()]
                self.assign_array('BASH_REMATCH', [(None, g) for g in groups])
            else:
                self.assign_array('BASH_REMATCH', [])
            return m is not None
        rhs = self.expand_str(e[3])
        if op == '<':
            return lhs < rhs
        if op == '>':
            return lhs > rhs
        if op in _ARITH_CMP:
            return _ARITH_CMP[op](self.arith_word(lhs), self.arith_word(rhs))
        return shbuiltins.test_binary(self, op, lhs, rhs)

    _handlers = {}

    # ----------------------------------------------------------------- source / traps
    def source_string(self, code, lineno_base=1):
        try:
            node = parse(code, lineno_base)
        except ParseError as e:
            self.err('%s: line %d: %s\n' % (self.root.name, e.line, e.msg))
            return 2
        return self.run_toplevel(node)

    def run_toplevel(self, node):
        """トップレベル(本体・eval・source・trap)のリスト実行。

        展開エラー(TopLevelAbort)が来たら、bash と同じく現在の行の残りを捨てて
        次の行から続行する。
        """
        items = node.items
        breaks = node.breaks
        n = len(items)
        st = 0
        i = 0
        while i < n:
            item, is_async = items[i]
            try:
                if is_async:
                    st = self.run_async(item)
                    self.last_status = st
                else:
                    st = self.run_item(item)
            except TopLevelAbort as e:
                st = e.status
                self.last_status = st
                while i < n and not breaks[i]:
                    i += 1
            i += 1
        return st

    def read_script(self, path):
        with open(path, 'rb') as f:
            data = f.read()
        if data.startswith(b'\xef\xbb\xbf'):
            data = data[3:]
        return data.decode(self.root.encoding, 'surrogateescape')

    def run_file(self, path):
        """メインスクリプトとして実行する。"""
        try:
            code = self.read_script(path)
        except OSError as e:
            self.err('%s: %s: %s\n' % (self.root.name, path, e.strerror or e))
            return 127
        self.root.name = self.argv0
        return self.run_code(code)

    def run_code(self, code):
        try:
            node = parse(code)
        except ParseError as e:
            self.err('%s: line %d: %s\n' % (self.root.name, e.line, e.msg))
            return 2
        return self.run_main(node)

    def run_main(self, node):
        try:
            try:
                st = self.run_toplevel(node)
                if self.root.pending_signals and not self.is_subshell:
                    self.check_signals()    # 最後のコマンド中に届いたシグナルの trap を実行する
            except ExitEx as e:
                st = e.status
            except ReturnEx as e:
                st = e.status
            except (BreakEx, ContinueEx):
                st = self.last_status
            return self._run_exit_trap(st)
        except PipeClosed:
            return 141
        except ExitEx as e:
            return e.status
        except TopLevelAbort as e:
            return e.status

    def run_trap(self, code):
        saved = self.last_status
        self.in_trap = True
        try:
            self.source_string(code)
        finally:
            self.in_trap = False
            self.last_status = saved

    def check_signals(self):
        if self.is_subshell:
            raise ExitEx(130)
        while self.root.pending_signals:
            sig = self.root.pending_signals.pop(0)
            t = self.traps.get(sig)
            if t is None:
                raise ExitEx(130 if sig == 'INT' else 143)
            if t:
                self.run_trap(t)


Interp._handlers = {
    List: Interp.run_list, AndOr: Interp.run_andor, Pipeline: Interp.run_pipeline,
    If: Interp.run_if, While: Interp.run_while, For: Interp.run_for, CFor: Interp.run_cfor,
    Case: Interp.run_case, Group: Interp.run_group, Subshell: Interp.run_subshell,
    FuncDef: Interp.run_funcdef, Cond: Interp.run_cond, ArithCmd: Interp.run_arithcmd,
}


def _stage(sub, cmd, statuses, k, rin, wout):
    """パイプラインの 1 段(スレッド本体)。"""
    try:
        try:
            statuses[k] = sub.run_isolated(cmd)
        except BaseException as e:      # 内部エラーでもパイプを必ず閉じる
            statuses[k] = 1
            try:
                import traceback
                sub.err('bashwin: internal error: %s\n' % ''.join(
                    traceback.format_exception(type(e), e, e.__traceback__)))
            except Exception:
                pass
    finally:
        for f in (wout, rin):
            if f is not None:
                try:
                    f.close()
                except OSError:
                    pass


def _hostname():
    try:
        import socket
        return socket.gethostname()
    except Exception:
        return 'localhost'


def _ppid():
    try:
        return os.getppid()
    except Exception:
        return 0
