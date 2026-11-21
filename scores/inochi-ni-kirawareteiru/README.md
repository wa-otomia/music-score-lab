[日本語](README.md) | [简体中文](README.zh-CN.md) | [English](README.en.md)

# 命に嫌われている。 ドラム譜

| 項目 | 内容 |
| --- | --- |
| 曲名 | 命に嫌われている。 |
| クレジット | 作詞・作曲：カンザキイオリ　歌：カンザキイオリ（セルフカバー） |
| 収録アルバム | 『不器用な男』 |
| ドラム採譜・編曲 | 音宮（譜面には「ドラム採譜・編曲：音宮」と印字） |
| テンポ / 拍子 | BPM 200。冒頭の 2 拍分の空白は 2/4 の弱起小節として印字し、その後は 4/4 |

本譜には採譜者による再構成・創作を含みます。

## ファイルと出典

| ファイル | 出典 |
| --- | --- |
| `source.mid` | 提供された元の MIDI：FL Studio の FPC から直接書き出したもので、ノートは 1 チャンネル、トラック名は `FPC 1`、冒頭に 4 拍分の空白があります。**変更しないでください** |
| `gm-channel10.mid` | 派生ファイル：`source.mid` を GM の 10 チャンネルに変更したもので、ノートのタイミングは同じです。10 チャンネルしか認識しないソフト向けです。変換自体には不要です |
| `metadata.yaml` | クレジットと変換設定：`drum_map: fpc-default`、`source_leading_beats: 4`、`pickup_beats: 2`、16 分音符グリッド |
| `score.musicxml` | `source.mid` から生成した、編集可能な MusicXML 4.0 |
| `score.pdf` | `source.mid` から生成し、目視で確認した A4 印刷用のドラム譜 |

`gm-channel10.mid` の生成コマンド：

```bash
python3 scripts/retag_gm_channel10.py scores/inochi-ni-kirawareteiru/source.mid \
  --out scores/inochi-ni-kirawareteiru/gm-channel10.mid
```

## 再生成

リポジトリのルートで実行します。

```bash
python3 scripts/build_score.py scores/inochi-ni-kirawareteiru/source.mid \
  --metadata scores/inochi-ni-kirawareteiru/metadata.yaml \
  --out-dir build/inochi
```

`gm-channel10.mid` を入力にしても同じ結果になります（どちらもノートを含むトラックは 1 つだけで、自動的に選ばれます）。
終了コードが 0 であることを確認し、`build/inochi/score.pdf` を全ページ目視で確認してから、`score.musicxml` と `score.pdf` をこのディレクトリにコピーしてください。

## 注意事項

- これは**愛好者による採譜**であり、公式の楽譜でも、出版社が許諾した楽譜でもありません。譜面には採譜者による再創作が含まれ、元の録音と 1 音ずつ一致することは保証しません。
- 譜面はプログラムが MIDI から自動で組版しています。装飾音や重複トリガーの統合などは記譜上の推定であり、MIDI と 1 音ずつ等価であることを意味しません。

## 著作権

楽曲の著作権およびその関連権利は、それぞれの権利者に帰属します。このリポジトリの MIT ライセンスは、このディレクトリには適用されません。
クレジットや編曲の記載は、頒布の許諾を**意味しません**。権利者の許可なく、この譜面を公開しないでください。
