# 命に嫌われている。 ドラム譜

| 项目 | 内容 |
| --- | --- |
| 曲名 | 命に嫌われている。 |
| 署名 | 作詞・作曲：カンザキイオリ　歌：カンザキイオリ（セルフカバー） |
| 收录专辑 | 『不器用な男』 |
| 鼓谱采谱与编曲 | 音宮（谱面印作「ドラム採譜・編曲：音宮」） |
| 速度 / 拍号 | BPM 200；开头 2 拍空白印成 2/4 弱起小节，之后为 4/4 |

本譜には採譜者による再構成・創作を含みます。（本谱含采谱者的重构与创作。）

## 文件与来源

| 文件 | 来源 |
| --- | --- |
| `source.mid` | 用户提供的原始 MIDI：FL Studio 中 FPC 直接导出，音符在第 1 通道，轨道名 `FPC 1`，开头有 4 拍空白。**不可修改** |
| `gm-channel10.mid` | 派生文件：由 `source.mid` 改为 GM 第 10 通道，音符时间不变，供只认第 10 通道的软件使用。转换本身不需要它 |
| `metadata.yaml` | 署名与转换设置：`drum_map: fpc-default`、`source_leading_beats: 4`、`pickup_beats: 2`、16 分网格 |
| `score.musicxml` | 由 `source.mid` 生成的可编辑 MusicXML 4.0 |
| `score.pdf` | 由 `source.mid` 生成并经人工检查的 A4 打印鼓谱 |

`gm-channel10.mid` 的生成命令：

```bash
python3 scripts/retag_gm_channel10.py scores/inochi-ni-kirawareteiru/source.mid \
  --out scores/inochi-ni-kirawareteiru/gm-channel10.mid
```

## 重新生成

在仓库根目录运行：

```bash
python3 scripts/build_score.py scores/inochi-ni-kirawareteiru/source.mid \
  --metadata scores/inochi-ni-kirawareteiru/metadata.yaml \
  --out-dir build/inochi
```

用 `gm-channel10.mid` 作输入得到的结果相同（两者都只有一个含音符的轨道，会被自动选中）。
确认退出码为 0、逐页检查 `build/inochi/score.pdf` 之后，再把 `score.musicxml` 和 `score.pdf` 复制到本目录。

## 说明

- 这是**爱好者采谱**，不是官方乐谱，也不是出版社授权的乐谱。谱面内容含采谱者的再创作，不保证与原录音逐音一致。
- 谱面由程序从 MIDI 自动排版；装饰音、重复触发的合并等属于记谱上的推断，不代表与 MIDI 逐音等价。

## 版权

歌曲的著作权及相关权利属于各自的权利人。本仓库的 MIT 许可证不适用于本目录。
署名和编曲说明**不等于**发行授权：未取得权利人许可，不要公开发布本谱。
