# 🌟 LetterCPU-26 — 26字母虚拟芯片 + LetterBASIC

> 不用 0/1，用 A~Z 共 26 个字母做计算的虚拟 CPU，以及跑在它上面的 QBASIC 方言。

## 核心思想

- 一个“字母位（Lit）”有 26 种状态，信息量 = log2(26) ≈ **4.7 bit**
- 数字 = 26 进制：`A=0, B=1, ..., Z=25`
  - `B + C = D`（1+2=3）
  - `Z + B = BA`（25+1=26，进位）
  - `HELLO` 就是一个 5-Lit 大数 = H×26⁴ + E×26³ + L×26² + L×26 + O
- 指令助记符本身就是英文单词，完美契合：`ADD SUB MUL PRINT FOR NEXT`

## 时序脉冲物理层（怎么造出真硬件）

不用 26 个电压等级，用**一根信号线 + 脉冲个数**表示 A~Z（`pulse.py`）：

- 一帧 = `START(高2拍) + N个脉冲(高1低1) + STOP(低2拍) + 间隔1拍`，N == 字母值
- `A(=0)` 是静默帧（只有 START/STOP，没有数据脉冲——静默也是数据！）
- `C(=2)` 是 2 个脉冲，`Z(=25)` 是 25 个脉冲
- 示波器上直接数出字母；硬件只需要一个计数器

`PLAY "CDE"` 就是把字母按脉冲数变成音高播出来，示波器可验证。

## 怎么玩（4 种入口）

| 入口 | 文件 | 说明 |
|------|------|------|
| 🌐 芯片可视化（网页） | `index.html` | 双击打开：芯片版图 + 汇编 + 单步 |
| 🌐 BASIC 可视化（网页） | `basic.html` | 双击打开：BASIC IDE + 芯片状态 + 脉冲示波器 + 发声 |
| 💻 命令行 BASIC | `letter_basic.py` | `python3 letter_basic.py demo_fib.lb` / 进 REPL |
| 💻 命令行芯片 | `letter_cpu.py` / `pulse.py` | 芯片内核演示 / 脉冲物理层演示 |
| 🖥️ 桌面可视化 | `visual_chip.py` / `visual_basic.py` | Tkinter 版（需桌面 Python） |

```bash
cd "/Volumes/666/+Python mac/创造新型计算芯片"
python3 letter_cpu.py            # 芯片演示: HELLO+WORLD、Z+B=BA、E->A倒数
python3 pulse.py                 # 脉冲层演示: A~Z对照表 + HELLO/CPU波形编解码
python3 letter_basic.py demo_fib.lb    # 斐波那契
python3 letter_basic.py demo_mult.lb   # 九九乘法表
printf 'LEE\n3\n' | python3 letter_basic.py demo_stars.lb   # 打招呼+星星
python3 letter_basic.py demo_guess.lb  # 猜字母游戏（需交互输入）
python3 letter_basic.py            # 进 REPL，HELP 看帮助，DEMO 跑演示
```

## LetterBASIC（QBASIC 方言）速查

```basic
行号(可选)  REM / ' 注释
LET X = 5 / X = HELLO        数字=十进制或26进制字母串
X$ = "文本"                  字符串，& 拼接
PRINT 项[;项...] / ?         数字自动显示 字母(十进制)，如 HELLO(123)
INPUT [提示;] X              数字/字母串自动识别
IF ... THEN ... [ELSE ...] / IF...THEN GOTO 行号 / THEN 行号
GOTO / GOSUB / RETURN
FOR X = a TO b [STEP s] ... NEXT [X]   可嵌套，STEP可为负
WHILE ... WEND / DO ... LOOP WHILE|UNTIL
DIM A(n) / A(i) 读写 / POKE A,i,v / PEEK(A,i)
SOUND 频率,时长 / PLAY "CDE" / SLEEP 秒 / CLS
表达式: + - * / MOD ( ) < > = <= >= <> AND OR NOT
函数: ABS() INT() RND(n)/RND LEN() ASC() VAL() CHR$()
特殊: 纯字母串直接当数字 (Z+B=BA)，PRINT 自动转字母显示
```

示例（斐波那契 `demo_fib.lb`）：

```basic
10 DIM F(10)
30 F(0) = 0
40 F(1) = 1
50 FOR I = 2 TO 9
60   F(I) = F(I-1) + F(I-2)
70 NEXT I
80 FOR I = 0 TO 9
90   PRINT "F("; I; ")="; F(I)
100 NEXT I
110 END
```

## Letter-ISA v2（芯片指令集，BASIC 编译目标）

`LDA STA ADD SUB MUL DIV MOD CMP JMP JZ JNZ JG JL JGE JLE CALL RET`
`PUSH POP POFF LDS STS CATS PRS PRTS OUT INP LDX STX CLR BEAT NOP HLT`

BASIC 的控制流（IF/FOR/WHILE/GOSUB）全部编译成 ISA 跳转（`BEAT`=语句边界拍），
单步执行时可看见每条 BASIC 对应的 ISA 伪指令流。

## 文件一览

- `letter_cpu.py` — v1 芯片内核（26进制 + 汇编器 + 单步）
- `letter_cpu_v2.py` — v2 芯片内核（寄存器/双内存/栈/字符串/比较跳转，供 BASIC 用）
- `pulse.py` — 时序脉冲物理层（编码/解码/ASCII 波形）
- `letter_basic.py` — LetterBASIC 解释器（编译成 ISA v2 伪指令流执行）
- `visual_chip.py` / `visual_basic.py` — Tkinter 桌面可视化
- `index.html` / `basic.html` — 网页可视化（双击即玩）
- `demo_fib.lb` / `demo_mult.lb` / `demo_stars.lb` / `demo_guess.lb` — BASIC 示例程序
