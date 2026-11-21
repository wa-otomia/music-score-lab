[日本語](drum-maps.md) | [简体中文](drum-maps.zh-CN.md) | [English](drum-maps.en.md)

# 乐器目录与鼓映射

MIDI 里的鼓只是音符号（例如 36、38、42）。把音符号印成谱面上的符头要两层配置：

1. **乐器目录** `configs/instruments.yaml`：每种乐器印在哪个位置、用什么符头、有没有开/闭记号、日文名和凡例缩写。
2. **鼓映射** `configs/drum-maps/*.yaml`：MIDI 音符号 → 乐器 ID。曲目元数据的 `note_map` 可以在映射之上再逐个改写。

映射里找不到的音符直接报错，不会猜：错误信息列出这些音符号，指出第一次出现在源 MIDI 第几拍，并用其中一个音符号给出 `note_map` 的写法示例。

## 乐器目录字段

```yaml
hihat-open: {name: Open Hi-Hat, name_ja: ハイハット（オープン）, abbr: HHo, part: hand, staff: n, head: x, mark: open}
```

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| （键） | 是 | 乐器 ID，映射和 `note_map` 用它引用乐器 |
| `name` | 是 | 英文名，写进 MusicXML 的 `instrument-name`（后面附 MIDI 音符号） |
| `name_ja` | 否 | 日文名，印在凡例里（可复制文字）。全角括号 `（…）` 及其后的部分在凡例中换到第二行。默认同 `name` |
| `abbr` | 否 | 凡例缩写，1–4 个字符，只能用 ASCII 字母、数字和 `. + -`。默认由 `name` 中的 ASCII 单词生成：有多个单词时取各词首字母大写（最多 4 个，如 `Hi Hat` → `HH`），只有一个单词时取它的前 3 个字符，没有 ASCII 单词时为 `X` |
| `part` | 是 | `hand`：上声部，符干朝上；`foot`：下声部，符干朝下 |
| `staff` | 是 | 谱表位置，一个字母 `a`–`s`，见下表 |
| `head` | 是 | 符头：`normal` 实心椭圆、`x` 叉、`circle-x` 圈叉、`diamond` 空心菱形、`triangle` 三角、`plus` 十字、`rhombus` 实心菱形 |
| `mark` | 否 | 记号：`open` 小圆圈 ○、`half-open` ⊖、`closed` ＋；不写则无。印在符头上方（手部高 3 个位置，脚部高 2 个位置） |

### 谱表位置字母

字母沿用 MusiXTeX 的音高字母，按高音谱号的位置理解；MusicXML 中写成对应的 `display-step` / `display-octave`。

| 字母 | 位置 | MusicXML | | 字母 | 位置 | MusicXML |
| --- | --- | --- | --- | --- | --- | --- |
| `a` | 下加二线 | A3 | | `j` | 第三间 | C5 |
| `b` | 下加二间 | B3 | | `k` | 第四线 | D5 |
| `c` | 下加一线 | C4 | | `l` | 第四间 | E5 |
| `d` | 下加一间 | D4 | | `m` | 第五线 | F5 |
| `e` | 第一线 | E4 | | `n` | 上加一间 | G5 |
| `f` | 第一间 | F4 | | `o` | 上加一线 | A5 |
| `g` | 第二线 | G4 | | `p` | 上加二间 | B5 |
| `h` | 第二间 | A4 | | `q` | 上加二线 | C6 |
| `i` | 第三线 | B4 | | `r` | 上加三间 | D6 |
| | | | | `s` | 上加三线 | E6 |

（“上加一间”指第五线与上加一线之间，“下加一间”指第一线与下加一线之间。）

内置目录中各乐器的位置和符头见 [notation-conventions.zh-CN.md](notation-conventions.zh-CN.md)。

## 内置映射

### `gm`（默认）

General MIDI Level 1 打击乐键位 35–81，加上 GS/GM2 扩展的 27–34 与 82–87，共 61 个音符。
每个音符对应的乐器见 `configs/drum-maps/gm.yaml`，乐器的位置与符头见 notation-conventions.zh-CN.md 中的总表。需要留意的几处：

