[日本語](metadata.md) | [简体中文](metadata.zh-CN.md) | [English](metadata.en.md)

# 曲目元数据（metadata.yaml）

每首曲目一个 `scores/<slug>/metadata.yaml`，由 `scripts/build_score.py --metadata` 读入。
新曲目请复制 [templates/metadata.yaml](../templates/metadata.yaml)。

- 顶层只允许本文列出的字段（含文末“旧字段”），出现其他字段会直接报错（防止拼错字段名后被悄悄忽略）。
- 所有字段都可省略；省略时使用“默认”一列的值。
- `midi`、`quantize`、`notation`、`dynamics`、`credits` 内部也只允许下文列出的子字段，拼错同样报错。

## 署名与文字

这些字段只影响标题区、页眉和 MusicXML 的署名，不影响记谱。值按原样输出（可以写日文）：PDF 中汉字、假名与拉丁字母之间
不自动加空格，写进去的空格原样印出（例外：紧跟在全角标点之后、或夹在假名/汉字与全角括号之间的半角空格按日文排版规则不印）；只是去掉首尾空白（含全角空格），并把换行、制表符等连续的 ASCII 空白合成一个半角空格。
复制文字时：汉字、假名与拉丁字母之间写的半角空格，pdftotext 和 pdf.js 都会保留；全角空格（U+3000）印出来没问题，
但 pdftotext 和 pdf.js 复制出来是半角空格，PyMuPDF 则保留 U+3000（PyMuPDF 反而会丢掉汉字、假名旁边的半角空格）。
MusicXML 中写入元数据的原值，不做上述空白处理。

| 字段 | 类型 | 默认 | 用途 | 示例 |
| --- | --- | --- | --- | --- |
| `title` | 字符串 | `Untitled` | 曲名：PDF 标题、续页页眉、PDF 文档标题，MusicXML `work-title` 与 `movement-title` | `命に嫌われている。` |
| `subtitle` | 字符串 | 无 | 曲名下的一行；MusicXML `work-number`（MuseScore 3 把它显示为副标题）和副标题 credit | `Self-cover ver.` |
| `artist` | 字符串 | 无 | 艺人：标题区、续页页眉；没有 `subtitle` 时作 MusicXML 副标题 credit | `カンザキイオリ` |
| `album` | 字符串 | 无 | 专辑：印成 `『…』` 跟在艺人后面 | `不器用な男` |
| `lyricist` | 字符串 | 无 | 作词（标签 `作詞`） | `カンザキイオリ` |
| `composer` | 字符串 | 无 | 作曲（标签 `作曲`） | `カンザキイオリ` |
| `vocal` | 字符串 | 无 | 演唱（标签 `歌`） | `カンザキイオリ（セルフカバー）` |
| `transcriber` | 字符串 | 无 | 鼓谱采谱（标签 `ドラム採譜`）；MusicXML `arranger` 类型的 credit | `音宮` |
| `arranger` | 字符串 | 无 | 鼓编曲（标签 `ドラム編曲`） | `音宮` |
| `note` | 字符串 | 无 | 备注（标签 `備考`），例如说明含采谱者的再创作 | `本譜には採譜者による再構成・創作を含みます。` |
| `copyright` | 字符串 | 无 | 印在第一页底部；MusicXML `rights` | `© 2026 …` |
| `credits` | 映射 | 无 | 改写职务标签，见下文 | `{arranger: アレンジ}` |
| `legend` | 布尔 | `false` | 是否在第一页印凡例。必须是 YAML 布尔值，写成带引号的字符串（如 `"false"`）会报错 | `false` |
| `slug` | 字符串 | 无 | 仅作记录（与目录名相同），程序不使用 | `inochi-ni-kirawareteiru` |

MusicXML 中：`title` 写成 `work-title` 和 `movement-title`；`subtitle` 写成 `<work>` 里的 `work-number`；
`composer`、`lyricist`、`arranger` 写成 `creator`；`artist`、`album`、`vocal`、`transcriber`、`note` 写成同名的
`miscellaneous-field`。第一页的 `credit`：曲名居中；副标题（`subtitle`，没有时用 `artist`）居中；`composer` 靠右；
`lyricist` 靠左；`transcriber`（credit 类型 `arranger`）靠左。读取 `credit` 的软件会显示这些署名。
MuseScore 3 不读 `credit`：打开后显示曲名（取自 `movement-title`）、副标题（取自 `work-number`，所以只有写了 `subtitle`
时才有）、作曲和作词，不显示 `artist` 和 `transcriber`。
PDF 文档属性：标题为 `<title> ドラム譜`，作者为 `transcriber` 与 `arranger`
（相同时只写一次），主题为 `artist / album`。

