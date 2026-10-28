#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LetterCPU-26 — 用 26 个英文字母做计算的虚拟芯片内核
=====================================================
一个"字母位(Lit)"有 26 种状态: A=0, B=1, ..., Z=25
数字 = 26 进制字母串, 比如:
    B + C = D        (1 + 2 = 3)
    Z + B = BA       (25 + 1 = 26, 产生进位)
    HELLO = H*26^4 + E*26^3 + L*26^2 + L*26 + O

指令集 Letter-ISA v1:
    LDA X   加载 (立即数字母串 / 内存标签)
    ADD X / SUB X / MUL X / DIV X
    STA NAME  存累加器到内存
    JMP L / JZ L / JNZ L   跳转
    OUT     输出累加器 (字母 + 十进制对照)
    HLT     停机
    NOP     空操作

内存预置:  NAME = WORD   (例如  DATA = HELLO)
操作数:    单个字母 B / 字母串 HELLO / 内存名 DATA
"""

ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
CHAR_TO_VAL = {c: i for i, c in enumerate(ALPHABET)}
BASE = 26


def str_to_val(s: str) -> int:
    """字母串(26进制) -> 十进制整数, 如 'BA' -> 26"""
    s = s.strip().upper()
    if not s or any(c not in CHAR_TO_VAL for c in s):
        raise ValueError(f"非法字母数: {s!r} (只允许 A~Z)")
    v = 0
    for c in s:
        v = v * BASE + CHAR_TO_VAL[c]
    return v


def val_to_str(n: int) -> str:
    """十进制整数 -> 字母串, 如 26 -> 'BA', 0 -> 'A'"""
    if n < 0:
        raise ValueError("LetterCPU 只演示非负数 (负数显示为 -XXX)")
    if n == 0:
        return "A"
    out = []
    while n > 0:
        n, r = divmod(n, BASE)
        out.append(ALPHABET[r])
    return "".join(reversed(out))


def fmt(n: int) -> str:
    """同时显示字母形态和十进制: HELLO(123456)"""
    if n < 0:
        return f"-{val_to_str(-n)}({n})"
    return f"{val_to_str(n)}({n})"


class LetterCPU:
    """26字母虚拟 CPU"""

    OPS_1ARG = {"LDA", "ADD", "SUB", "MUL", "DIV", "STA", "JMP", "JZ", "JNZ"}
    OPS_0ARG = {"OUT", "HLT", "NOP"}

    def __init__(self):
        self.reset()

    def reset(self):
        self.acc = 0          # 累加器(主寄存器)
        self.pc = 0           # 程序计数器
        self.zero = True      # 零标志
        self.halted = False
        self.instructions = []  # [(op, arg, raw)]
        self.labels = {}        # label -> 指令下标
        self.memory = {}        # NAME -> int
        self.outputs = []       # OUT 采集
        self.steps = 0

    # ---------- 汇编 ----------
    def assemble(self, source: str):
        self.reset()
        pending_labels = []
        for lineno, raw in enumerate(source.splitlines(), 1):
            line = raw.split(";")[0].strip().upper()
            if not line:
                continue
            # 数据定义: NAME = WORD
            if "=" in line:
                name, _, word = line.partition("=")
                name, word = name.strip(), word.strip()
                if not name.replace("_", "").isalpha() or not word.isalpha():
                    raise SyntaxError(f"第{lineno}行数据定义错误: {raw}")
                self.memory[name] = str_to_val(word)
                continue
            # 标签: LOOP:
            if line.endswith(":"):
                label = line[:-1].strip()
                if not label:
                    raise SyntaxError(f"第{lineno}行空标签: {raw}")
                pending_labels.append(label)
                continue
            parts = line.split()
            op, arg = parts[0], (parts[1] if len(parts) > 1 else None)
            if op not in self.OPS_1ARG and op not in self.OPS_0ARG:
                raise SyntaxError(f"第{lineno}行未知指令 {op}: {raw}")
            if op in self.OPS_1ARG and arg is None:
                raise SyntaxError(f"第{lineno}行 {op} 缺少操作数: {raw}")
            idx = len(self.instructions)
            for lb in pending_labels:
                if lb in self.labels:
                    raise SyntaxError(f"重复标签: {lb}")
                self.labels[lb] = idx
            pending_labels.clear()
            self.instructions.append([op, arg, raw.strip()])
        for lb in pending_labels:  # 末尾孤立标签指向结尾
            self.labels[lb] = len(self.instructions)

    # ---------- 取操作数值 ----------
    def resolve(self, arg):
        if arg is None:
            return None
        a = arg.strip().upper()
        if a.startswith("[") and a.endswith("]"):
            a = a[1:-1]
        if a in self.memory:
            return self.memory[a]
        return str_to_val(a)  # 纯字母串 = 26进制立即数

    # ---------- 单步 ----------
    def step(self):
        if self.halted or self.pc >= len(self.instructions):
            self.halted = True
            return None
        op, arg, raw = self.instructions[self.pc]
        cur = self.pc
        info = {"pc": cur, "op": op, "arg": arg, "raw": raw}

        if op == "LDA":
            self.acc = self.resolve(arg)
        elif op == "ADD":
            self.acc += self.resolve(arg)
        elif op == "SUB":
            self.acc -= self.resolve(arg)
        elif op == "MUL":
            self.acc *= self.resolve(arg)
        elif op == "DIV":
            d = self.resolve(arg)
            if d == 0:
                raise ZeroDivisionError(f"PC={cur}: DIV A 除以零")
            self.acc //= d
        elif op == "STA":
            self.memory[arg.strip().upper().strip("[]")] = self.acc
        elif op == "JMP":
            self.pc = self._jump(arg); info["jump"] = True
            return self._finish_step(info)
        elif op == "JZ":
            if self.acc == 0:
                self.pc = self._jump(arg); info["jump"] = True
                return self._finish_step(info)
        elif op == "JNZ":
            if self.acc != 0:
                self.pc = self._jump(arg); info["jump"] = True
                return self._finish_step(info)
        elif op == "OUT":
            self.outputs.append(self.acc)
            info["output"] = self.acc
        elif op == "HLT":
            self.halted = True
            return self._finish_step(info, halted=True)
        elif op == "NOP":
            pass

        self.zero = (self.acc == 0)
        self.pc += 1
        self.steps += 1
        info.update(acc=self.acc, zero=self.zero, halted=self.halted)
        return info

    def _jump(self, label):
        lb = label.strip().upper()
        if lb not in self.labels:
            raise NameError(f"未知标签: {label}")
        return self.labels[lb]

    def _finish_step(self, info, halted=False):
        self.zero = (self.acc == 0)
        if not halted:
            self.steps += 1
        else:
            self.halted = True
        info.update(acc=self.acc, zero=self.zero, halted=self.halted)
        return info

    def run(self, max_steps=10000, on_step=None):
        while not self.halted and self.steps < max_steps:
            info = self.step()
            if on_step:
                on_step(info)
            if self.pc >= len(self.instructions):
                self.halted = True
        return self.outputs


DEMO_HELLO_WORLD = """; LetterCPU-26 演示: HELLO + WORLD (26进制大数加法)
LDA HELLO
ADD WORLD
STA RESULT
OUT
HLT
"""

DEMO_COUNTDOWN = """; 倒数循环: 从 E(4) 倒数到 A(0), 每次 OUT
COUNT = E
LDA COUNT
LOOP:
OUT
JZ DONE
SUB B
JMP LOOP
DONE:
HLT
"""


def demo():
    print("=" * 60)
    print("  LetterCPU-26 演示  (A=0 ... Z=25, 26进制)")
    print("=" * 60)
    print("\n【1】字母加法: HELLO + WORLD")
    cpu = LetterCPU()
    cpu.assemble(DEMO_HELLO_WORLD)
    cpu.memory["HELLO"] = str_to_val("HELLO")
    cpu.memory["WORLD"] = str_to_val("WORLD")
    print(f"  HELLO = {fmt(cpu.memory['HELLO'])}")
    print(f"  WORLD = {fmt(cpu.memory['WORLD'])}")
    cpu.run()
    print(f"  结果  = {fmt(cpu.outputs[-1])}   <-- 字母真的在算数!")

    print("\n【2】Z + B = BA (进位演示)")
    print(f"  Z({25}) + B({1}) = {fmt(25 + 1)}")

    print("\n【3】倒数循环 E->A, 每次 OUT:")
    cpu2 = LetterCPU()
    cpu2.assemble(DEMO_COUNTDOWN)
    cpu2.run()
    print("  " + " -> ".join(fmt(v) for v in cpu2.outputs))

    print("\n【4】一个 Lit 的信息量 = log2(26) ≈ 4.7 bit, 是二进制位的 4.7 倍")


if __name__ == "__main__":
    demo()
