[日本語](README.md) | [简体中文](README.zh-CN.md) | [English](README.en.md)

# music-score-lab

ドラムの MIDI と曲ごとのメタデータ（YAML）から、次の 2 つの成果物を生成します。

- `score.musicxml`：編集可能な MusicXML 4.0。MuseScore などでそのまま開いて修正を続けられます。
- `score.pdf`：A4 印刷用のドラム譜。日本式の記譜で、譜面はベクター描画、タイトルなどの文字は選択・コピー・検索できます。

このリポジトリは複数の曲の元 MIDI、メタデータ、成果物をまとめて管理するもので、特定の 1 曲専用の**ものではありません**。
人もコーディングエージェント（Claude Code、Codex など）も同じルールに従います。詳しくは [AGENTS.md](AGENTS.md) を参照してください。

## クイックスタート

```bash
python3 scripts/build_score.py scores/inochi-ni-kirawareteiru/source.mid \
  --metadata scores/inochi-ni-kirawareteiru/metadata.yaml \
  --out-dir build/inochi
```

このコマンド 1 つで、MIDI の読み込み → クオンタイズ・小節分割 → `build/inochi/score.musicxml` の書き出し → `build/inochi/score.pdf` の組版
→ 2 つの出力の検証、を順に行います。画面には、小節数、音符数、装飾音数、統合した重複トリガー数を示す `"<曲名>": <概要>` の形式の 1 行と、注意（プログラムが `Note: …` として出力するもの）がすべて表示されます。

| 終了コード | 意味 |
| --- | --- |
| 0 | 生成と検証に成功 |
| 1 | 検証失敗：出力が記譜モデルと一致しない（MusicXML の内容、PDF の文字やフォントが不適合） |
| 2 | 入力または環境の問題：MIDI／メタデータの誤り、または忠実に記譜できない内容（未割り当てのノート、非対応の拍子記号やリズムなど）、タイトルなどの文字を印字・コピーできない、外部コマンドがない、XSD ファイルが見つからない・読み込めない・解析できない、lxml がない。エラーメッセージに修正すべき点が示されます |

主なオプション：

| オプション | 働き |
| --- | --- |
| `--drum-map NAME_OR_PATH` | メタデータの `drum_map` を上書きします（組み込みの `gm`、`fpc-default`、または YAML のパス） |
| `--track TEXT` | トラック名にその文字列を含むトラックだけを使います（大文字小文字は区別せず、複数指定可） |
| `--channel N` | MIDI チャンネル N だけを使います（1–16、複数指定可） |
| `--no-pdf` | MusicXML の生成と検証だけを行います（TeX 環境は不要） |
| `--legend` / `--no-legend` | 1 ページ目の楽器凡例を印刷する／しない。指定がなければメタデータの `legend` に従い、メタデータにもなければ印刷しません |
| `--repeats MODE` | 反復記号モード（`off`、`simile`、`full`）を指定します。メタデータの `notation.repeats` より優先されます（既定は `simile`） |
| `--beam-eighths MODE` | 8 分音符の連桁モード（`beat`、`half-bar`）を指定します。メタデータの `notation.beam_eighths` より優先されます（既定は `beat`） |
| `--system-spacing SCALE` | PDF の段間（システム間の縦間隔）の倍率（`0.7`–`2.5`）を指定します。メタデータの `notation.system_spacing` より優先されます（既定は `1.1`、`1.0` で標準の詰めた間隔。PDF のみ） |
| `--work-dir DIR` | PDF の中間ファイル（TeX ソース、合成前の譜面ページ）を残します。原因調査に使います |
| `--xsd PATH` | MusicXML 4.0 の `musicxml.xsd` のパス。環境変数 `MUSICXML_XSD` でも指定できます。指定すると schema 検証を追加で行います（lxml が必要） |

## 動作環境

- Python 3.10 以上。Python パッケージは `requirements.txt` を参照してください（mido、PyYAML、PyMuPDF。lxml は XSD 検証を行うときだけ必要で、テストでも使います）。
- PDF の生成には次が必要です：MusiXTeX（musixper のパーカッション符頭を含む）、XeLaTeX + fontspec + xeCJK + pdfpages、Ghostscript、
  ローカルにインストールされた Noto Sans CJK JP フォント。リポジトリにフォントファイルは含まれません。