### 标题区怎样拼出来

第一页标题区从上到下：

1. `title`（大号粗体）
2. `subtitle`
3. `artist　『album』`
4. 歌曲署名：按 `lyricist`、`composer`、`vocal` 的顺序
5. 鼓谱署名：按 `transcriber`、`arranger` 的顺序
6. `備考：note`
7. `BPM <速度>`
8. 凡例（只在 `legend: true` 或命令行 `--legend` 时印出）

第 4、5 行中，**值完全相同**（去掉首尾空白后逐字比较）的职务合并成一个标签，用 `・` 连接，不同的人之间用全角空格分隔。
比较时不合并中间的连续空白：`A  B`（两个空格）与 `A B` 印出来一样，但不会合并。

| 元数据 | 印出的行 |
| --- | --- |
| `lyricist: A`、`composer: A`、`vocal: B` | `作詞・作曲：A　歌：B` |
| `lyricist: A`、`composer: B` | `作詞：A　作曲：B` |
| `transcriber: C`、`arranger: C` | `ドラム採譜・編曲：C` |
| `transcriber: C`、`arranger: D` | `ドラム採譜：C　ドラム編曲：D` |

合并时，如果第一个标签以 `ドラム` 开头，后面标签开头重复的 `ドラム` 会省略，所以是 `ドラム採譜・編曲` 而不是
`ドラム採譜・ドラム編曲`。人名写法稍有不同（例如一个带「（セルフカバー）」一个不带）就不会合并。

### credits：改写标签

`credits` 的键是职务名，值是要印的标签。可改的职务：`lyricist`、`composer`、`vocal`、`transcriber`、`arranger`、`note`。
`artist`、`album` 也允许写，但这两项在标题区不印标签，所以不起作用；其他键报错。

```yaml
credits:
  vocal: ボーカル        # 「歌：…」改成「ボーカル：…」
  arranger: アレンジ     # 「ドラム編曲：…」改成「アレンジ：…」
```

## 鼓映射与选轨

| 字段 | 类型 | 默认 | 说明 |
| --- | --- | --- | --- |
| `drum_map` | 字符串 | `gm` | 内置映射名（`gm`、`fpc-default`），或映射 YAML 的路径。相对路径先相对于元数据文件所在目录查找，找不到再相对于当前目录。命令行 `--drum-map` 优先 |
| `note_map` | 映射 | 无 | 在 `drum_map` 之上逐个改写音符：`MIDI 音符号: 乐器`。写法见 [drum-maps.zh-CN.md](drum-maps.zh-CN.md) |
| `midi.tracks` | 列表或单个值 | 自动 | 只用这些轨道。字符串＝轨道名包含该文字（不区分大小写）；整数＝轨道序号（从 0 开始，第 0 轨通常是速度轨）。命令行 `--track`（只能按名称）优先 |
| `midi.channels` | 列表或单个整数 | 自动 | 只用这些 MIDI 通道，按 1–16 编号（GM 鼓是 10，FPC 直接导出是 1）。命令行 `--channel` 优先 |

`tracks` 和 `channels` 同时给出时，两个条件都要满足。都不给时自动选择：文件里只有一个含音符的轨道/通道就用它；
否则用所有第 10 通道；否则用轨道名含 `fpc`、`drum`、`perc`、`kit`、`ドラム`、`鼓` 的轨道；仍无法判断就报错并列出各轨道。

```yaml
drum_map: fpc-default
note_map:
  40: hand-clap          # 这个 FPC 套件把拍手放在 40 号 pad 上
midi:
  tracks: [FPC]          # 或 [1]（按序号），或 channels: [10]
```

## 量化

