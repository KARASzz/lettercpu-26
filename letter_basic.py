#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
letter_basic.py — LetterBASIC v1.1: LetterCPU-26 上的 QBASIC 方言
================================================================
直接跑在 LetterCPU-26 上、编译成 Letter-ISA v2 伪指令流执行的类 QBASIC 语言。

支持:
  行号(可选)  REM  ' 注释(行内 ' 也行, 字符串里的 ' 不算)
  LET / 隐式赋值:   LET X = 5   /  X = HELLO (数字=十进制或26进制字母串)
  X$ = "文本"                   字符串变量 (必须 $ 后缀)
  PRINT 项[;项...] / ? 速写    数字自动显示 字母(十进制), 如 HELLO(123)
  INPUT [提示;] X               输入 (数字/字母串自动识别)
  IF ... THEN ... [ELSE ...] / IF...THEN GOTO 行号 / THEN 行号
  GOTO / GOSUB / RETURN
  FOR X = a TO b [STEP s] ... NEXT [X]      (支持嵌套、负步长)
  WHILE 条件 ... WEND / DO ... LOOP WHILE|UNTIL 条件
  DIM A(n) / A(i) 读写 / POKE A,i,v / PEEK(A,i)
  SOUND 频率,时长 / PLAY "CDE" (字母=脉冲音高) / SLEEP 秒 / CLS
  表达式: + - * / MOD ( ) < > = <= >= <> AND OR NOT, & 拼接字符串
  内置: ABS() INT() RND(n)/RND LEN() ASC() CHR$() VAL()
        (VAL 把字母串按 26 进制转数字; RND(100) = 1~100 随机整数)

示例:
  10 PRINT "HELLO 26-CPU"
  20 FOR I = 1 TO 5
  30   PRINT I
  40 NEXT I

用法:
  python3 letter_basic.py prog.lb      运行文件
  python3 letter_basic.py              进 REPL (HELP 看帮助, DEMO 跑演示)
"""
import math
import random
import re
import sys
import time

from letter_cpu_v2 import str_to_val as S2V, val_to_str as V2S

# ---------------- 词法 ----------------

TOKEN_RE = re.compile(r"""
    (?P<STRING>"[^"]*")
  | (?P<NUMBER>\d+)
  | (?P<WORD>[A-Za-z_][A-Za-z0-9_]*\$?)
  | (?P<OP><=|>=|<>|[-+*/()=,<>:;&])
  | (?P<SKIP>\s+)