- 任意：poppler-utils（`pdffonts` によるフォント確認、`pdftoppm` によるプレビュー描画）、MusicXML 4.0 XSD（schema 検証）、MuseScore（MusicXML の編集）。

Debian / Ubuntu の場合：

```bash
sudo apt install texlive-music texlive-xetex texlive-lang-cjk texlive-latex-recommended \
  ghostscript poppler-utils fonts-noto-cjk python3-mido python3-yaml python3-pymupdf python3-lxml
# テストの実行には次も必要：
sudo apt install python3-pytest
```

仮想環境も使えます：`python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt pytest`
（TeX、Ghostscript、フォントはシステムのパッケージで入れる必要があります）。

MusicXML 4.0 の XSD はリポジトリに含まれていません。schema 検証が必要なときは、W3C の MusicXML 4.0 配布パッケージから `musicxml.xsd` を取得し、
`export MUSICXML_XSD=/path/to/musicxml.xsd` を設定してください。未設定の場合は schema 検証をスキップし、それ以外の検証は通常どおり行われます。

## ディレクトリ構成

```text
AGENTS.md                      エージェントと貢献者向けのルール（CLAUDE.md は @AGENTS.md の 1 行のみ）
configs/instruments.yaml       楽器カタログ：譜表上の位置、符頭、開／閉記号、日本語名、凡例の略称
configs/drum-maps/gm.yaml      General MIDI / GS パーカッションマップ（ノート番号 27–87）
configs/drum-maps/fpc-default.yaml  FL Studio FPC のデフォルト配置（gm を継承）
docs/metadata.md               メタデータのフィールド説明
docs/drum-maps.md              楽器カタログとドラムマップの説明
docs/notation-conventions.md   このリポジトリが実装する日本式ドラム譜の記法
templates/metadata.yaml        新しい曲のメタデータのテンプレート
scripts/build_score.py         メインのエントリポイント：1 コマンドで MusicXML + PDF を生成して検証
scripts/score_core.py          共通の記譜モデル：トラック選択、マッピング、クオンタイズ、小節、声部、休符、連桁
scripts/score_structure.py     共通の構造計画：複数小節休符、反復記号（% / // / |: :| / 1. 2.）、セクション区切り
scripts/midi_to_musicxml.py    モデル → MusicXML
scripts/midi_to_musixtex.py    モデル → MusiXTeX ソース
scripts/render_score.py        MusiXTeX → Ghostscript でアウトライン化 → XeLaTeX で合成 → PDF
scripts/pdf_tounicode.py       PDF の ToUnicode を修正し、どのリーダーでも正しい文字をコピーできるようにする
scripts/validate_score.py      MusicXML / PDF がモデルに忠実か検証
scripts/retag_gm_channel10.py  MIDI を複製してチャンネル 10 に付け替える（変換自体には不要）
tests/                         pytest のテスト
scores/<曲の slug>/            曲ごとに 1 ディレクトリ（後述）
build/                         ローカルの出力先。.gitignore で無視される
```

## PDF の見た目

- 1 ページ目の上部は日本語のタイトル部です：曲名、サブタイトル、`アーティスト　『アルバム』`、`作詞・作曲：…　歌：…`、
  `ドラム採譜・編曲：…`、`備考：…`、最後の行はテンポ `BPM 200` です。
  同じ人が複数の役割を担当する場合は 1 つのラベルにまとめます。規則は [docs/metadata.md](docs/metadata.md) を参照してください。
- **凡例**（デフォルトでは印刷しません）：メタデータに `legend: true` と書くか、コマンドラインに `--legend` を付けると、タイトル部の下にこの曲で実際に使う楽器を印刷します。
  各項目は小さな譜表上の符頭で、その下に略称と日本語名が付きます。メタデータで有効でも、`--no-legend` で一時的に無効にできます。