| 字段 | 类型 | 默认 | 说明 |
| --- | --- | --- | --- |
| `quantize.subdivision` | 整数 | `4` | 直拍网格：`4`＝16 分音符，`2`＝8 分音符。只允许这两个值 |
| `quantize.tuplets` | 字符串 | `auto` | `auto`：逐拍、逐声部判断是否记成三连音；`off`：从不记三连音（遇到三连音就报错）。不加引号的 `off` 会被 YAML 读成 false，同样按 `off` 处理 |
| `quantize.flam_window` | 数 | `1/8` | 装饰音窗口，单位为四分音符（`1/8` 即 32 分音符）。可写 `1/16`、`0.125` 等；`0` 关闭装饰音识别 |

判断规则（每一拍的手声部、脚声部分别决定）：

- 这一拍这一声部所有音离直拍网格都不超过 1/24 拍：按直拍记。
- 否则，`tuplets: auto` 且每个音离三连音网格都不超过 1/32 拍：记成三连音
  （`subdivision: 4` 时网格为 1/6 拍，能记三连音和 16 分六连音；`subdivision: 2` 时网格为 1/3 拍）。
  轻微的人为偏差（约 ±0.015–0.025 拍）一般可以识别；偏差超过 1/32 拍的三连音报错，请先在 DAW 中量化。
- 例外：有音离某个 64 分音符位置不超过 1/192 拍、而这个位置又不是三连音位置（例如正好在 3/16 拍）时，
  不记成三连音，报错并说明这是 32/64 分音符节奏。人为偏差恰好把音推到这种位置附近时也会这样报错
  （例如 1/3 拍处的音提前约 0.02 拍，落在 5/16 拍附近）。
- `subdivision: 4` 时，8 分音符与 8 分三连音同在一拍（拍头、1/3、1/2 拍处）正好落在六连音网格上，记成六连音；
  16 分音符与三连音同在一拍（如 1/4 与 1/3 拍处）两种网格都对不上，报错。
- 都不满足：报错，指出从乐谱起点数第几拍、哪个声部。不会按“差不多”的网格硬量化。
- 记成三连音的拍里，所有音都在直拍 16 分位置上的声部（例如另一个声部踩的四分或 16 分）照常按直拍记，不加三连音记号。
- flam 的主音天生偏晚，容差放宽到 1/16 拍（也不受上面 64 分位置例外的限制）；装饰音落在网格上时也可以用装饰音的位置来定位。

装饰音与重复触发（同一个 MIDI 音符）：

- 与第一次击打相差不超过 1/48 拍的击打视为同一下（重复触发），保留力度最大者，数量在提示里给出。
- 在某次击打之前 `flam_window` 以内、力度更弱的击打记为它的装饰音；一个主音最多两个装饰音：一个为 flam（带斜线的小 8 分音符），两个为 drag（连横梁的两个小 16 分音符）。
  连续渐强的快速击打不当作装饰音，会按 32 分音符报错。
- 其他情况下两次击打量化到同一位置会报错，不会丢掉其中一次。
- 不同音符之间不做装饰音识别。

## 拍号、速度、弱起

| 字段 | 类型 | 默认 | 说明 |
| --- | --- | --- | --- |
| `time_signature` | 字符串 `"n/4"` | 无 | MIDI 没有拍号事件时使用。MIDI 有拍号事件时，它必须与 MIDI 的第一个拍号相同，否则报错；之后的拍号变化总是取自 MIDI。都没有时按 4/4 并提示。只支持 1/4–12/4 |
| `tempo_bpm` | 数 | 乐谱起点（舍去开头多余的拍之后）生效的 MIDI 速度；起点之前没有速度事件时取第一个，MIDI 没有速度事件则 120 | 标题区 `BPM` 与 MusicXML 第一小节的速度。范围 10–400。与 MIDI 不同时给出提示，谱面按元数据。MIDI 中后续的速度变化仍会印出 |
| `pickup_beats` | 整数 | `0` | 弱起小节的拍数（四分音符）。弱起小节编号为 0，印出自己的拍号（如 `2/4`），可以有音符 |
| `source_leading_beats` | 整数 | 等于 `pickup_beats` | 源 MIDI 中第 1 小节（弱起之后第一个完整小节）开始的位置，以拍（四分音符）计。要求 `0 ≤ pickup_beats ≤ source_leading_beats` |