| 音符 | GM 名称 | 映射到 | 说明 |
| --- | --- | --- | --- |
| 35 | Acoustic Bass Drum | `kick-2`（第一线） | 只用 35 当底鼓时，用 `note_map: {35: kick}` 印在常规的第一间 |
| 36 | Bass Drum 1 | `kick`（第一间） | |
| 38、40 | Acoustic / Electric Snare | 都是 `snare` | 谱面上无法区分；需要区分时给其中一个改符头 |
| 44 | Pedal Hi-Hat | `hihat-pedal`（下加一间，脚） | |
| 42、46 | Closed / Open Hi-Hat | 同一位置（上加一间），46 加 ○ | |

### `fpc-default`

FL Studio 的鼓采样器 FPC 的默认布局。据 [FL Studio 在线手册的 FPC 页面](https://www.image-line.com/fl-studio-learning/fl-studio-online-manual/html/plugins/FPC.htm)（以下为意译）：

- 布局菜单中的 Default 与 Akai MPC 系列的布局一致（除非已被自己保存的布局覆盖）；
- 音符旁括号里的名称是 General MIDI 标准名称；空白预设的各个 pad 已经分配到相应的 General MIDI 音符；
- 每个 pad 的触发音符可以在 Play Key/Octave 中改，布局可以另存。

也就是说，用默认布局时 FPC 发出的音符号就是 GM 打击乐编号，所以 `fpc-default` 直接 `extends: gm`，不改任何音符。
它与 `gm` 的区别只在于说明文字，写在元数据里可以记录“这是 FPC 导出”。

FL Studio 直接导出 FPC 时，音符在 MIDI 第 1 通道、轨道名形如 `FPC 1`；转换器的自动选轨会选中它（见 [metadata.zh-CN.md](metadata.zh-CN.md)）。
**如果改过 pad 的音色或音符**，某个音符号上实际放的已经不是 GM 名称对应的乐器，必须用 `note_map` 或自定义映射改写，
否则谱面会印错乐器。

## 改写音符

### 在元数据中用 `note_map`

`note_map` 的键是 MIDI 音符号（0–127），值有三种写法：

```yaml
note_map:
  # 1. 换成目录里的另一种乐器
  40: hand-clap

  # 2. 以目录中的乐器为基础，改其中几个字段
  38: {as: snare, head: circle-x, name_ja: スネア（リムショット）, abbr: RS}

  # 3. 完整定义一个新乐器（name、part、staff、head 必填；可加 id）
  77: {id: block, name: Block, name_ja: ブロック, abbr: BL, part: hand, staff: r, head: triangle}
```

`note_map` 只覆盖写到的音符，其余仍按 `drum_map`。

### 写自己的映射文件

一套 FPC 套件或电子鼓音源经常要用时，复制成一个映射文件更方便：

```yaml
# 例如 scores/<slug>/my-kit.yaml 或 configs/drum-maps/my-kit.yaml
name: 我的 FPC 套件
description: Bank A 的 40 号 pad 换成了拍手，41 号是第三个落地嗵鼓
extends: fpc-default        # 内置映射名，或相对于本文件所在目录的路径
notes:
  40: hand-clap
  41: {as: tom-floor-low, abbr: FT3, name_ja: フロアタム3}
```

- 顶层只允许 `name`、`description`、`extends`、`notes`。
- `extends` 可以多层继承，子映射覆盖父映射中的同号音符；出现循环继承会报错。
- `notes` 的值与 `note_map` 的三种写法相同。
- 元数据中写 `drum_map: my-kit.yaml`（相对于元数据文件所在目录），或把文件放进 `configs/drum-maps/` 后直接写 `drum_map: my-kit`。

## 位置与符头相同的乐器

谱面只靠位置、符头和记号区分乐器。两个 MIDI 音符的**位置、符头、记号和声部**都相同时（例如 GM 38 和 40 都是 `snare`），
它们在谱面上无法区分，凡例中也合并为一项，只印音符号较小者的缩写和日文名。两者同时击打时，两个符头会重叠印在同一处，转换时会给出提示。
同一位置、不同符头的两个乐器同时击打（例如 ride 与 ride bell）也会提示符头重叠。提示指出第几小节第几拍，并给出改位置的写法，
例如 `40: {as: snare, staff: l}`。
MusicXML 中它们仍是不同的乐器（各自保留原 MIDI 音符号，可以正确回放）。

需要在谱面上区分时，用 `note_map` 给其中一个换符头或位置。内置乐器目录中没有两种乐器的位置、符头、记号和声部完全相同。
