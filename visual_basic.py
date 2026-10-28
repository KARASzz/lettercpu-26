#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
visual_basic.py — LetterBASIC 可视化 IDE (Tkinter)
==================================================
左边: 芯片状态 + 变量监视 + 脉冲示波器
右边: BASIC 编辑器 + 运行控制 + 输出
运行: python3 visual_basic.py
"""
import tkinter as tk
from tkinter import scrolledtext
import math

from letter_basic import LetterBasic, HELP_TEXT
from letter_cpu_v2 import val_to_str as V2S
from pulse import letter_pulses, encode_word, ascii_wave

LIT_COLORS = ["#38f28a", "#4dd8ff", "#c792ff", "#ff7ad9", "#ffd84d"]
BG = "#0b1020"


DEMOS = {
    "❤ 打招呼+星星": """10 REM 星星三角形 + 打招呼 + 脉冲音阶
20 INPUT "你叫什么名字"; N$
30 PRINT "你好, "; N$; "!"
40 INPUT "画几层星星"; N
50 FOR I = 1 TO N
60   FOR J = 1 TO I
70     PRINT "*";
80   NEXT J
90   PRINT
100 NEXT I
110 PLAY "CDEFGAB"
120 END
""",
    "🔢 斐波那契": """10 REM 斐波那契前10项
20 DIM F(10)
30 F(0) = 0
40 F(1) = 1
50 FOR I = 2 TO 9
60   F(I) = F(I-1) + F(I-2)
70 NEXT I
80 FOR I = 0 TO 9
90   PRINT "F("; I; ")="; F(I)
100 NEXT I
110 END
""",
    "✖ 乘法表": """10 REM 九九乘法表
20 FOR A = 1 TO 9
30   FOR B = 1 TO A
40     PRINT A; "x"; B; "="; A*B; " ";
50   NEXT B
60   PRINT
70 NEXT A
80 END
""",
    "🎲 猜字母": """10 REM 猜字母数 A~Z