谱面从源 MIDI 的 `source_leading_beats − pickup_beats` 拍处开始（之前的部分舍去），落在舍去部分里的音符会报错。示例：源 MIDI 开头有一整小节（4 拍）
空白，希望谱面只保留 2 拍空白、印成 2/4 弱起，写 `source_leading_beats: 4`、`pickup_beats: 2`。
弱起小节之后的小节线按 MIDI 拍号排；MIDI 的拍号变化必须正好落在这些小节线上，否则报错。

## 力度

| 字段 | 类型 | 默认 | 说明 |
| --- | --- | --- | --- |
| `dynamics.ghost_below` | 整数 | 无（不启用） | 手部力度**小于**该值的音记为鬼音：PDF 符头加括号，MusicXML `notehead parentheses="yes"` |
| `dynamics.accent_above` | 整数 | 无（不启用） | 手部力度**大于**该值的音加重音记号 `>`（MusicXML `accent`） |

脚部（底鼓、踩镲踏板）不做鬼音 / 重音标记。

## 记谱

| 字段 | 类型 | 默认 | 说明 |
| --- | --- | --- | --- |
| `notation.repeats` | 字符串 | `simile` | 控制 1 小节（`%`）与 2 小节（`//`）反复记号（simile）的记谱。`simile`：启用（默认）；`off`：关闭（所有非空小节都完整记出）。不加引号的 `off` 会被 YAML 读成 false，同样按 `off` 处理。命令行 `--repeats` 优先 |
| `notation.repeat_counters` | 布尔 | `true` | 当 1 小节 `%` 连续出现 2 小节及以上（即连续 3 个及以上相同小节）时，是否在每个 `%` 上方印出反复次数（`2`、`3`、`4`、…）。必须是 YAML 布尔值，写成带引号的字符串（如 `"false"`）会报错 |
| `notation.beam_eighths` | 字符串 | `beat` | 8 分音符的横梁分组方式。`beat`：按拍分组，不跨拍（默认）；`half-bar`：在 4/4 的非弱起小节中，若前半小节（第 1–2 拍）或后半小节（第 3–4 拍）恰好为连续 4 个普通直拍 8 分音符，则用一条横梁连成一组（手、脚声部各自独立判断）。命令行 `--beam-eighths` 优先 |

孤立的单个 `%`（仅连续 2 个相同小节）不印数字。2 小节反复 `//` 的符号本身始终带有 `2`，不受 `repeat_counters` 影响。反复记号的判定规则、分页处理与横梁规则见 [notation-conventions.zh-CN.md](notation-conventions.zh-CN.md) 的“反复记号”和“横梁”。

```yaml
notation:
  repeats: simile        # 或 off（命令行 --repeats 优先）
  repeat_counters: true  # 设为 false 时省略连续 % 上方的数字（2, 3, 4…）
  beam_eighths: beat     # beat（默认）或 half-bar（命令行 --beam-eighths 优先）
```

## 段落

| 字段 | 类型 | 默认 | 说明 |
| --- | --- | --- | --- |
| `sections` | 映射 | 无 | 顶层字段，格式为 `小节号: 排练记号`。键为大于等于 1 且在乐谱小节号范围内的整数（不可指定第 0 弱起小节）；值为去掉首尾空白后 1–24 个字符的可打印 ASCII 字符串（中文、日文等非 ASCII 字符或空字符串会报错） |

每个段落的首小节前会印双纵线（曲首以及弱起小节之后除外），并在小节上方印带方框的排练记号。同时，段落起点会拆开多小节休止、重置 1 小节（`%`）与 2 小节（`//`）反复记号，并在换行优化时优先从段落起点另起一行。详见 [notation-conventions.zh-CN.md](notation-conventions.zh-CN.md) 的“段落与排练记号”。

```yaml
sections:
  1: Intro
  9: A
  25: Chorus
```

## 旧字段

早期元数据中的字段仍可读，但新文件请用新写法：

| 旧字段 | 新写法 | 说明 |
| --- | --- | --- |
| `beats`、`beat_type` | `time_signature: "4/4"` | 只写其中一个时另一个按 4；同时有 `time_signature` 时以它为准 |
| `quantize_divisions_per_beat` | `quantize.subdivision` | 同时存在时以 `quantize.subdivision` 为准 |