- 2 ページ目以降の上部には続きページのヘッダー `<曲名>　<アーティスト>　ドラム譜` を印刷します。各ページの下部にはページ番号 `n / N` を印刷し、メタデータに `copyright` があれば 1 ページ目の下部に印刷します。
- 譜面（音符、休符、小節番号、拍子記号、テンポ記号、反復記号、枠付きリハーサルマーク）はすべてベクターのパスなので、拡大しても劣化しません。コピーできる文字は、タイトル部、凡例、
  続きページのヘッダー、ページ番号、著作権表示の行**だけ**で、フォントは埋め込みサブセットの Noto Sans CJK JP です。漢字・かなとラテン文字の間には自動でスペースを入れず、メタデータに書いたスペースはそのまま印刷します（例外：全角句読点「、。）」」など」の直後にある半角スペース、およびかな・漢字と全角括弧の間にある半角スペースは、日本語組版の規則に従い印刷もコピーもしません）：
  pdftotext や pdf.js でコピーするとこれらの半角スペースは保持されるので、コピーした署名はメタデータと一致します。ただし全角スペース（U+3000。タイトル部で各項目を区切る全角スペースを含む）は、
  pdftotext や pdf.js では半角スペースとしてコピーされます。PyMuPDF は U+3000 を保持しますが、漢字・かなの隣の半角スペースは落とします。検証では ActualText（Poppler、MuPDF、Chrome の PDFium などが使用）
  と ToUnicode（pdf.js、Preview などが使用）の 2 通りで文字を抽出し、期待値と比較します（比較の前に NFC 正規化を行い、空白をすべて除去するので、
  確認するのは文字とその順序だけで、スペースや改行は確認しません）。
- 改行はフレーズに沿った最適化によって決まります（4 小節フレーズやセクション・反復の境界を優先。弱起 0 小節目がある場合は 1–4 小節目と 1 段目にまとめ、最終段も含め最大 5 小節。複数小節休符は 1 小節、2 小節反復 `//` は 2 小節として扱い分割しません）。各段の先頭に枠付きの小節番号を、段途中の各小節の先頭にも小さな小節番号を印刷します（弱起小節は 0、2 小節反復 `//` の中央の小節線では省略）。

## 対応する入力

- **トラック選択**：FL Studio FPC の直接エクスポート（チャンネル 1、トラック名は `FPC 1` など）、GM チャンネル 10、マルチトラック MIDI のいずれにも対応します。
  自動選択の順序：音符を含むトラック／チャンネルが 1 つだけならそれを使います。そうでなければチャンネル 10 をすべて使います。それもなければトラック名に
  `fpc`、`drum`、`perc`、`kit`、`ドラム`、`鼓`（大文字小文字は区別しません）を含むトラックを使います。それでも判断できない場合は、ファイル中のトラックを列挙してエラーにします。
  その場合はメタデータの `midi.tracks` / `midi.channels`、またはコマンドラインの `--track` / `--channel` で指定してください。
- **ドラムマップ**：組み込みの `gm` と `fpc-default` があります。メタデータの `note_map` で個別のノートを変更することも、独自のマップファイルを書くこともできます。
  マップにないノートは推測せずエラーにします。詳しくは [docs/drum-maps.md](docs/drum-maps.md) を参照してください。
- **拍子記号**：1/4 から 12/4 まで、小節線上での拍子変更を含みます。MIDI の拍子イベントから取得し、MIDI に拍子がなければメタデータの
  `time_signature` を使い、どちらもなければ 4/4 として注意を出します。
- **リズムグリッド**：16 分（デフォルト）または 8 分です。拍ごと、声部（手／足）ごとに個別に判断します。ストレートな拍グリッドに合わず 3 連符グリッドに合う場合は、
  自動で 3 連符として記譜します（8 分グリッドでは 8 分 3 連符、16 分グリッドでは 3 連符または 6 連符）。そのため、手が 3 連符で足がストレートの 16 分、といった
  複合リズムも記譜できます。3 連符の判定はやや厳しめです（規則は [docs/metadata.md](docs/metadata.md) の「クオンタイズ」を参照）：わずかな人為的ずれは識別できますが、
  ずれが 1/32 拍を超える場合や、音が 3/16 拍のような 64 分位置に来る場合はエラーになるので、先に DAW でクオンタイズしてください。
- **装飾音**：同じ音高で、主音の直前（デフォルトでは 32 分音符以内）にあり、かつ弱い打撃は装飾音として記譜します（主音 1 つにつき最大 2 つ。1 つは斜線付きの小さな 8 分音符＝フラム、2 つは連桁でつないだ小さな 16 分音符 2 つ＝ドラッグとして印刷します）。
- **弱起**：`pickup_beats` で弱起の拍数を指定します。弱起小節には音符があっても、まったく空でも構いません。番号は 0 で、拍子記号は単独で印刷します。
  `source_leading_beats` は、元 MIDI の先頭にある余分な空拍を取り除くために使います。
