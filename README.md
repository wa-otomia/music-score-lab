# music-score-lab

把鼓 MIDI 和一份曲目元数据（YAML）转换成两份成品：

- `score.musicxml`：可编辑的 MusicXML 4.0，MuseScore 等软件可以直接打开继续修改；
- `score.pdf`：A4 打印用鼓谱，日式记谱，谱面为矢量，标题等文字可以选中、复制、搜索。

仓库同时存放多首曲目的源 MIDI、元数据和成品，**不是**某一首歌的专用仓库。
人和编程代理（Claude Code、Codex 等）遵守同一套规则，见 [AGENTS.md](AGENTS.md)。

## 快速开始

```bash
python3 scripts/build_score.py scores/inochi-ni-kirawareteiru/source.mid \
  --metadata scores/inochi-ni-kirawareteiru/metadata.yaml \
  --out-dir build/inochi
```

这一条命令依次：读 MIDI → 量化、切小节 → 写 `build/inochi/score.musicxml` → 排版 `build/inochi/score.pdf`
→ 校验两份输出。屏幕上会打印小节数、音符数、装饰音数、合并的重复触发数，以及所有提示。

| 退出码 | 含义 |
| --- | --- |
| 0 | 生成并校验通过 |
| 1 | 校验失败（输出与 MIDI 模型不一致，或 PDF 文字、字体不合格） |
| 2 | 输入无法忠实记谱（未映射的音符、不支持的拍号或节奏等），或缺少外部命令；错误信息会说明要改什么 |

常用选项：

| 选项 | 作用 |
| --- | --- |
| `--drum-map NAME_OR_PATH` | 覆盖元数据里的 `drum_map`（内置 `gm`、`fpc-default`，或 YAML 路径） |
| `--track TEXT` | 只用轨道名包含该文字的轨道（不区分大小写，可重复） |
| `--channel N` | 只用 MIDI 通道 N（1–16，可重复） |
| `--no-pdf` | 只生成并校验 MusicXML，不需要 TeX 环境 |
| `--work-dir DIR` | 保留 PDF 中间文件（TeX 源码、未合成的谱页），便于排查 |
| `--xsd PATH` | MusicXML 4.0 `musicxml.xsd` 路径；也可设环境变量 `MUSICXML_XSD`。提供时额外做 schema 校验 |

## 环境要求

- Python 3.10 及以上；Python 包见 `requirements.txt`（mido、PyYAML、PyMuPDF）。
- 出 PDF 需要：MusiXTeX（含 musixper 打击乐符头）、XeLaTeX + fontspec + xeCJK + pdfpages、Ghostscript、
  本机安装的 Noto Sans CJK JP 字体。仓库不附带任何字体文件。
- 可选：poppler-utils（`pdffonts` 字体检查、`pdftoppm` 渲染预览）、MusicXML 4.0 XSD（schema 校验）、MuseScore（编辑 MusicXML）。

Debian / Ubuntu：

```bash
sudo apt install texlive-music texlive-xetex texlive-lang-cjk texlive-latex-recommended \
  ghostscript poppler-utils fonts-noto-cjk python3-mido python3-yaml python3-pymupdf
# 跑测试另需：
sudo apt install python3-pytest python3-lxml
```

也可以用虚拟环境：`python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt pytest lxml`
（TeX、Ghostscript 和字体仍需用系统包安装）。

MusicXML 4.0 的 XSD 不在仓库里。需要 schema 校验时，从 W3C MusicXML 4.0 发布包取得 `musicxml.xsd`，
然后 `export MUSICXML_XSD=/path/to/musicxml.xsd`。没有设置时跳过 schema 校验，其余校验照常进行。

## 目录结构

