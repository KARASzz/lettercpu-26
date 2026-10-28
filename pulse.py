#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pulse.py — LetterCPU-26 时序脉冲物理层 (Letter-Pulse Line Code v1)
================================================================
核心思想: 不用 26 个电压等级, 用「一根线 + 脉冲个数」表示 A~Z。

  字母值 N = A0 B1 C2 ... Z25
  一帧 = [START 高2拍] + [N 个数据脉冲(每脉冲=高1拍+低1拍)] + [STOP 低2拍] + [间隔1拍]

  A(=0) 帧 = 只有 START/STOP, 无数据脉冲 (静默也是数据!)
  C(=2) 帧 = START + 2个脉冲 + STOP
  Z(=25)帧 = START + 25个脉冲 + STOP

为什么这样定:
  脉冲数 == 数值, 硬件只需要会计数, 和 26 进制数学完美对应。
  波特率恒定: 示波器上能直接数出字母。
"""
BASE = 26
ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
VAL = {c: i for i, c in enumerate(ALPHABET)}


def letter_pulses(ch: str) -> int:
    """单个字母 -> 脉冲数 (A=0 ... Z=25)"""
    ch = ch.upper()
    if ch not in VAL:
        raise ValueError(f"非字母: {ch!r}")
    return VAL[ch]


def word_pulses(word: str) -> list:
    """字母串 -> 每个字母的脉冲数, 如 HELLO -> [7,4,11,11,14]"""
    return [letter_pulses(c) for c in word.upper() if c.isalpha()]


def encode_frame(n: int, unit: int = 1) -> list:
    """
    一个字母值 N -> 0/1 采样序列。
    START=高2拍, 数据脉冲=高1低1 xN, STOP=低2拍, 帧间隔=低1拍。
    """
    if not (0 <= n < 26):
        raise ValueError("N 必须 0..25")
    s = []
    s += [1] * (2 * unit)            # START
    for _ in range(n):
        s += [1] * unit + [0] * unit  # 数据脉冲
    s += [0] * (2 * unit)            # STOP
    s += [0] * unit                  # 帧间隔
    return s


def encode_word(word: str, unit: int = 1) -> dict:
    """整个字母串 -> 波形 + 统计"""
    word = "".join(c for c in word.upper() if c.isalpha())
    samples = []
    counts = []
    for c in word:
        n = letter_pulses(c)
        counts.append(n)
        samples += encode_frame(n, unit)
    return {
        "word": word,
        "counts": counts,
        "total_pulses": sum(counts),
        "samples": samples,
        "duration": len(samples),
    }


def decode_frames(counts: list) -> str:
    """脉冲数序列 -> 字母串, 如 [7,4,11,11,14] -> HELLO"""
    return "".join(ALPHABET[n] for n in counts)


def decode_samples(samples: list, unit: int = 1) -> str:
    """
    波形采样 -> 字母串 (教学版解码器)。
    原理: 找到 START(连续2高), 然后数后面高脉冲个数, 遇到连续>=2低即 STOP。
    简化实现: 按帧模板长度反推 —— 这里用脉冲计数法演示。
    """
    # 统计上升沿, 按 STOP(>=2连低) 切帧
    frames, cur_high_runs, i = [], 0, 0
    n = len(samples)
    # 先找每帧的 START: 连续 2unit 个 1
    while i < n:
        if samples[i] == 1 and i + 1 < n and samples[i + 1] == 1:
            # 进入一帧: 跳过 START
            i += 2 * unit
            pulses = 0
            # 数数据脉冲: 每个脉冲以 1 开头
            while i < n:
                # 看接下来是否有 >=2unit 个连续 0 -> STOP
                zeros = 0
                j = i
                while j < n and samples[j] == 0 and zeros < 2 * unit:
                    zeros += 1
                    j += 1
                if zeros >= 2 * unit:
                    i = j + unit  # 跳过 STOP+间隔
                    break
                if samples[i] == 1:
                    pulses += 1
                    i += 2 * unit  # 跳过 高1低1
                else:
                    i += 1
            frames.append(pulses)
        else:
            i += 1
    return decode_frames([f for f in frames if 0 <= f < 26])


def ascii_wave(samples: list, width: int = 80) -> str:
    """采样序列 -> ASCII 波形 (█=高, ·=低), 自动压缩到 width 列"""
    if not samples:
        return ""
    step = max(1, len(samples) // width)
    comp = []
    for i in range(0, len(samples), step):
        chunk = samples[i:i + step]
        comp.append(1 if sum(chunk) / len(chunk) >= 0.5 else 0)
    return "".join("█" if b else "·" for b in comp)


def table() -> str:
    lines = ["字母  值  脉冲数  示意(脉冲部分)"]
    for c in ALPHABET:
        n = VAL[c]
        bar = ("▲" * n) if n else "(静默帧)"
        lines.append(f"  {c}   {n:2d}   {n:2d}     {bar}")
    return "\n".join(lines)


def demo():
    print("=" * 64)
    print("  Letter-Pulse 物理层演示: 脉冲数 == 字母值")
    print("=" * 64)
    print("\n【A~Z 脉冲对照表】")
    print(table())
    for w in ("C", "HELLO", "CPU"):
        enc = encode_word(w)
        print(f"\n【{w}】脉冲数列 {enc['counts']}  共 {enc['total_pulses']} 个脉冲  "
              f"时长 {enc['duration']} 拍")
        print("波形: " + ascii_wave(enc["samples"]))
        back = decode_samples(enc["samples"])
        print(f"解码回: {back}  {'✅' if back == w else '❌'}")
    print("\n硬件一句话: 一根信号线 + 一个计数器 = 26 字母 CPU 总线。")


if __name__ == "__main__":
    demo()