- **テンポ変更**：MIDI 内のテンポ変更は、その小節の先頭に（♩ = 数値）として印刷し、MusicXML にも同様に書き込みます。小節の途中でテンポが変わる場合は注意を出します。
- **強弱（任意）**：`dynamics.ghost_below` / `dynamics.accent_above` を設定すると、手パートの弱い音は括弧付き符頭（ゴーストノート）で印刷し、
  強い音にはアクセント記号 `>` を付けます。デフォルトでは無効です。
- **反復記号と連桁**：既定では 1 小節（`%`）および 2 小節（`//`）の反復記号が有効です（`notation.repeats: simile`）。`full` にするとフレーズ単位の `|: ... :|` 反復と 1 番・2 番括弧（`1.`／`2.`）も非破壊で折りたたみ、`off` にするとすべて展開します（`--repeats` で上書き可）。また、`notation.beam_eighths: half-bar`（または `--beam-eighths half-bar`）で 4/4 小節の半小節 4 連 8 分音符の連桁を有効にできます。
- **セクション（任意）**：メタデータのトップレベル `sections`（`元の小節番号: ASCII ラベル`）で複縦線・枠付きリハーサルマーク・反復／休符のリセット・セクション先頭での改段を指定できます。

## 既知の制限

- 32 分音符（および 3/16 拍のような 64 分位置）、5 連符などのその他の連符、同じ声部の同じ拍内での 16 分音符と 3 連符の混在、
  およびクオンタイズされていない演奏には対応しません。いずれもエラーにして第何拍のどの声部かを示し、リズムをこっそり変えたり音を落としたりはしません。16 分グリッドでは、8 分音符と 8 分 3 連符の混在
  （拍頭、1/3、1/2 拍の位置など）が 6 連符グリッド上に載るため、6 連符として記譜できます。同じ音高の重複トリガーのうち統合されるのは、間隔が 1/48 拍以内のものだけです
  （件数は注意に表示されます）。
- 6/8、12/8 などの複合拍子や、分母が 4 でない拍子記号には対応しません。DAW で x/4 に 3 連符を組み合わせる形に直してください。
- ロール（roll）とトレモロ（tremolo）の記号、および左右の手順（スティッキング）は記譜しません。
- ハンドクラップ、カウベル、シェイカーなどの補助パーカッションは、ドラムセットと**同じ譜表**に印刷し、位置と符頭で区別します。凡例（`legend: true` / `--legend`）を有効にすると、それらが一覧に載ります。
- 休符：2 つの声部がそれぞれ各拍を埋めます。手・足のどちらかの声部で、ある拍内に音がない部分には休符を印刷します（手声部は上寄り、足声部は下寄り）。
  2 つの声部が同じ時刻に同じ長さの休符を持つ場合は、中央に 1 つの休符として合成します。ある声部が小節全体で音を持たない場合は全休符を印刷します。MusicXML でも、各声部に完全な休符が書かれます。
- 音符の長さはドラム譜の慣習に従って推定します。音は同じ声部の次の音または拍の終わりまで続き、最長で 4 分音符です。MIDI 上の音の長さは表現しません。
- 同じ位置・同じ符頭に割り当てられた異なる MIDI ノートは、譜面上では区別できません（例：GM の 38 と 40 はどちらもスネアとして印刷されます）。同時に現れた場合は注意を出します。
- タイトルなどの文字は、Noto Sans CJK JP が表示できる文字でなければなりません。絵文字などの欠字はエラー（終了コード 2）になります。字形が同じ 2 つの文字（〜 と ～ など）を
  同じ字重で印刷する場合もエラーになります。コピーした結果が区別できないためです。1 ページ目の曲名は太字、それ以外の文字（2 ページ目以降のヘッダーの曲名を含む）は標準の字重なので、
  衝突するのは同じ字重の中で混在させた場合だけです。

## 新しい曲を追加する

1. 安定した ASCII の slug を決め、`scores/<slug>/` を作ります。
2. **元の** MIDI をそのまま `scores/<slug>/source.mid` として置き、以後は変更しません。
3. [templates/metadata.yaml](templates/metadata.yaml) を `scores/<slug>/metadata.yaml` にコピーし、クレジット、ドラムマップ、弱起などを記入します。
   フィールドは [docs/metadata.md](docs/metadata.md) を参照してください。
