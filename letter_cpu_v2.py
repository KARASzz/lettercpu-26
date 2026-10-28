#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
letter_cpu_v2.py — LetterCPU-26 v2 芯片内核 (Letter-ISA v2)
===========================================================
相对 v1 的升级 (为了跑 BASIC):
  寄存器: ACC(数字) SACC(字符串) IX(变址) SP(栈指针, 隐含)
  标志: ZF(零) NF(负, ACC<比较值)
  数据栈 + 调用栈 (PUSH/POP, CALL/RET -> GOSUB 的硬件基础)
  数字串双内存: mem_num / mem_str
  字符串输出 PRS, 数字输入 INP, 比较 CMP + JG/JL/JGE/JLE

数字显示永远是 字母(十进制), 如 HELLO(123456)。
内存预置: NAME = 123 / NAME = HELLO(26进制) / NAME$ = "文本"
"""
import re

ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
CHAR_TO_VAL = {c: i for i, c in enumerate(ALPHABET)}
BASE = 26


def str_to_val(s):
    s = s.strip().upper()
    if not s or any(c not in CHAR_TO_VAL for c in s):
        raise ValueError(f"非法字母数: {s!r}")
    v = 0
    for c in s:
        v = v * BASE + CHAR_TO_VAL[c]
    return v


def val_to_str(n):
    if n < 0:
        return "-" + val_to_str(-n)
    if n == 0:
        return "A"
    out = []
    while n > 0:
        n, r = divmod(n, BASE)
        out.append(ALPHABET[r])
    return "".join(reversed(out))


def fmt(n):
    if n < 0:
        return f"-{val_to_str(-n)}({n})"
    return f"{val_to_str(n)}({n})"


def is_decimal(tok):
    return re.fullmatch(r"-?\d+", tok or "") is not None


class LetterCPUv2:
    OPS_1 = {"LDA", "STA", "ADD", "SUB", "MUL", "DIV", "MOD", "CMP",
             "JMP", "JZ", "JNZ", "JG", "JL", "JGE", "JLE",
             "CALL", "PUSH", "POP", "PRS", "LDS", "STS", "CATS",
             "INP", "LDX", "STX"}
    OPS_0 = {"OUT", "PRTS", "HLT", "NOP", "RET", "CLR", "POFF", "BEAT"}

    def __init__(self, on_input=None, on_output=None):
        self.on_input = on_input      # fn(prompt)->str
        self.on_output = on_output    # fn(text)->None
        self.reset()

    def reset(self):
        self.acc = 0
        self.sacc = ""
        self.ix = 0
        self.zf = True
        self.nf = False
        self.halted = False
        self.pc = 0
        self.steps = 0
        self.instr = []       # (op, arg, raw)
        self.labels = {}
        self.mem_num = {}
        self.mem_str = {}
        self.stack = []
        self.callstack = []
        self.outputs = []

    # ---------------- 汇编 ----------------
    def assemble(self, source):
        self.reset()
        pend = []
        for lineno, raw in enumerate(source.splitlines(), 1):
            line = raw.split(";")[0].strip()
            if not line:
                continue
            up = line.upper()
            # 数据定义 NAME = ... (操作码开头的行不算, 如 PRS "A=B")
            first = up.split()[0] if up.split() else ""
            if "=" in line and first not in self.OPS_1 and first not in self.OPS_0:
                name, _, rhs = line.partition("=")
                name, rhs = name.strip().upper(), rhs.strip()
                if not re.fullmatch(r"[A-Z_][A-Z0-9_]*\$?", name):
                    raise SyntaxError(f"第{lineno}行变量名错误: {raw}")
                if len(rhs) >= 2 and rhs.startswith('"') and rhs.endswith('"'):
                    self.mem_str[name.rstrip("$")] = rhs[1:-1]
                    if name.endswith("$"):
                        self.mem_str[name[:-1]] = rhs[1:-1]
                    else:
                        self.mem_str[name] = rhs[1:-1]
                elif rhs.upper() in self.mem_num or rhs.upper() in self.mem_str:
                    pass  # 允许稍后 resolve, 这里先记? 简化: 当立即数处理在运行时
                elif re.fullmatch(r"-?\d+", rhs):
                    self.mem_num[name.rstrip("$")] = int(rhs)
                elif re.fullmatch(r"[A-Za-z]+", rhs):
                    self.mem_num[name.rstrip("$")] = str_to_val(rhs)
                else:
                    raise SyntaxError(f"第{lineno}行数据定义错误: {raw}")
                continue
            if up.endswith(":") and '"' not in line:
                lb = up[:-1].strip()
                if not re.fullmatch(r"[A-Z_][A-Z0-9_]*", lb):
                    raise SyntaxError(f"第{lineno}行标签错误: {raw}")
                pend.append(lb)
                continue
            op, _, rest = line.partition(" ")
            op, arg = op.strip().upper(), rest.strip()
            if op not in self.OPS_1 and op not in self.OPS_0:
                raise SyntaxError(f"第{lineno}行未知指令 {op}: {raw}")
            if op in self.OPS_1 and not arg:
                raise SyntaxError(f"第{lineno}行 {op} 缺操作数: {raw}")
            if op in self.OPS_0:
                arg = None
            idx = len(self.instr)
            for lb in pend:
                if lb in self.labels:
                    raise SyntaxError(f"重复标签: {lb}")
                self.labels[lb] = idx
            pend.clear()
            self.instr.append([op, arg, raw.strip()])
        for lb in pend:
            self.labels[lb] = len(self.instr)

    # ---------------- 取值 ----------------
    def _num(self, arg):
        if arg is None:
            raise ValueError("缺少操作数")
        a = arg.strip()
        # [MEM] 去括号
        if a.startswith("[") and a.endswith("]"):
            a = a[1:-1].strip()
        up = a.upper()
        # 字符串字面量不能当数字
        if len(a) >= 2 and a.startswith('"') and a.endswith('"'):
            raise ValueError(f"字符串不能当数字用: {a}")
        if up in self.mem_num:
            return self.mem_num[up.rstrip("$")]
        if is_decimal(a):
            return int(a)
        if re.fullmatch(r"[A-Za-z]+", a):
            # 内存字符串? 先查, 没有就当26进制立即数
            if up in self.mem_str:
                raise ValueError(f"{a} 是字符串, 不能当数字用")
            return str_to_val(a)
        raise NameError(f"未知数字操作数: {arg}")

    def _str(self, arg):
        if arg is None:
            return self.sacc
        a = arg.strip()
        if len(a) >= 2 and a.startswith('"') and a.endswith('"'):
            return a[1:-1]
        up = a.upper().strip("[]")
        if up in self.mem_str:
            return self.mem_str[up.rstrip("$")]
        if up.rstrip("$") in self.mem_str:
            return self.mem_str[up.rstrip("$")]
        if up in self.mem_num:
            return val_to_str(self.mem_num[up])
        # 裸字母串当字面文本
        if re.fullmatch(r"[A-Za-z ]+", a):
            return a
        raise NameError(f"未知字符串操作数: {arg}")

    def emit(self, text):
        self.outputs.append(str(text))
        if self.on_output:
            self.on_output(str(text))

    def ask(self, prompt="? "):
        if self.on_input:
            return self.on_input(prompt)
        try:
            return input(prompt)
        except EOFError:
            return ""

    # ---------------- 单步 ----------------
    def _jump(self, label):
        lb = label.strip().upper()
        if lb not in self.labels:
            raise NameError(f"未知标签: {label}")
        return self.labels[lb]

    def _flags(self, v):
        self.zf = (v == 0)
        self.nf = (v < 0)

    def step(self):
        if self.halted or self.pc >= len(self.instr):
            self.halted = True
            return None
        op, arg, raw = self.instr[self.pc]
        cur = self.pc
        info = {"pc": cur, "op": op, "arg": arg, "raw": raw}

        def nxt():
            self.pc += 1
            self.steps += 1
            info.update(acc=self.acc, sacc=self.sacc, zf=self.zf,
                        nf=self.nf, halted=self.halted)

        if op == "LDA":
            self.acc = self._num(arg)
            self._flags(self.acc)
            nxt(); return info
        if op == "STA":
            self.mem_num[arg.strip().upper().strip("[]").rstrip("$")] = self.acc
            nxt(); return info
        if op == "LDX":
            self.ix = self._num(arg); nxt(); return info
        if op == "STX":
            self.mem_num[arg.strip().upper().strip("[]").rstrip("$")] = self.ix
            nxt(); return info
        if op in ("ADD", "SUB", "MUL", "DIV", "MOD"):
            v = self._num(arg)
            if op == "ADD":
                self.acc += v
            elif op == "SUB":
                self.acc -= v
            elif op == "MUL":
                self.acc *= v
            elif op == "DIV":
                if v == 0:
                    raise ZeroDivisionError(f"PC={cur}: 除以零")
                self.acc //= v
            else:
                if v == 0:
                    raise ZeroDivisionError(f"PC={cur}: 除以零")
                self.acc %= v
            self._flags(self.acc)
            nxt(); return info
        if op == "CMP":
            d = self.acc - self._num(arg)
            self._flags(d)
            nxt(); info["cmp"] = d; return info
        if op == "JMP":
            self.pc = self._jump(arg); self.steps += 1
            info["jump"] = True; info.update(acc=self.acc, halted=self.halted); return info
        if op == "JZ":
            if self.zf:
                self.pc = self._jump(arg); self.steps += 1
                info["jump"] = True; info.update(acc=self.acc, halted=self.halted); return info
            nxt(); return info
        if op == "JNZ":
            if not self.zf:
                self.pc = self._jump(arg); self.steps += 1
                info["jump"] = True; info.update(acc=self.acc, halted=self.halted); return info
            nxt(); return info
        if op == "JG":
            if not self.zf and not self.nf:
                self.pc = self._jump(arg); self.steps += 1
                info["jump"] = True; info.update(acc=self.acc, halted=self.halted); return info
            nxt(); return info
        if op == "JL":
            if self.nf:
                self.pc = self._jump(arg); self.steps += 1
                info["jump"] = True; info.update(acc=self.acc, halted=self.halted); return info
            nxt(); return info
        if op == "JGE":
            if not self.nf:
                self.pc = self._jump(arg); self.steps += 1
                info["jump"] = True; info.update(acc=self.acc, halted=self.halted); return info
            nxt(); return info
        if op == "JLE":
            if self.zf or self.nf:
                self.pc = self._jump(arg); self.steps += 1
                info["jump"] = True; info.update(acc=self.acc, halted=self.halted); return info
            nxt(); return info
        if op == "CALL":
            self.callstack.append(self.pc + 1); self.pc = self._jump(arg)
            self.steps += 1; info["jump"] = True
            info.update(acc=self.acc, halted=self.halted); return info
        if op == "RET":
            if not self.callstack:
                raise RuntimeError(f"PC={cur}: RET 无返回地址")
            self.pc = self.callstack.pop(); self.steps += 1
            info["jump"] = True; info.update(acc=self.acc, halted=self.halted); return info
        if op == "PUSH":
            self.stack.append(self._num(arg)); nxt(); return info
        if op == "POP":
            if not self.stack:
                raise RuntimeError(f"PC={cur}: POP 空栈")
            self.mem_num[arg.strip().upper().strip("[]").rstrip("$")] = self.stack.pop()
            nxt(); return info
        if op == "POFF":
            if not self.stack:
                raise RuntimeError(f"PC={cur}: 空栈")
            self.acc = self.stack.pop(); self._flags(self.acc); nxt(); return info
        if op == "LDS":
            self.sacc = self._str(arg); nxt(); return info
        if op == "STS":
            self.mem_str[arg.strip().upper().strip("[]").rstrip("$").rstrip("$")] = self.sacc
            nxt(); return info
        if op == "CATS":
            self.sacc += self._str(arg); nxt(); return info
        if op == "PRS":
            self.emit(self._str(arg)); nxt(); info["output"] = self.sacc; return info
        if op == "PRTS":
            self.emit(self.sacc); nxt(); info["output"] = self.sacc; return info
        if op == "OUT":
            self.emit(f"{fmt(self.acc)}"); nxt(); info["output"] = self.acc; return info
        if op == "INP":
            name = (arg or "INPUT").strip().upper().strip("[]")
            raw_in = self.ask("? ").strip()
            if re.fullmatch(r"-?\d+", raw_in):
                val = int(raw_in)
            elif re.fullmatch(r"[A-Za-z]+", raw_in):
                val = str_to_val(raw_in.upper())
                self.emit(f"(收到字母数 {raw_in.upper()} = {val})")
            else:
                try:
                    val = int(raw_in)
                except ValueError:
                    val = 0
            self.mem_num[name.rstrip("$")] = val
            self.acc = val; self._flags(val)
            nxt(); return info
        if op == "CLR":
            self.acc = 0; self._flags(0); nxt(); return info
        if op == "BEAT":
            nxt(); return info
        if op == "NOP":
            nxt(); return info
        if op == "HLT":
            self.halted = True
            info.update(acc=self.acc, halted=True); return info
        raise RuntimeError(f"未实现: {op}")

    def run(self, max_steps=100000, on_step=None):
        while not self.halted and self.steps < max_steps:
            info = self.step()
            if on_step:
                on_step(info)
            if self.pc >= len(self.instr):
                self.halted = True
        if self.steps >= max_steps:
            raise RuntimeError("步数超限(死循环?)")
        return self.outputs


DEMO_FIB = """; LetterCPU v2: 斐波那契前 8 项 (ACC 永远显示 字母(十进制))
N = 8
LDA A
STA PREV
LDA B
STA CURR
LDA N
STA LEFT
LOOP:
LDA PREV
OUT
LDA CURR
STA TEMP
ADD PREV
STA NEXTV
LDA CURR
STA PREV
LDA NEXTV
STA CURR
LDA LEFT
SUB B
STA LEFT
CMP A
JNZ LOOP
HLT
"""