```text
AGENTS.md                      代理与贡献者规则（CLAUDE.md 只有一行 @AGENTS.md）
configs/instruments.yaml       乐器目录：谱表位置、符头、开/闭记号、日文名、图例缩写
configs/drum-maps/gm.yaml      General MIDI / GS 打击乐映射（音符号 27–87）
configs/drum-maps/fpc-default.yaml  FL Studio FPC 默认布局（继承 gm）
docs/metadata.md               元数据字段说明
docs/drum-maps.md              乐器目录与鼓映射说明
docs/notation-conventions.md   本仓库实现的日式鼓谱记法
templates/metadata.yaml        新曲目元数据模板
scripts/build_score.py         主入口：一条命令出 MusicXML + PDF 并校验
scripts/score_core.py          共用记谱模型：选轨、映射、量化、小节、声部、休止、横梁
scripts/midi_to_musicxml.py    模型 → MusicXML
scripts/midi_to_musixtex.py    模型 → MusiXTeX 源码
scripts/render_score.py        MusiXTeX → Ghostscript 转曲 → XeLaTeX 合成 → PDF
scripts/pdf_tounicode.py       修正 PDF 的 ToUnicode，让各种阅读器复制出正确文字
scripts/validate_score.py      校验 MusicXML / PDF 是否忠实于模型
scripts/retag_gm_channel10.py  复制一份 MIDI 并改成第 10 通道（转换本身不需要）
tests/                         pytest 测试
scores/<曲目 slug>/            每首曲目一个目录（见下文）
build/                         本地输出目录，已被 .gitignore 忽略
```

## PDF 的样子

- 第一页顶部是日文标题区：曲名、副标题、`アーティスト　『アルバム』`、`作詞・作曲：…　歌：…`、
  `ドラム採譜・編曲：…`、`備考：…`，最后一行形如 `BPM 200　拍子 2/4（弱起）→ 4/4　上声部（符尾上）＝手　下声部（符尾下）＝足`。
  同一个人担任的多个职务合并成一个标签，规则见 [docs/metadata.md](docs/metadata.md)。
- 标题区下方是**凡例**：只列本曲实际用到的乐器，每项是一小段谱表上的符头，下面印缩写和日文名。
- 续页顶部印 `曲名　アーティスト　ドラム譜`；每页底部印页码 `n / N`；元数据有 `copyright` 时印在第一页底部。
- 谱面（音符、休止符、小节号、拍号、速度记号）全部是矢量路径，放大不失真。能复制出的文字**只有**标题区、凡例、
  页眉和页码，字体为嵌入子集的 Noto Sans CJK JP。校验会分别按 ActualText（Poppler、MuPDF、Chrome 的 PDFium 等使用）
  和 ToUnicode（pdf.js、Preview 等使用）两种方式提取文字，两种结果都必须与预期一致。
- 每行最多 4 小节，每行开头印小节号；弱起小节编号为 0。

## 支持的输入

- **选轨**：FL Studio FPC 直接导出（第 1 通道、轨道名如 `FPC 1`）、GM 第 10 通道、多轨 MIDI 都可以。
  自动选择顺序：只有一个含音符的轨道/通道就用它；否则用所有第 10 通道；否则用轨道名含
  `fpc`、`drum`、`perc`、`kit`、`ドラム`、`鼓`（不区分大小写）的轨道；仍无法判断时报错并列出文件中的轨道，
  这时在元数据 `midi.tracks` / `midi.channels` 或命令行 `--track` / `--channel` 中指定。
- **鼓映射**：内置 `gm` 与 `fpc-default`；可以用元数据 `note_map` 改单个音符，或写自己的映射文件。
  映射里没有的音符直接报错，不猜。详见 [docs/drum-maps.md](docs/drum-maps.md)。
- **拍号**：1/4 到 12/4，包括落在小节线上的拍号变化，取自 MIDI 拍号事件；MIDI 没有拍号时用元数据
  `time_signature`，都没有则按 4/4 并给出提示。
- **节奏网格**：16 分（默认）或 8 分。每一拍、每个声部（手/脚）单独判断：直拍网格对不上而三连音网格对得上时，
  自动记成三连音（8 分网格下为 8 分三连音；16 分网格下为三连音或六连音）。所以手打三连音、脚踩直拍 16 分这样的
  复合节奏也能记。
- **装饰音**：同一音高、在主音之前很近（默认 32 分音符以内）且更弱的击打记为装饰音（一个主音最多两个，即 flam / drag）。
- **弱起**：`pickup_beats` 指定弱起拍数，弱起小节可以有音符，也可以全空；编号为 0，单独印拍号。
  `source_leading_beats` 用来去掉源 MIDI 开头多余的空拍。
- **速度变化**：MIDI 中的速度变化印在所在小节开头（♩ = 数值），MusicXML 中同步写入；变化发生在小节中途时会给出提示。
- **力度（可选）**：设置 `dynamics.ghost_below` / `dynamics.accent_above` 后，手部的弱音印成括号符头（ghost note），
  强音加重音记号 `>`。默认不启用。