""", re.VERBOSE)


def tokenize(expr):
    toks = []
    for m in TOKEN_RE.finditer(expr):
        k = m.lastgroup
        if k == "SKIP":
            continue
        toks.append((k, m.group()))
    return toks


def strip_comment(s):
    """去掉行内 ' 注释, 双引号字符串里的 ' 不算"""
    out, in_s = [], False
    for c in s:
        if c == '"':
            in_s = not in_s
        if c == "'" and not in_s:
            break
        out.append(c)
    return "".join(out)


def split_top(s, sep=","):
    """顶层分隔(括号/字符串里的分隔符不算)"""
    parts, cur, in_s, depth = [], "", False, 0
    for c in s:
        if c == '"':
            in_s = not in_s
        if not in_s:
            if c in "([":
                depth += 1
            elif c in ")]":
                depth -= 1
        if c == sep and not in_s and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += c
    parts.append(cur)
    return parts


def find_top_eq(s):
    """找顶层(括号外/字符串外)的 = , 跳过 <= >= <> 中的 ="""
    in_s, depth = False, 0
    for i, c in enumerate(s):
        if c == '"':
            in_s = not in_s
        if in_s:
            continue
        if c in "([":
            depth += 1
        elif c in ")]":
            depth -= 1
        elif c == "=" and depth == 0:
            prev = s[i - 1] if i > 0 else ""
            if prev in "<>":
                continue
            return i
    return -1


def parse_lhs(lhs):
    """解析赋值左部: VAR 或 VAR(下标表达式, 允许嵌套括号).
    返回 (NAME, idx|None), NAME 已大写, idx 保留原样; 非法返回 None"""
    m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*\$?)\s*(.*)$", lhs.strip(), re.I | re.S)
    if not m:
        return None
    name, tail = m.group(1).upper(), m.group(2).strip()
    if not tail:
        return name, None
    if not tail.startswith("(") or not tail.endswith(")"):
        return None
    depth, in_s = 0, False
    for i, c in enumerate(tail):
        if c == '"':
            in_s = not in_s
        if in_s:
            continue
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0 and i != len(tail) - 1:
                return None
            if depth < 0:
                return None
    if depth != 0:
        return None
    return name, tail[1:-1]


def split_assignment(s):
    """切分赋值语句为 (左部, 右部); 无顶层 = 返回 None"""
    i = find_top_eq(s)
    if i < 0:
        return None
    return s[:i], s[i + 1:]


class ExprParser:
    """表达式解析 + 求值 (数字 / 字符串二元类型)"""

    def __init__(self, getvar, builtin):
        self.getvar = getvar
        self.builtin = builtin
        self.array_has = lambda n: False  # 由解释器回填
        self.array_get = lambda n, i: 0
        self.toks = []
        self.pos = 0

    def parse(self, text):
        self.toks = tokenize(text)
        self.pos = 0
        v = self.or_expr()
        if self.pos != len(self.toks):
            raise SyntaxError(f"表达式多余部分: {self.toks[self.pos][1]!r}")
        return v

    def peek(self):
        return self.toks[self.pos] if self.pos < len(self.toks) else (None, None)

    def eat(self, typ=None, val=None):
        t, v = self.peek()
        if t is None:
            raise SyntaxError("表达式意外结束")
        if typ and t != typ:
            raise SyntaxError(f"期望 {typ}, 得到 {v}")
        if val and v.upper() != val:
            raise SyntaxError(f"期望 {val}, 得到 {v}")
        self.pos += 1
        return v

    # OR -> AND -> NOT -> 比较 -> 加减(&拼接) -> 乘除MOD -> 一元 -> 原子
    def or_expr(self):
        v = self.and_expr()
        while self.peek()[1] and self.peek()[1].upper() == "OR":
            self.eat()
            r = self.and_expr()
            v = int(bool(num(v)) or bool(num(r)))
        return v

    def and_expr(self):
        v = self.not_expr()
        while self.peek()[1] and self.peek()[1].upper() == "AND":
            self.eat()
            r = self.not_expr()
            v = int(bool(num(v)) and bool(num(r)))
        return v

    def not_expr(self):
        if self.peek()[1] and self.peek()[1].upper() == "NOT":
            self.eat()
            return int(not num(self.not_expr()))
        return self.cmp_expr()

    def cmp_expr(self):
        v = self.add_expr()
        t, op = self.peek()
        if t == "OP" and op in ("=", "<", ">", "<=", ">=", "<>"):
            self.eat()
            r = self.add_expr()
            if isinstance(v, str) or isinstance(r, str):
                a, b = str(v), str(r)
            else:
                a, b = num(v), num(r)
            ok = {"=": a == b, "<>": a != b, "<": a < b, ">": a > b,
                  "<=": a <= b, ">=": a >= b}[op]
            return int(ok)
        return v

    def add_expr(self):
        v = self.mul_expr()
        while True:
            t, op = self.peek()
            if t == "OP" and op in ("+", "-", "&"):
                self.eat()
                r = self.mul_expr()
                if op == "&":
                    v = str(v) + str(r)
                elif op == "+":
                    if isinstance(v, str) or isinstance(r, str):
                        v = str(v) + str(r)
                    else:
                        v = num(v) + num(r)
                else:
                    v = num(v) - num(r)
            else:
                return v

    def mul_expr(self):
        v = self.unary()
        while True:
            t, op = self.peek()
            if t == "OP" and op in ("*", "/"):
                self.eat()
                r = self.unary()
                v = num(v) * num(r) if op == "*" else num(v) // num(r)
            elif t == "WORD" and op.upper() == "MOD":
                self.eat()
                r = self.unary()
                v = num(v) % num(r)
            else:
                return v

    def unary(self):
        t, op = self.peek()
        if t == "OP" and op in ("+", "-"):
            self.eat()
            v = self.unary()
            return v if op == "+" else -num(v)
        return self.atom()

    def atom(self):
        t, v = self.peek()
        if t == "STRING":
            self.eat()
            return v[1:-1]
        if t == "NUMBER":
            self.eat()
            return int(v)
        if t == "OP" and v == "(":
            self.eat()
            x = self.or_expr()
            self.eat("OP", ")")
            return x
        if t == "WORD":
            name = self.eat().upper()
            if self.peek() == ("OP", "("):
                self.eat()
                # PEEK(数组名, 下标): 首参是数组名, 不求值
                if name == "PEEK":
                    t2, v2 = self.peek()
                    if t2 != "WORD":
                        raise SyntaxError("PEEK(数组,下标)")
                    arrname = self.eat().upper()
                    if self.peek() != ("OP", ","):
                        raise SyntaxError("PEEK(数组,下标)")
                    self.eat()
                    idx = self.or_expr()
                    self.eat("OP", ")")
                    return self.array_get(arrname, num(idx))
                args = []
                if self.peek() != ("OP", ")"):
                    args.append(self.or_expr())
                    while self.peek() == ("OP", ","):
                        self.eat()
                        args.append(self.or_expr())
                self.eat("OP", ")")
                # 数组下标读取 A(i)
                if self.array_has(name) and len(args) == 1:
                    return self.array_get(name, num(args[0]))
                return self.builtin(name, args)
            try:
                return self.getvar(name)
            except NameError:
                if re.fullmatch(r"[A-Za-z]+", name):
                    return S2V(name)  # 裸字母串 = 26 进制立即数
                raise
        raise SyntaxError(f"表达式错误, 在 {v!r}")


def num(v):
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, (int, float)):
        return int(v)
    if isinstance(v, str):
        v = v.strip()
        if re.fullmatch(r"-?\d+", v):
            return int(v)
        if re.fullmatch(r"[A-Za-z]+", v):
            return S2V(v.upper())
        raise ValueError(f"不能当数字: {v!r}")
    raise ValueError(f"不能当数字: {v!r}")


# ---------------- 编译器: BASIC -> ISA v2 伪指令流 ----------------

class BasicCompiler:
    def __init__(self):
        self.code = []       # [op, arg]
        self.lbl_n = 0

    def lbl(self, base="L"):
        self.lbl_n += 1
        return f"{base}{self.lbl_n}"

    def out(self, op, arg=None):
        self.code.append([op, arg])

    def out_label(self, name):
        self.code.append(["__LABEL__", name])

    def compile_lines(self, stmts):
        """stmts: [(lineno|None, text)]"""
        for ln, _ in stmts:
            if ln is not None:
                pass  # 行号标签在下面逐行打
        block_stack = []
        for ln, text in stmts:
            if ln is not None:
                self.out_label(f"LINE{ln}")
            self.compile_stmt(text, block_stack)
        if block_stack:
            raise SyntaxError(f"有未闭合的块: {block_stack[0][0]}")
        return self.code

    def compile_stmt(self, text, block_stack):
        self.out("BEAT", None)  # 语句边界拍
        t = text.strip()
        if not t or t.upper().startswith("REM") or t.startswith("'"):
            self.out("NOP", None)
            return
        for part in split_top(t, ":"):
            self.compile_one(part.strip(), block_stack)

    def compile_one(self, t, block_stack):
        if not t:
            return
        w, _, rest = t.partition(" ")
        W = w.upper()
        if W in ("PRINT", "?"):
            self.c_print(rest.strip())
            return
        if W == "INPUT":
            self.c_input(rest.strip())
            return
        if W in ("GOTO", "GOSUB"):
            m = re.search(r"(\d+)\s*$", t)
            if not m:
                raise SyntaxError(f"{W} 后需行号: {t}")
            self.out("CALL" if W == "GOSUB" else "JMP", f"LINE{m.group(1)}")
            return
        if W == "RETURN":
            self.out("RET", None)
            return
        if W in ("END", "STOP"):
            self.out("HLT", None)
            return
        if W == "CLS":
            self.out("__CLS__", None)
            return
        if W == "SLEEP":
            self.out("__SLEEP__", rest.strip())
            return
        if W == "SOUND":
            self.out("__SOUND__", rest.strip())
            return
        if W == "PLAY":
            letters = rest.strip()
            if len(letters) >= 2 and letters.startswith('"') and letters.endswith('"'):
                letters = letters[1:-1]
            self.out("__PLAY__", letters)
            return
        if W == "DIM":
            found = False
            for m in re.finditer(r"([A-Za-z_][A-Za-z0-9_]*\$?)\s*\(\s*(\d+)\s*\)", t):
                found = True
                self.out("__DIM__", f"{m.group(1).upper()},{m.group(2)}")
            if not found:
                raise SyntaxError(f"DIM 语法: DIM A(n) — 得 {t!r}")
            return
        if W == "POKE":
            self.out("__POKE__", rest.strip())
            return
        if W == "LET":
            self.c_let(rest.strip())
            return
        if W == "IF":
            self.c_if(t, block_stack)
            return
        if W == "FOR":
            self.c_for(t, block_stack)
            return
        if W == "NEXT":
            self.c_next(t, block_stack)
            return
        if W == "WHILE":
            lab, end = self.lbl("WH"), self.lbl("WE")
            self.out_label(lab)
            self.out("__WHILE__", rest.strip() + f" => {end}")
            block_stack.append(("WHILE", lab, end))
            return
        if W == "WEND":
            if not block_stack or block_stack[-1][0] != "WHILE":
                raise SyntaxError("WEND 无匹配 WHILE")
            _, lab, end = block_stack.pop()
            self.out("JMP", lab)
            self.out_label(end)
            return
        if W == "DO":
            lab = self.lbl("DO")
            self.out_label(lab)
            block_stack.append(("DO", lab, None))
            return
        if W == "LOOP":
            if not block_stack or block_stack[-1][0] != "DO":
                raise SyntaxError("LOOP 无匹配 DO")
            _, lab, _ = block_stack.pop()
            m = re.match(r"(WHILE|UNTIL)\s+(.+)", rest.strip(), re.I)
            if m:
                self.out("__DOCHK__", f"{m.group(1).upper()} {m.group(2)} => {lab}")
            else:
                self.out("JMP", lab)
            return
        # 隐式赋值 X = ... / A(i) = ... (允许嵌套括号下标)
        _sp = split_assignment(t)
        if _sp and parse_lhs(_sp[0]) is not None:
            self.c_let(t)
            return
        raise SyntaxError(f"未知语句: {t}")

    # ---- PRINT ----
    def c_print(self, rest):
        if not rest.strip():
            self.out("__PRINTLN__", "")
            return
        items = split_top(rest, ";")
        items = [p.strip() for p in items if p.strip() != ""]
        newline = not rest.rstrip().endswith(";")
        self.out("__PRINT__", "\n".join(items) + ("\n<NL>" if newline else "\n<NONE>"))

    def c_input(self, rest):
        m = re.match(r'^(?:"([^"]*)"\s*;\s*)?([A-Za-z_][A-Za-z0-9_]*\$?(\([^)]*\))?)\s*$',
                     rest.strip(), re.I)
        if not m:
            raise SyntaxError(f"INPUT 语法: INPUT [提示;] 变量 — 得 {rest!r}")
        prompt, var = m.group(1) or "? ", m.group(2)
        self.out("__INPUT__", f"{prompt}\n{var.upper()}")

    def c_let(self, rest):
        parts = split_assignment(rest)
        if not parts:
            raise SyntaxError(f"赋值语法错误: {rest}")
        lhs, expr = parts
        parsed = parse_lhs(lhs)
        if not parsed:
            raise SyntaxError(f"赋值语法错误: {rest}")
        var, idx = parsed
        if idx is not None:
            self.out("__SETIDX__", f"{var},{idx},{expr}")
        else:
            self.out("__LET__", f"{var} = {expr}")

    def c_if(self, t, block_stack):
        m = re.match(r"IF\s+(.+?)\s+THEN\s+(.+)$", t.strip(), re.I | re.S)
        if not m:
            raise SyntaxError(f"IF 语法: IF 条件 THEN ... — 得 {t!r}")
        cond, then = m.group(1), m.group(2).strip()
        me = re.match(r"^(.+?)\s+ELSE\s+(.+)$", then, re.I | re.S)
        else_part = None
        if me:
            then, else_part = me.group(1).strip(), me.group(2).strip()
        mg = re.match(r"^(?:GO\s*TO|GOTO|GOSUB)\s+(\d+)$", then.strip(), re.I)
        mn = re.match(r"^(\d+)$", then.strip())
        if (mg or mn) and not else_part:
            ln = int((mg or mn).group(1))
            op = "CALL" if "GOSUB" in then.upper() else "JMP"
            self.out("__IFJ__", f"{cond} ? {op} LINE{ln}")
            return
        end = self.lbl("IF")
        if else_part:
            els = self.lbl("IE")
            self.out("__IF__", f"{cond} ? ELSE {els}")
            for part in split_top(then, ":"):
                self.compile_one(part.strip(), block_stack)
            self.out("JMP", end)
            self.out_label(els)
            for part in split_top(else_part, ":"):
                self.compile_one(part.strip(), block_stack)
            self.out_label(end)
        else:
            self.out("__IF__", f"{cond} ? END {end}")
            for part in split_top(then, ":"):
                self.compile_one(part.strip(), block_stack)
            self.out_label(end)

    def c_for(self, t, block_stack):
        m = re.match(r"FOR\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+?)\s+TO\s+(.+?)(\s+STEP\s+(.+))?$",
                     t.strip(), re.I | re.S)
        if not m:
            raise SyntaxError(f"FOR 语法: FOR X = a TO b [STEP s] — 得 {t!r}")
        var, a, b, s = m.group(1).upper(), m.group(2), m.group(3), m.group(5)
        top, end = self.lbl("FT"), self.lbl("FE")
        self.out("__FOR__", f"{var} = {a} TO {b} STEP {s or '1'} => {top},{end}")
        self.out_label(top)
        block_stack.append(("FOR", var, top, end))

    def c_next(self, t, block_stack):
        if not block_stack or block_stack[-1][0] != "FOR":
            raise SyntaxError("NEXT 无匹配 FOR")
        _, fvar, top, end = block_stack.pop()
        self.out("__NEXT__", f"{fvar} => {top},{end}")
        self.out_label(end)


# ---------------- 运行时 ----------------

class LetterBasic:
    """LetterBASIC 解释器: 执行编译产物, 控制流全编译成 ISA 跳转"""

    def __init__(self, on_print=print, on_input=None, trace=None, beep=None):
        self.on_print = on_print
        self.on_input = on_input
        self.trace = trace      # fn(isa_op, isa_arg, snapshot)
        self.beep = beep        # fn(freq_hz, seconds) 播放脉冲音
        self.reset()

    def reset(self):
        self.num = {}
        self.str = {}
        self.arr = {}
        self.for_stack = []
        self.gosub_stack = []
        self.pc = 0
        self.prog = []
        self.labels = {}
        self.halted = False
        self.out_line = ""

    # ---- 装载 ----
    def load(self, source):
        stmts = self.parse_program(source)
        comp = BasicCompiler()
        code = comp.compile_lines(stmts)
        self.prog = []
        self.labels = {}
        for op, arg in code:
            if op == "__LABEL__":
                self.labels[arg] = len(self.prog)
            else:
                self.prog.append([op, arg])
        self.pc = 0
        self.halted = False
        return stmts

    @staticmethod
    def parse_program(source):
        stmts = []
        for raw in source.splitlines():
            s = strip_comment(raw).strip()
            if not s:
                continue
            m = re.match(r"^(\d+)\s+(.*)$", s)
            if m:
                stmts.append((int(m.group(1)), m.group(2)))
            else:
                stmts.append((None, s))
        if any(l is not None for l, _ in stmts):
            numbered = sorted([p for p in stmts if p[0] is not None])
            stmts = numbered + [p for p in stmts if p[0] is None]
        return stmts

    # ---- 变量 / 数组 ----
    def getvar(self, name):
        name = name.upper()
        if name.endswith("$"):
            if name in self.str:
                return self.str[name]
            if name[:-1] in self.str:
                return self.str[name[:-1]]
            raise NameError(f"未定义字符串变量 {name}")
        if name in self.num:
            return self.num[name]
        raise NameError(f"未定义变量 {name}")

    def setvar(self, name, val):
        name = name.upper()
        if name.endswith("$") or isinstance(val, str):
            key = name if name.endswith("$") else name + "$"
            self.str[key] = str(val)
            self.str[key.rstrip("$")] = str(val)
        else:
            self.num[name] = num(val)

    def array_has(self, name):
        return name.upper() in self.arr

    def array_get(self, name, i):
        name = name.upper()
        arr = self.arr.get(name, [])
        if 0 <= i < len(arr):
            return arr[i]
        return 0

    def array_set(self, name, i, val):
        name = name.upper()
        if name not in self.arr:
            self.arr[name] = [0] * 256
        while len(self.arr[name]) <= i:
            self.arr[name].append(0 if not name.endswith("$") else "")
        self.arr[name][i] = val

    def builtin(self, name, args):
        n = name.upper().rstrip("$")
        a = args[0] if args else 0
        if n == "ABS":
            return abs(num(a))
        if n == "INT":
            try:
                return math.floor(float(a)) if isinstance(a, float) else num(a)
            except (TypeError, ValueError):
                return 0
        if n == "RND":
            if args:
                return random.randint(1, max(1, num(a)))
            return random.random()
        if n == "LEN":
            return len(str(a))
        if n == "ASC":
            s = str(a)
            return ord(s[0]) if s else 0
        if n == "VAL":
            s = str(a).strip()
            if re.fullmatch(r"-?\d+", s):
                return int(s)
            return S2V(s.upper()) if re.fullmatch(r"[A-Za-z]+", s) else 0
        if n in ("CHR", "CHR$"):
            return chr(num(a) % 0x110000)
        raise NameError(f"未知函数 {name}")

    def ev(self, expr):
        p = ExprParser(self.getvar, self.builtin)
        p.array_has = self.array_has
        p.array_get = self.array_get
        return p.parse(expr)

    def emit(self, s, end="\n"):
        if end == "":
            self.out_line += str(s)
        else:
            text = self.out_line + str(s)
            self.out_line = ""
            self.on_print(text)

    # ---- 单步 ----
    def step(self):
        if self.halted or self.pc >= len(self.prog):
            self.halted = True
            return None
        op, arg = self.prog[self.pc]
        cur = self.pc
        if self.trace:
            self.trace(op, arg, {"num": dict(self.num), "str": dict(self.str),
                                "pc": self.pc, "halted": self.halted})

        if op == "BEAT":
            self.pc += 1
            return {"op": op, "pc": cur}
        if op == "NOP":
            self.pc += 1
            return {"op": op, "pc": cur}
        if op == "HLT":
            self.halted = True
            if self.out_line:
                self.emit("", end="\n")
            self.pc += 1
            return {"op": op, "pc": cur, "halted": True}
        if op == "JMP":
            self.pc = self._lbl(arg)
            return {"op": op, "pc": cur}
        if op == "CALL":
            self.gosub_stack.append(self.pc + 1)
            self.pc = self._lbl(arg)
            return {"op": op, "pc": cur}
        if op == "RET":
            if not self.gosub_stack:
                raise RuntimeError("RETURN 无匹配 GOSUB")
            self.pc = self.gosub_stack.pop()
            return {"op": op, "pc": cur}
        if op == "__CLS__":
            self.emit("(清屏)", end="\n")
            self.pc += 1
            return {"op": "CLS", "pc": cur}
        if op == "__SLEEP__":
            secs = max(0, min(5, num(self.ev(arg)) if arg.strip() else 0))
            time.sleep(secs)
            self.pc += 1
            return {"op": "SLEEP", "pc": cur}
        if op == "__SOUND__":
            parts = split_top(arg or "")
            freq = num(self.ev(parts[0])) if len(parts) > 0 and parts[0].strip() else 440
            dur = max(0, min(5, num(self.ev(parts[1])) if len(parts) > 1 else 1))
            self.emit(f"♪ SOUND {freq}Hz {dur}s", end="\n")
            if self.beep:
                self.beep(freq, dur)
            else:
                time.sleep(min(dur, 1))
            self.pc += 1
            return {"op": "SOUND", "pc": cur}
        if op == "__PLAY__":
            letters = "".join(c for c in (arg or "").upper() if c.isalpha())
            self.emit(f"♪ PLAY {letters} (脉冲音阶, {len(letters)} 个字母)", end="\n")
            if self.beep:
                for c in letters:
                    self.beep(220 * (2 ** (S2V(c) / 12)), 0.22)
            self.pc += 1
            return {"op": "PLAY", "pc": cur}
        if op == "__LET__":
            var, _, expr = arg.partition("=")
            var, expr = var.strip().upper(), expr.strip()
            val = self.ev(expr)
            self.setvar(var, val)
            self.pc += 1
            return {"op": "LET", "pc": cur, "detail": f"{var}={val!r}"}
        if op == "__SETIDX__":
            parts = split_top(arg)
            if len(parts) < 3:
                raise SyntaxError(f"数组赋值错误: {arg}")
            var = parts[0].strip().upper()
            i = num(self.ev(parts[1].strip()))
            val = self.ev(",".join(parts[2:]))
            self.array_set(var, i, val)
            self.pc += 1
            return {"op": "SETIDX", "pc": cur}
        if op == "__DIM__":
            name, _, size = arg.partition(",")
            self.arr[name.strip().upper()] = [0] * int(size.strip())
            self.pc += 1
            return {"op": "DIM", "pc": cur}
        if op == "__POKE__":
            parts = split_top(arg)
            if len(parts) < 3:
                raise SyntaxError(f"POKE 语法: POKE 数组,下标,值 — 得 {arg!r}")
            arr = parts[0].strip().upper()
            self.array_set(arr, num(self.ev(parts[1].strip())), self.ev(",".join(parts[2:])))
            self.pc += 1
            return {"op": "POKE", "pc": cur}
        if op == "__PRINT__":
            items_raw, mode = arg.rsplit("\n", 1)
            items = items_raw.split("\n") if items_raw else []
            out = ""
            for it in items:
                v = self.ev(it)
                if isinstance(v, str):
                    out += v
                else:
                    out += f"{V2S(v)}({v}) " if v >= 0 else f"{v} "
            if mode == "<NL>":
                self.emit(out, end="\n")
            else:
                self.emit(out, end="")
            self.pc += 1
            return {"op": "PRINT", "pc": cur, "output": out}
        if op == "__PRINTLN__":
            self.emit("", end="\n")
            self.pc += 1
            return {"op": "PRINT", "pc": cur}
        if op == "__INPUT__":
            prompt, var = arg.split("\n", 1)
            q = prompt + " " if prompt else "? "
            raw_in = self.ask(q).strip()
            self._store_input(var.strip(), raw_in)
            self.pc += 1
            return {"op": "INPUT", "pc": cur}
        if op == "__IF__":
            cond, _, target = arg.partition("?")
            v = num(self.ev(cond.strip()))
            dest = target.strip().split()[-1]
            if v:
                self.pc += 1
            else:
                self.pc = self._lbl(dest)
            return {"op": "IF", "pc": cur, "cond": v}
        if op == "__IFJ__":
            cond, _, jmp = arg.partition("?")
            v = num(self.ev(cond.strip()))
            bits = jmp.strip().split()
            how, dest = bits[0], bits[1]
            if v:
                if how == "CALL":
                    self.gosub_stack.append(self.pc + 1)
                self.pc = self._lbl(dest)
            else:
                self.pc += 1
            return {"op": "IF", "pc": cur, "cond": v}
        if op == "__FOR__":
            m = re.match(r"(\w+)\s*=\s*(.+)\s+TO\s+(.+)\s+STEP\s+(.+)\s*=>\s*(\w+),(\w+)", arg)
            if not m:
                raise SyntaxError(f"FOR 内部错误: {arg}")
            var, top, end = m.group(1), m.group(5), m.group(6)
            va, vb, vs = num(self.ev(m.group(2))), num(self.ev(m.group(3))), num(self.ev(m.group(4)))
            if vs == 0:
                raise RuntimeError("STEP 不能为 0")
            self.num[var] = va
            self.for_stack.append({"var": var, "end": vb, "step": vs,
                                   "top": self._lbl(top), "endpc": self._lbl(end)})
            self.pc += 1
            return {"op": "FOR", "pc": cur}
        if op == "__NEXT__":
            if not self.for_stack:
                raise SyntaxError("NEXT 无匹配 FOR")
            _, _, rest = arg.partition("=>")
            top, end = [x.strip() for x in rest.split(",")]
            fr = self.for_stack[-1]
            self.num[fr["var"]] = self.num.get(fr["var"], 0) + fr["step"]
            c, e, st = self.num[fr["var"]], fr["end"], fr["step"]
            alive = (c <= e) if st > 0 else (c >= e)
            if alive:
                self.pc = self._lbl(top)
            else:
                self.for_stack.pop()
                self.pc = self._lbl(end)
            return {"op": "NEXT", "pc": cur}
        if op == "__WHILE__":
            cond, _, end = arg.partition("=>")
            v = num(self.ev(cond.strip()))
            if v:
                self.pc += 1
            else:
                self.pc = self._lbl(end.strip())
            return {"op": "WHILE", "pc": cur, "cond": v}
        if op == "__DOCHK__":
            m = re.match(r"(WHILE|UNTIL)\s+(.+)\s*=>\s*(\w+)", arg)
            kw, cond, lab = m.group(1), m.group(2), m.group(3)
            v = num(self.ev(cond))
            go_back = (v != 0) if kw == "WHILE" else (v == 0)
            self.pc = self._lbl(lab) if go_back else self.pc + 1
            return {"op": "LOOP", "pc": cur}
        raise RuntimeError(f"未实现伪指令: {op} {arg}")

    def _lbl(self, name):
        if name not in self.labels:
            raise NameError(f"未知行号/标签: {name} (GOTO/GOSUB 的行号不存在?)")
        return self.labels[name]

    def _store_input(self, var, raw_in):
        var = var.strip().upper()
        if var.endswith("$"):
            self.str[var] = raw_in
            self.str[var.rstrip("$")] = raw_in
            return
        parsed = parse_lhs(var)
        if parsed and parsed[1] is not None:
            self.array_set(parsed[0], num(self.ev(parsed[1])),
                           self.coerce_num(raw_in))
        else:
            self.num[var.rstrip("$")] = self.coerce_num(raw_in)

    @staticmethod
    def coerce_num(raw_in):
        raw_in = raw_in.strip()
        if re.fullmatch(r"-?\d+", raw_in):
            return int(raw_in)
        if re.fullmatch(r"[A-Za-z]+", raw_in):
            return S2V(raw_in.upper())
        try:
            return int(raw_in)
        except ValueError:
            return 0

    def ask(self, prompt="? "):
        if self.on_input:
            return self.on_input(prompt)
        try:
            return input(prompt)
        except EOFError:
            return ""

    def run(self, max_steps=100000):
        n = 0
        while not self.halted and n < max_steps:
            self.step()
            n += 1
        if n >= max_steps:
            raise RuntimeError("步数超限(死循环?)")
        if self.out_line:
            self.on_print(self.out_line)
            self.out_line = ""


HELP_TEXT = """LetterBASIC 命令一览:
  PRINT 项[;项...] / ?     输出, 数字自动显示 字母(十进制), 如 HELLO(123)
  INPUT [提示;] X          输入数字/字母串(字母串按26进制转数字)
  LET X = 表达式           赋值 (LET 可省略, 如 X = 5)
  X$ = "文本"              字符串变量, & 拼接
  IF 条件 THEN ... [ELSE ...]   条件执行; 或 THEN GOTO 行号 / THEN 行号
  GOTO 行号 / GOSUB 行号 / RETURN
  FOR X = a TO b [STEP s] ... NEXT [X]   (可嵌套, STEP 可为负)
  WHILE 条件 ... WEND / DO ... LOOP WHILE|UNTIL 条件
  DIM A(n) / A(i) 读写 / POKE A,i,v / PEEK(A,i)
  SOUND 频率,时长 / PLAY "CDE"(脉冲音阶) / SLEEP 秒 / CLS
  REM 或 ' 注释 / 行号可选 / END 结束