20 PRINT "我想了一个 A~Z 的字母, 猜猜是多少?"
30 TARGET = INT(RND(26)) + 1
40 TRIES = 0
50 INPUT "猜一个字母"; G$
60 TRIES = TRIES + 1
70 G = VAL(G$)
80 IF G = TARGET THEN PRINT "猜中了! 用了 "; TRIES; " 次" : PLAY "CDEFGAB" : END
90 IF G < TARGET THEN PRINT "小了, 往后猜 (往 Z 方向)"
100 IF G > TARGET THEN PRINT "大了, 往前猜 (往 A 方向)"
110 GOTO 50
""",
}


class BasicIDE:
    def __init__(self, root):
        self.root = root
        root.title("LetterBASIC · 26字母芯片上的 QBASIC")
        root.configure(bg=BG)
        root.geometry("1180x760")
        self.lb = None
        self.running = False
        self.speed_ms = 250

        # 脉冲音: 用正弦 beep (macOS afplay 回退到静默)
        try:
            import subprocess
            self._has_afplay = True
        except Exception:
            self._has_afplay = False

        self._build()
        self.load_demo("❤ 打招呼+星星")
        self.draw_all()

    # ---------- 界面 ----------
    def _build(self):
        top = tk.Frame(self.root, bg=BG)
        top.pack(fill="x", padx=12, pady=8)
        tk.Label(top, text="🌟 LetterBASIC", bg=BG, fg="#38f28a",
                 font=("PingFang SC", 20, "bold")).pack(side="left")
        tk.Label(top, text="  跑在 LetterCPU-26 上的 QBASIC 方言 · 数字永远显示 字母(十进制)",
                 bg=BG, fg="#8b95b5", font=("PingFang SC", 11)).pack(side="left")

        main = tk.Frame(self.root, bg=BG)
        main.pack(fill="both", expand=True, padx=12, pady=4)

        left = tk.Frame(main, bg=BG)
        left.pack(side="left", fill="both", expand=True)
        self.canvas = tk.Canvas(left, bg="#070b16", highlightthickness=0, height=300)
        self.canvas.pack(fill="x")
        self.wave = tk.Canvas(left, bg="#070b16", highlightthickness=0, height=120)
        self.wave.pack(fill="x", pady=6)
        self.vars_text = tk.StringVar()
        tk.Label(left, textvariable=self.vars_text, bg=BG, fg="#dfe7ff",
                 font=("Menlo", 11), justify="left", anchor="nw").pack(fill="x", pady=4)

        right = tk.Frame(main, bg=BG, width=460)
        right.pack(side="right", fill="y", padx=(12, 0))
        right.pack_propagate(False)
        tk.Label(right, text="📝 LetterBASIC 程序", bg=BG, fg="#fff",
                 font=("PingFang SC", 12, "bold")).pack(anchor="w")
        self.editor = scrolledtext.ScrolledText(right, height=20, font=("Menlo", 12),
                                                bg="#0e1528", fg="#e8f0ff",
                                                insertbackground="white")
        self.editor.pack(fill="x", pady=6)
        btns = tk.Frame(right, bg=BG)
        btns.pack(fill="x")
        for txt, cmd in [("🔨 装载", self.do_load), ("▶ 运行", self.do_run),
                         ("⏹ 停止", self.do_stop), ("👣 单步", self.do_step),
                         ("🔄 重置", self.do_reset)]:
            tk.Button(btns, text=txt, command=cmd).pack(side="left", padx=2)
        demos = tk.Frame(right, bg=BG)
        demos.pack(fill="x", pady=6)
        tk.Label(demos, text="示例:", bg=BG, fg="#8b95b5").pack(side="left")
        for name in DEMOS:
            tk.Button(demos, text=name.split()[0],
                      command=lambda n=name: self.load_demo(n)).pack(side="left", padx=2)
        spd = tk.Frame(right, bg=BG)
        spd.pack(fill="x")
        tk.Label(spd, text="速度:", bg=BG, fg="#8b95b5").pack(side="left")
        tk.Scale(spd, from_=30, to=1200, orient="horizontal", bg=BG, fg="#fff",
                 highlightthickness=0, length=220,
                 command=lambda v: setattr(self, "speed_ms", int(float(v)))
                 ).pack(side="left")
        tk.Label(right, text="📟 输出 (INPUT 请在弹窗/终端输入)",
                 bg=BG, fg="#fff", font=("PingFang SC", 12, "bold")).pack(anchor="w", pady=(6, 0))
        self.log = scrolledtext.ScrolledText(right, height=12, font=("Menlo", 11),
                                             bg="#0e1528", fg="#b8ffd9",
                                             state="disabled")
        self.log.pack(fill="both", expand=True, pady=6)

    # ---------- 逻辑 ----------
    def log_msg(self, s):
        self.log.configure(state="normal")
        self.log.insert("end", s + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def beep(self, freq, secs):
        # macOS: 用 afplay 播正弦? 为简单起见用系统 beep 模拟, 只闪波形
        self.show_wave_freq(freq, secs)
        try:
            self.root.bell()
        except Exception:
            pass

    def show_wave_freq(self, freq, secs):
        pass  # 波形绘制在 draw_all 里用当前 PLAY 字母

    def load_demo(self, name):
        self.editor.delete("1.0", "end")
        self.editor.insert("1.0", DEMOS[name])
        self.do_load()

    def ensure_loaded(self):
        if self.lb is None:
            self.do_load()

    def do_load(self):
        src = self.editor.get("1.0", "end")
        outs = []

        def on_print(s):
            outs.append(s)
            self.log_msg(s.rstrip("\n") if s.strip() else "")

        self.lb = LetterBasic(on_print=on_print, on_input=self.ask_input,
                              trace=self.on_trace, beep=self.beep)
        try:
            stmts = self.lb.load(src)
            self.log_msg(f"✅ 装载成功: {len(stmts)} 行 BASIC, {len(self.lb.prog)} 条 ISA 伪指令")
        except Exception as e:
            self.log_msg(f"❌ 装载失败: {e}")
        self.running = False
        self.draw_all()

    def ask_input(self, prompt="? "):
        # 用一个小弹窗问输入 (打包成同步)
        win = tk.Toplevel(self.root)
        win.title("INPUT")
        win.geometry("320x140")
        tk.Label(win, text=prompt, font=("PingFang SC", 12)).pack(pady=8)
        ent = tk.Entry(win, font=("Menlo", 14))
        ent.pack(padx=16, fill="x")
        ent.focus()
        result = {}

        def ok(_=None):
            result["v"] = ent.get()
            win.destroy()
        tk.Button(win, text="确定", command=ok).pack(pady=8)
        win.bind("<Return>", ok)
        win.grab_set()
        self.root.wait_window(win)
        return result.get("v", "")

    def on_trace(self, op, arg, snap):
        pass

    def do_run(self):
        self.ensure_loaded()
        if self.lb.halted:
            self.do_load()
        self.running = True
        self.auto()

    def do_stop(self):
        self.running = False
        self.log_msg("⏹ 已停止")

    def do_reset(self):
        self.running = False
        self.do_load()
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")
        self.log_msg("🔄 已重置")

    def do_step(self):
        self.ensure_loaded()
        self.running = False
        self.exec_one()

    def exec_one(self):
        if self.lb.halted:
            self.log_msg("🏁 程序结束")
            self.running = False
            self.draw_all()
            return
        try:
            info = self.lb.step()
        except Exception as e:
            self.log_msg(f"❌ 运行错误 PC={self.lb.pc}: {e}")
            self.running = False
            self.draw_all()
            return
        if info is None:
            self.log_msg("🏁 程序结束")
            self.running = False
        self.draw_all()

    def auto(self):
        if not self.running:
            return
        if self.lb.halted:
            self.log_msg("🏁 程序结束")
            self.running = False
            self.draw_all()
            return
        self.exec_one()
        if self.running:
            self.root.after(max(30, self.speed_ms), self.auto)

    # ---------- 绘制 ----------
    def draw_all(self):
        self.draw_chip()
        self.draw_wave()
        self.draw_vars()

    def draw_chip(self):
        c = self.canvas
        c.delete("all")
        W = c.winfo_width() or 620
        H = 300
        cx, cy = W // 2, H // 2
        size_w, size_h = min(W - 60, 560), 220
        # 芯片主体
        c.create_rectangle(cx - size_w//2, cy - size_h//2, cx + size_w//2, cy + size_h//2,
                           fill="#131c33", outline="#38f28a", width=2)
        c.create_text(cx, cy - size_h//2 + 20, text="LetterCPU-26 · BASIC 运行时",
                      fill="#38f28a", font=("PingFang SC", 13, "bold"))
        # 模块
        mods = [("ACC", "数字核"), ("STR", "字符串核"), ("PC", "行号/跳转"),
                ("MEM", "变量/数组"), ("STK", "GOSUB栈"), ("PLS", "脉冲输出")]
        for i, (k, sub) in enumerate(mods):
            x = cx - size_w//2 + 40 + i * ((size_w - 80) // 5)
            y = cy + 10
            c.create_rectangle(x - 42, y - 34, x + 42, y + 34, fill="#16213c",
                               outline="#4d628f", width=2)
            c.create_text(x, y - 8, text=k, fill="#fff", font=("Menlo", 13, "bold"))
            c.create_text(x, y + 12, text=sub, fill="#8b95b5", font=("PingFang SC", 10))
        # PC / 步数
        pc = self.lb.pc if self.lb else 0
        total = len(self.lb.prog) if self.lb else 0
        c.create_text(cx, cy + size_h//2 - 22,
                      text=f"ISA-PC {pc}/{total}   FOR层 {len(self.lb.for_stack) if self.lb else 0}   "
                           f"GOSUB层 {len(self.lb.gosub_stack) if self.lb else 0}",
                      fill="#9fb3dd", font=("Menlo", 11))
        # 进度条
        if total:
            p = min(1.0, pc / total)
            c.create_rectangle(cx - size_w//2 + 20, cy + size_h//2 - 14,
                               cx - size_w//2 + 20 + (size_w - 40) * p, cy + size_h//2 - 8,
                               fill="#38f28a", outline="")

    def draw_wave(self):
        c = self.wave
        c.delete("all")
        W = c.winfo_width() or 620
        H = 120
        c.create_text(8, 12, text="时序脉冲示波器 (脉冲数 == 字母值 A=0..Z=25)",
                      fill="#8b95b5", font=("PingFang SC", 10), anchor="w")
        # 取最近一次 PLAY / SOUND 的字母, 否则显示 HELLO
        word = getattr(self, "_last_word", "HELLO")
        try:
            enc = encode_word(word)
        except Exception:
            enc = encode_word("HELLO")
        samples = enc["samples"]
        # 压缩到画布宽度
        mid, amp = H // 2 + 14, 26
        step = max(1, len(samples) / (W - 20))
        prev = None
        for x in range(W - 20):
            idx = int(x * step)
            v = samples[idx] if idx < len(samples) else 0
            y = mid - amp if v else mid + amp
            xx = x + 10
            if prev is not None:
                c.create_line(prev[0], prev[1], xx, y, fill="#38f28a", width=2)
                if y != prev[1]:
                    c.create_line(xx, prev[1], xx, y, fill="#38f28a", width=2)
            prev = (xx, y)
        c.create_text(W - 8, 12, text=f"{word} 脉冲{enc['counts']} 共{enc['total_pulses']}",
                      fill="#38f28a", font=("Menlo", 10), anchor="e")

    def draw_vars(self):
        if not self.lb:
            self.vars_text.set("变量: (未装载)")
            return
        nums = "  ".join(f"{k}={V2S(v)}({v})" for k, v in list(self.lb.num.items())[:10])
        strs = "  ".join(f'{k}="{v}"' for k, v in list(self.lb.str.items())[:6])
        arrs = "  ".join(f"{k}({len(v)})" for k, v in list(self.lb.arr.items())[:6])
        self.vars_text.set(f"数字变量: {nums or '(无)'}\n字符串: {strs or '(无)'}\n数组: {arrs or '(无)'}")


def main():
    root = tk.Tk()
    BasicIDE(root)
    root.mainloop()


if __name__ == "__main__":
    main()
