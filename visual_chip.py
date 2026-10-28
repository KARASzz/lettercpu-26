#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
visual_chip.py — LetterCPU-26 可视化: 看字母在芯片里流动、计算
运行: python3 visual_chip.py
"""
import tkinter as tk
from tkinter import ttk, scrolledtext
from letter_cpu import LetterCPU, str_to_val, fmt

DEMO1 = """; HELLO + WORLD —— 26进制大数加法
LDA HELLO
ADD WORLD
STA RESULT
OUT
HLT"""

DEMO2 = """; 倒数循环 E(4) -> A(0)
COUNT = E
LDA COUNT
LOOP:
OUT
JZ DONE
SUB B
JMP LOOP
DONE:
HLT"""

DEMO3 = """; Z + B = BA —— 进位演示
LDA Z
ADD B
OUT
HLT"""


class ChipVisualizer:
    BG = "#0b1020"
    CHIP = "#131c33"
    ACCENT = "#38f28a"
    WARN = "#ffb020"
    LIT_COLORS = ["#38f28a", "#4dd8ff", "#c792ff", "#ff7ad9", "#ffd84d"]

    def __init__(self, root):
        self.root = root
        root.title("LetterCPU-26 · 26字母虚拟芯片")
        root.configure(bg=self.BG)
        root.geometry("1080x720")
        self.cpu = LetterCPU()
        self.running = False
        self.speed_ms = 600
        self.bus_dot = 0

        self._build_ui()
        self.load_demo(DEMO1)
        self.draw_chip()

    # ---------- 界面 ----------
    def _build_ui(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TButton", font=("PingFang SC", 11), padding=6)
        style.configure("TLabel", background=self.BG, foreground="#dfe7ff",
                        font=("PingFang SC", 11))

        top = tk.Frame(self.root, bg=self.BG)
        top.pack(fill="x", padx=12, pady=8)
        tk.Label(top, text="🌟 LetterCPU-26", bg=self.BG, fg=self.ACCENT,
                 font=("PingFang SC", 20, "bold")).pack(side="left")
        tk.Label(top, text="  不用 0/1，用 A~Z 共 26 个字母计算 · 1 Lit ≈ 4.7 bit",
                 bg=self.BG, fg="#8b95b5",
                 font=("PingFang SC", 11)).pack(side="left")

        main = tk.Frame(self.root, bg=self.BG)
        main.pack(fill="both", expand=True, padx=12, pady=4)

        # 左: 芯片画布
        left = tk.Frame(main, bg=self.BG)
        left.pack(side="left", fill="both", expand=True)
        self.canvas = tk.Canvas(left, bg="#070b16", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.reg_text = tk.StringVar()
        tk.Label(left, textvariable=self.reg_text, bg=self.BG, fg="#dfe7ff",
                 font=("Menlo", 12), justify="left").pack(anchor="w", pady=6)

        # 右: 代码 + 控制
        right = tk.Frame(main, bg=self.BG, width=380)
        right.pack(side="right", fill="y", padx=(12, 0))
        right.pack_propagate(False)

        tk.Label(right, text="📝 汇编程序 (Letter-ASM)",
                 bg=self.BG, fg="#dfe7ff",
                 font=("PingFang SC", 12, "bold")).pack(anchor="w")
        self.editor = scrolledtext.ScrolledText(right, height=16, font=("Menlo", 12),
                                                bg="#0e1528", fg="#e8f0ff",
                                                insertbackground="white")
        self.editor.pack(fill="x", pady=6)

        btns = tk.Frame(right, bg=self.BG)
        btns.pack(fill="x")
        for txt, cmd in [("🔨 汇编", self.do_assemble), ("▶ 运行", self.do_run),
                         ("⏹ 停止", self.do_stop), ("👣 单步", self.do_step),
                         ("🔄 重置", self.do_reset)]:
            ttk.Button(btns, text=txt, command=cmd).pack(side="left", padx=2)

        demos = tk.Frame(right, bg=self.BG)
        demos.pack(fill="x", pady=6)
        tk.Label(demos, text="示例:", bg=self.BG, fg="#8b95b5").pack(side="left")
        for name, code in [("加法", DEMO1), ("倒数", DEMO2), ("进位", DEMO3)]:
            ttk.Button(demos, text=name,
                       command=lambda c=code: self.load_demo(c)).pack(side="left", padx=2)

        speed = tk.Frame(right, bg=self.BG)
        speed.pack(fill="x")
        tk.Label(speed, text="速度:", bg=self.BG, fg="#8b95b5").pack(side="left")
        self.speed = ttk.Scale(speed, from_=100, to=1500, value=600,
                               command=lambda v: setattr(self, "speed_ms", int(float(v))))
        self.speed.pack(side="left", fill="x", expand=True, padx=6)

        tk.Label(right, text="📟 输出 / 日志", bg=self.BG, fg="#dfe7ff",
                 font=("PingFang SC", 12, "bold")).pack(anchor="w", pady=(6, 0))
        self.log = scrolledtext.ScrolledText(right, height=12, font=("Menlo", 11),
                                             bg="#0e1528", fg="#b8ffd9",
                                             state="disabled")
        self.log.pack(fill="both", expand=True, pady=6)

    # ---------- 功能 ----------
    def log_msg(self, s):
        self.log.configure(state="normal")
        self.log.insert("end", s + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def load_demo(self, code):
        self.editor.delete("1.0", "end")
        self.editor.insert("1.0", code)
        self.do_assemble()

    def do_assemble(self):
        src = self.editor.get("1.0", "end")
        try:
            self.cpu.assemble(src)
            # 预置演示数据
            for w in ("HELLO", "WORLD"):
                if w not in self.cpu.memory:
                    try:
                        self.cpu.memory[w] = str_to_val(w)
                    except ValueError:
                        pass
            self.log_msg(f"✅ 汇编成功: {len(self.cpu.instructions)} 条指令, "
                         f"内存 { {k: fmt(v) for k, v in self.cpu.memory.items()} }")
        except Exception as e:
            self.log_msg(f"❌ 汇编失败: {e}")
        self.refresh()

    def do_run(self):
        if not self.cpu.instructions:
            self.do_assemble()
        self.running = True
        self.auto_step()

    def do_stop(self):
        self.running = False
        self.log_msg("⏹ 已停止")

    def do_reset(self):
        self.running = False
        self.do_assemble()
        self.log_msg("🔄 已重置")

    def do_step(self):
        self.running = False
        self.exec_one()

    def exec_one(self):
        if self.cpu.halted:
            self.log_msg("🏁 程序停机 (HLT)")
            self.refresh()
            return
        try:
            info = self.cpu.step()
        except Exception as e:
            self.log_msg(f"❌ 运行错误: {e}")
            self.running = False
            return
        if info is None:
            self.cpu.halted = True
            self.log_msg("🏁 程序结束")
        else:
            op = info["op"]
            if op == "OUT":
                self.log_msg(f"📟 OUT → {fmt(info['output'])}  "
                             f"(字母形态 + 十进制对照)")
            else:
                self.log_msg(f"PC={info['pc']:02d} {info['raw']:<18} → ACC={fmt(info['acc'])}")
            if info.get("halted"):
                self.log_msg("🏁 程序停机 (HLT)")
                self.running = False
        self.bus_dot = 0
        self.refresh()

    def auto_step(self):
        if not self.running:
            return
        if self.cpu.halted:
            self.running = False
            self.refresh()
            return
        self.exec_one()
        if self.running:
            self.root.after(max(60, self.speed_ms), self.auto_step)

    # ---------- 芯片绘制 ----------
    def draw_chip(self, active=""):
        c = self.canvas
        c.delete("all")
        W = c.winfo_width() or 600
        H = c.winfo_height() or 560
        cx, cy = W // 2, H // 2 - 10
        size = min(W, H) - 90

        # 引脚
        for i in range(8):
            for sx, sy, ex, ey in [
                (cx - size//2 + i*(size//7), cy - size//2 - 22,
                 cx - size//2 + i*(size//7), cy - size//2),
                (cx - size//2 + i*(size//7), cy + size//2,
                 cx - size//2 + i*(size//7), cy + size//2 + 22),
                (cx - size//2 - 22, cy - size//2 + i*(size//7),
                 cx - size//2, cy - size//2 + i*(size//7)),
                (cx + size//2, cy - size//2 + i*(size//7),
                 cx + size//2 + 22, cy - size//2 + i*(size//7)),
            ]:
                c.create_line(sx, sy, ex, ey, fill="#3a4a6e", width=4)

        # 芯片主体
        c.create_rectangle(cx - size//2, cy - size//2, cx + size//2, cy + size//2,
                           fill=self.CHIP, outline=self.ACCENT, width=2)
        c.create_text(cx, cy - size//2 + 22, text="LetterCPU-26 · 26字母计算核心",
                      fill=self.ACCENT, font=("PingFang SC", 13, "bold"))

        # 内部模块
        mods = [
            ("ACC\n累加器", -1, -1, "ACC"),
            ("ALU\n26进制运算", 1, -1, "ALU"),
            ("PC\n程序计数", -1, 1, "PC"),
            ("MEM\n字母内存", 1, 1, "MEM"),
        ]
        self.mod_coords = {}
        for title, gx, gy, key in mods:
            x = cx + gx * size // 4
            y = cy + gy * size // 4
            w, h = size//3.1, size//4.2
            color = self.WARN if key in active else "#22314f"
            edge = self.WARN if key in active else "#4d628f"
            c.create_rectangle(x - w//2, y - h//2, x + w//2, y + h//2,
                               fill=color if key in active else "#16213c",
                               outline=edge, width=2)
            c.create_text(x, y, text=title, fill="white" if key not in active else "black",
                          font=("PingFang SC", 12, "bold"))
            self.mod_coords[key] = (x, y)

        # ACC 的字母形态跑马灯
        try:
            from letter_cpu import val_to_str
            acc_letters = val_to_str(self.cpu.acc) if self.cpu.acc >= 0 else "-" + val_to_str(-self.cpu.acc)
        except Exception:
            acc_letters = "A"
        ax, ay = self.mod_coords.get("ACC", (cx, cy))
        for i, ch in enumerate(acc_letters[-8:]):
            col = self.LIT_COLORS[i % len(self.LIT_COLORS)]
            c.create_text(ax - 60 + i * 17, ay + 42, text=ch, fill=col,
                          font=("Menlo", 15, "bold"))

        # 数据总线流动小点
        if self.cpu.instructions and not self.cpu.halted:
            t = self.bus_dot % 20
            x0, y0 = self.mod_coords.get("MEM", (cx, cy))
            x1, y1 = self.mod_coords.get("ACC", (cx, cy))
            fx = x0 + (x1 - x0) * t / 20
            fy = y0 + (y1 - y0) * t / 20
            c.create_oval(fx - 5, fy - 5, fx + 5, fy + 5, fill=self.ACCENT, outline="")
            self.bus_dot += 1
            self.root.after(120, lambda: self.draw_chip(active))
            return

    def refresh(self):
        # 高亮当前指令涉及的模块
        active = ""
        if self.cpu.instructions and not self.cpu.halted and self.cpu.pc < len(self.cpu.instructions):
            op = self.cpu.instructions[self.cpu.pc][0]
            active = {"LDA": "MEM", "STA": "MEM", "ADD": "ALU", "SUB": "ALU",
                      "MUL": "ALU", "DIV": "ALU", "JMP": "PC", "JZ": "PC",
                      "JNZ": "PC", "OUT": "ACC"}.get(op, "ACC")
        self.draw_chip(active)
        # 高亮当前指令行
        self.editor.tag_remove("cur", "1.0", "end")
        mem = ", ".join(f"{k}={fmt(v)}" for k, v in list(self.cpu.memory.items())[:6])
        self.reg_text.set(
            f"ACC 累加器 = {fmt(self.cpu.acc)}    PC = {self.cpu.pc}    "
            f"零标志 ZF = {int(self.cpu.zero)}    步数 = {self.cpu.steps}\n"
            f"内存: {mem if mem else '(空)'}")
        if self.cpu.instructions and self.cpu.pc < len(self.cpu.instructions):
            # 粗略定位第 pc 条指令所在行
            try:
                lines = self.editor.get("1.0", "end").splitlines()
                target = self.cpu.instructions[self.cpu.pc][2]
                for i, ln in enumerate(lines, 1):
                    if ln.split(";")[0].strip().upper() == target.split(";")[0].strip().upper():
                        self.editor.tag_add("cur", f"{i}.0", f"{i}.end")
                        self.editor.tag_config("cur", background="#3a2f00")
                        break
            except Exception:
                pass


def main():
    root = tk.Tk()
    ChipVisualizer(root)
    root.mainloop()


if __name__ == "__main__":
    main()
