# 代理操作规则

本文件是编程代理（Claude Code、Codex 等）和人类贡献者在本仓库工作的唯一规则来源。
`CLAUDE.md` 只有一行 `@AGENTS.md`，不要在那里另写规则。修改乐谱、转换器或发布 PDF 之前先读完本文件。
面向使用者的说明见 [README.md](README.md)。

## 仓库定位

- 这是一个可扩展的**用户自制鼓谱**合集，加上一套可复现的「鼓 MIDI → MusicXML + PDF」工具链，不专属于任何一首歌。
- 乐谱资料放在 `scores/<稳定的 ASCII slug>/`；可复用的软件放在 `scripts/`、`configs/`、`tests/`、`docs/`、`templates/`。
- 不要声称某份乐谱是官方乐谱，或与原录音逐音一致。源 MIDI 可能含采谱者的重构或改编。

## 来源与每首曲目的文件

- `source.mid`：用户提供的原始 MIDI，**不可变**。不要用量化、移位或改通道后的版本覆盖它。
- 派生 MIDI（如 `gm-channel10.mid`）可以有，但必须在曲目 README 中写明由哪个文件、用哪条命令得到。
- `metadata.yaml`：署名、鼓映射、选轨、弱起、量化等设置，字段见 `docs/metadata.md`；新曲目从 `templates/metadata.yaml` 复制。
- `score.musicxml`：可编辑的交换格式；`score.pdf`：经人工检查的打印成品。两者都由 `scripts/build_score.py` 生成。
- `README.md`：该曲目的来源链、生成命令、采谱说明和版权说明。
- 重新生成时保留元数据中的署名和注释；不要未经检查就用新输出覆盖已提交的 `score.musicxml` / `score.pdf`。

## 流水线

```text
source.mid + metadata.yaml
  └─ score_core.py      选轨 → 鼓映射 → 装饰音/重复识别 → 逐拍量化（直拍/三连音）→ 切小节
                        → 每声部时值、休止、横梁（唯一的节奏推断处）
       ├─ midi_to_musicxml.py   → score.musicxml（MusicXML 4.0）
       └─ midi_to_musixtex.py   → MusiXTeX 源码（只含 ASCII）
            └─ render_score.py
                 1. musixtex -d 排谱（凡例符头另排成小谱表并裁切）
                 2. gs -dNoOutputFonts 把谱面字形全部转成矢量路径
                 3. XeLaTeX + xeCJK + pdfpages 合成：标题区、凡例文字、页眉、页码是真文字（Noto Sans CJK JP 子集）
                 4. pdf_tounicode.py 按 ActualText 修正 ToUnicode，保证复制出正确字符
  └─ validate_score.py  校验 MusicXML 与 PDF
```

- 两个输出器只翻译 `score_core` 的结果，不各自推断节奏。改记谱逻辑就改 `score_core.py`，并同时检查两种输出。
- 不要用绘图原语伪造乐谱；MusicXML 必须是真正的音符、声部和横梁。
- 输入无法忠实记谱时（未映射的音符、不支持的拍号、32 分音符或五连音等），转换器必须报错并说明怎么改，
  不能静默丢音或猜测。新增支持要同时改转换器和测试。
- 乐器的位置、符头、日文名只在 `configs/instruments.yaml` 定义；音符号到乐器的对应只在 `configs/drum-maps/*.yaml`
  和曲目的 `note_map` 中定义。说明见 `docs/drum-maps.md`。

## 验证义务

改了转换器、配置或乐谱，交付前都要完成：

1. `python3 -m pytest -q tests`（测试沙箱不要放在易失目录；可用 `--basetemp` 指定）。
2. 对受影响的曲目运行 `python3 scripts/build_score.py <midi> --metadata <yaml> --out-dir build/<slug>`，
   退出码必须为 0。设置 `MUSICXML_XSD` 指向 MusicXML 4.0 的 `musicxml.xsd`，让校验包含 XSD schema 检查。
   `build_score.py` 的校验包括：小节数、拍号、弱起；每声部每小节时值之和；每个 MIDI 音符的记谱次数；横梁层级；
   PDF 为 A4、谱面为矢量且无位图、字体全部嵌入并带 ToUnicode、每页可复制文字恰好等于标题区/凡例/页眉/页码。
3. 把 PDF 渲染成图片（如 `pdftoppm -r 100 -png`）亲眼检查：至少第一页（标题区、凡例）、最密集的一页、中间一页和最后一页。
   重点看符头形状、开/闭记号位置、横梁数量、三连音数字、装饰音、休止符、拍号变化、换行和换页、文字有无缺字或替换字形。
4. 可选：用 pdf.js（Firefox 的 PDF 引擎）提取文字，再核对一次复制结果。
5. 说明改动影响的是乐谱内容，还是只影响排版。

## 记谱约定摘要

详见 `docs/notation-conventions.md`。

- 一个五线谱表、打击乐谱号。手（军鼓、嗵鼓、镲、踩镲、辅助打击乐）为上声部，符干朝上；脚（底鼓、踩镲踏板）为下声部，符干朝下。
- 鼓用实心椭圆符头，镲和踩镲用叉形符头；开（open）印小圆圈 ○，半开印 ⊖，闭（closed）印 ＋；手部印在符头上方、脚部印在符头下方，位置相对于实际符头计算。
- 横梁按拍分组，不跨拍：8 分一条横梁，16 分两条；横梁组里孤立的 16 分音符用短横梁（hook），横梁组以外的单个音符用符尾。三连音印数字 3，16 分六连音印 6。
- 弱起小节编号为 0 并印出自己的拍号；拍号变化只能在小节线上。
- PDF 只在两个声部都休止的地方印休止符；MusicXML 中每个声部都有完整的休止符。连续空小节合并成多小节休止。
- 第一页印凡例，只列实际用到的乐器。
- 不能从 MIDI 推断左右手顺序，不要在谱上添加 sticking。

## 提交规范

- 不要提交 `build/` 下的任何内容、TeX 中间文件、日志、临时 PNG、字体文件（包括字体子集）、凭据或无关文件。
  字体只从系统安装（`fonts-noto-cjk`）。
- 改共享转换器时，改动保持小而集中；测试和渲染检查通过之前，不要提交新生成的乐谱。
- 文档使用简体中文；日文只用于歌曲署名和乐器的日文名。文档内容必须与当前代码一致，改了行为就同步改文档。

## 版权

- MIT 许可证**只**适用于本仓库的原创代码和文档，不授予歌曲、编曲、歌词、录音，以及 `scores/` 下 MIDI、MusicXML、PDF 的任何权利。
- 每首曲目的公开发行权需要单独确认。署名、「爱好者采谱」说明和软件许可证都不能代替权利人的许可。
- **未经权利人授权，不要公开上传受版权保护的乐谱。** 不确定时保持私有，并询问用户；不要把用户「请帮我采谱」理解为发行许可。