4. `python3 scripts/build_score.py scores/<slug>/source.mid --metadata scores/<slug>/metadata.yaml --out-dir build/<slug>` を実行し、
   エラーと注意に従ってメタデータを修正します（未割り当てのノートは `note_map` に書き、マルチトラックなら `midi.tracks` などを書きます）。
5. PDF を画像に描画して 1 ページずつ確認し（例：`pdftoppm -r 100 -png build/<slug>/score.pdf build/<slug>/page`）、
   問題がなければ `score.musicxml` と `score.pdf` を `scores/<slug>/` にコピーします。
6. `scores/<slug>/README.md` を書きます：出典、派生ファイル、生成方法、採譜の説明、著作権の説明。

## サンプル曲

[命に嫌われている。](scores/inochi-ni-kirawareteiru/README.md)：作詞・作曲：カンザキイオリ　歌：カンザキイオリ（セルフカバー）、
『不器用な男』収録。ドラム採譜・編曲：音宮。採譜者による再構成と創作を含みます。これはファンによる採譜であり、公式の楽譜では**ありません**。

## ステップごとのスクリプト

日常的には `build_score.py` だけで十分です。問題を調べるときは、各ステップを個別に実行できます。変換スクリプトと検証スクリプトはどれも `--drum-map`、`--repeats`、`--beam-eighths` を受け付けます。`--track` と `--channel` を
受け付けるのは `midi_to_musicxml.py`、`render_score.py`、`validate_score.py`、`build_score.py` だけです（`midi_to_musixtex.py` はメタデータでのみトラックを選びます）。`--system-spacing` は PDF 用の `midi_to_musixtex.py`、`render_score.py`、`build_score.py` だけが受け付けます。
`midi_to_musicxml.py`、`render_score.py`、`midi_to_musixtex.py` は変換だけを行い、終了コードは 0 または 2 です。`validate_score.py` の終了コードは上の表と同じで、
入力ファイルが見つからない場合も 2 を返します。`retag_gm_channel10.py` は `source --out` だけを受け付け、エラー時は Python の例外がそのまま出て、上の 0/1/2 の区別はありません。

```bash
python3 scripts/midi_to_musicxml.py MIDI --metadata META --out OUT.musicxml
python3 scripts/render_score.py MIDI --metadata META --out OUT.pdf [--legend|--no-legend] [--system-spacing SCALE] [--keep-tex OUT.tex] [--work-dir DIR]
python3 scripts/validate_score.py MIDI --metadata META --musicxml OUT.musicxml --pdf OUT.pdf [--xsd XSD]
python3 scripts/midi_to_musixtex.py MIDI --metadata META --out OUT.tex [--system-spacing SCALE]  # MusiXTeX ソースだけを見る
python3 scripts/retag_gm_channel10.py source.mid --out build/gm-channel10.mid  # チャンネル 10 しか認識しないソフト向け
python3 -m pytest -q tests
```

テスト用の任意の環境変数：`MUSICXML_XSD` が `musicxml.xsd` を指していれば XSD 検証のテストを実行します。`PDFJS_TEXT` が pdf.js の文字抽出スクリプト
（`node スクリプト ファイル.pdf` でページごとに `--- page N` を出力し、続けてそのページの文字断片を `|` でつないで出力するもの）を指しており、`node` もある場合は、pdf.js でコピーした文字も追加で照合します。
未設定の場合はこれらのテストをスキップします。TeX 環境がない場合は PDF のテストをスキップします。

## ライセンスと著作権

- このリポジトリの**オリジナルのコードとドキュメント**は MIT ライセンスで公開しています（`LICENSE` を参照）。
- MIT ライセンスは `scores/` ディレクトリには**適用されず**、第三者の音楽作品（楽曲、編曲、歌詞、録音、およびリポジトリ内の MIDI、
  MusicXML、PDF の楽譜）にも適用されません。これらの著作権と頒布権はそれぞれの権利者に帰属します。
- 採譜することや出典を明記することは、頒布の許諾を得たことにはなりません。権利者の許可を得ずに、著作権で保護された楽譜を公開しないでください。
  このリポジトリは、どの楽譜にも再頒布の許可があるとは仮定していません。