表达式: + - * / MOD ( ) < > = <= >= <> AND OR NOT
函数: ABS() INT() RND(n)/RND LEN() ASC() CHR$() VAL()
特殊: 纯字母串可直接当数字用 (Z+B=BA), 数组下标读取直接 A(i)
例: 10 PRINT "HELLO" : 20 FOR I=1 TO 3 : PRINT I : NEXT I
输入 HELP 看帮助, DEMO 跑演示, QUIT 退出。
"""

DEMO_PROG = """10 REM LetterBASIC 演示: 斐波那契 + 脉冲音阶
20 PRINT "HELLO 26-CPU, 我是 LetterBASIC!"
30 PRINT "Z+B="; Z+B; " (26进制进位)"
40 DIM F(10)
50 F(0) = 0 : F(1) = 1
60 FOR I = 2 TO 9
70   F(I) = F(I-1) + F(I-2)
80 NEXT I
90 PRINT "斐波那契前10项:"
100 FOR I = 0 TO 9
110   PRINT "F("; I; ")="; F(I)
120 NEXT I
130 PLAY "CDEFGAB"
140 END
"""


def run_source(source, on_print=print, on_input=None, trace=None, beep=None):
    lb = LetterBasic(on_print=on_print, on_input=on_input, trace=trace, beep=beep)
    lb.load(source)
    lb.run()
    return lb


def repl():
    print("🌟 LetterBASIC v1.1 — 跑在 LetterCPU-26 上的 QBASIC 方言")
    print("输入 HELP 看帮助, DEMO 跑演示, QUIT 退出。直接粘贴多行, 空行执行。")
    buf = []
    while True:
        try:
            line = input("LBASIC> " if not buf else "......> ")
        except (EOFError, KeyboardInterrupt):
            print("\n再见!")
            break
        s = line.strip()
        if not buf and s.upper() in ("QUIT", "EXIT"):
            print("再见!")
            break
        if not buf and s.upper() == "HELP":
            print(HELP_TEXT)
            continue
        if not buf and s.upper() == "DEMO":
            run_source(DEMO_PROG)
            continue
        buf.append(line)
        if line.strip() == "":
            src = "\n".join(buf)
            buf = []
            if src.strip():
                try:
                    run_source(src)
                except Exception as e:
                    print(f"❌ {e}")


def main(argv):
    if len(argv) > 1:
        with open(argv[1], encoding="utf-8") as f:
            src = f.read()
        run_source(src)
    else:
        repl()


if __name__ == "__main__":
    main(sys.argv)