## 已知限制

- 不支持 32 分音符、五连音等其他连音、同一声部同一拍里直拍与三连音混用，以及未量化的演奏：一律报错并指出第几拍、
  哪个声部，不会悄悄改动节奏或丢音。只有相差不到 1/48 拍的同音高重复触发会被合并（提示中给出数量）。
- 不支持 6/8、12/8 等复合拍，也不支持分母不是 4 的拍号；请在 DAW 中改成 x/4 加三连音。
- 不记滚奏（roll）和震音（tremolo）记号，不记左右手顺序（sticking）。
- 拍手、牛铃、沙锤等辅助打击乐与鼓组印在**同一个谱表**上，靠位置和符头区分，凡例中一定会列出。
- 休止符：PDF 一般只在**两个声部都休止**的地方印休止符，以免谱面拥挤；三连音组内部和复合节奏的拍里会按声部印出，
  保证每组时值完整。MusicXML 中每个声部都有完整的休止符。
- 音符时值按鼓谱惯例推断：一个音持续到同一声部的下一个音或本拍结束，最长四分音符；不表达 MIDI 中的音长。
- 映射到同一位置、同一符头的不同 MIDI 音符在谱面上无法区分（例如 GM 38 和 40 都印成军鼓）；它们同时出现时会给出提示。
- 标题等文字必须是 Noto Sans CJK JP 能显示的字符：表情符号等缺字会报错；两个外形相同的字符（如 〜 与 ～）
  在同一份谱里混用也会报错，因为复制出来无法区分。

## 添加新曲目

1. 选一个稳定的 ASCII slug，建立 `scores/<slug>/`。
2. 把**原始** MIDI 原样放成 `scores/<slug>/source.mid`，以后不再改动它。
3. 复制 [templates/metadata.yaml](templates/metadata.yaml) 为 `scores/<slug>/metadata.yaml`，填写署名、鼓映射、弱起等；
   字段见 [docs/metadata.md](docs/metadata.md)。
4. 运行 `python3 scripts/build_score.py scores/<slug>/source.mid --metadata scores/<slug>/metadata.yaml --out-dir build/<slug>`，
   按报错和提示修改元数据（未映射的音符写进 `note_map`，多轨时写 `midi.tracks` 等）。
5. 把 PDF 渲染成图片逐页检查（例如 `pdftoppm -r 100 -png build/<slug>/score.pdf build/<slug>/page`），
   确认无误后再把 `score.musicxml`、`score.pdf` 复制到 `scores/<slug>/`。
6. 写 `scores/<slug>/README.md`：来源、派生文件、生成方法、采谱说明和版权说明。

## 示例曲目

[命に嫌われている。](scores/inochi-ni-kirawareteiru/README.md)：作詞・作曲・歌 カンザキイオリ，收录于『不器用な男』；
ドラム採譜・編曲 音宮，含采谱者的重构与创作。这是爱好者采谱，**不是**官方乐谱。

## 分步脚本

日常使用 `build_score.py` 即可。排查问题时可以单独运行各步骤（`--drum-map`、`--track`、`--channel` 用法相同）：

```bash
python3 scripts/midi_to_musicxml.py MIDI --metadata META --out OUT.musicxml
python3 scripts/render_score.py MIDI --metadata META --out OUT.pdf [--keep-tex OUT.tex] [--work-dir DIR]
python3 scripts/validate_score.py MIDI --metadata META --musicxml OUT.musicxml --pdf OUT.pdf [--xsd XSD]
python3 scripts/midi_to_musixtex.py MIDI --metadata META --out OUT.tex     # 只看 MusiXTeX 源码
python3 scripts/retag_gm_channel10.py source.mid --out build/gm-channel10.mid  # 给只认第 10 通道的软件用
python3 -m pytest -q tests
```

## 授权与版权

- 本仓库的**原创代码和文档**以 MIT 许可证发布（见 `LICENSE`）。
- MIT 许可证**不适用于** `scores/` 目录，也不适用于任何第三方音乐作品：歌曲、编曲、歌词、录音，以及仓库中的 MIDI、
  MusicXML、PDF 乐谱。这些内容的著作权和发行权属于各自的权利人。
- 采谱或注明出处都不等于获得发行授权。未取得权利人许可，不要公开发布受版权保护的乐谱。
  本仓库不假定任何乐谱已获准公开再发行。
