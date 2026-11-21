"""鼓 MIDI → 记谱模型（MusicXML 与 MusiXTeX 两个输出器共用）。

处理流程：

1. 读取 MIDI，按轨道/通道选出鼓声部。不要求 GM 第 10 通道：FL Studio 的 FPC
   默认导出在第 1 通道、轨道名形如 ``FPC 1``。
2. 用鼓映射（``configs/drum-maps/*.yaml`` + 元数据 ``note_map``）把 MIDI 音符换成乐器
   （谱表位置、符头、手/脚声部）。映射里没有的音符直接报错，不猜。
3. 识别装饰音（同一音高紧贴在主音前的弱音）与重复触发。
4. 逐拍量化：每一拍在「直拍网格」（16 分或 8 分）与「三连音网格」中选误差明显更小者；
   两者都对不上（32 分音符、五连音、未量化的演奏）时报错并指出位置，不静默丢音。
5. 按 MIDI 拍号（或元数据覆盖）切小节：支持 1/4–12/4 以及小节线上的拍号变化，
   支持带音符的弱起小节。
6. 为每个声部推导时值、休止和横梁层级。两个输出器只翻译这里的结果，不各自推断节奏。

内部时间单位固定为每四分音符 ``R`` = 48 刻度，与源文件 ticks_per_beat 无关。
"""
from __future__ import annotations

import bisect
import math
import re
from collections import defaultdict
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path
from typing import Any

import mido
import yaml

R = 48  # internal ticks per quarter note; divisible by 2, 3, 4, 6, 8, 12, 16, 24

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / 'configs'
INSTRUMENTS_FILE = CONFIG_DIR / 'instruments.yaml'
DRUM_MAP_DIR = CONFIG_DIR / 'drum-maps'
DEFAULT_DRUM_MAP = 'gm'

HEADS = ('normal', 'x', 'circle-x', 'diamond', 'triangle', 'plus', 'rhombus')
MARKS = (None, 'open', 'half-open', 'closed')
# MusiXTeX pitch letters on a treble-clef staff: c = C4 (one ledger line below),
# e = bottom line, m = top line, n = space above, o = first ledger line above.
STAFF_LETTERS = 'abcdefghijklmnopqrs'


class ScoreError(ValueError):
    """The input cannot be engraved faithfully; the message says what to change."""


# --------------------------------------------------------------------------- config

@dataclass(frozen=True)
class Instrument:
    id: str
    name: str
    name_ja: str
    abbr: str
    part: str      # 'hand' (up stems, voice 1) or 'foot' (down stems, voice 2)
    staff: str     # MusiXTeX pitch letter, e.g. 'j' = third space (snare)
    head: str      # see HEADS
    mark: str | None = None  # open / half-open / closed ornament above the note


@dataclass(frozen=True)
class DrumMap:
    name: str
    notes: dict[int, Instrument]
    sources: tuple[str, ...]


INSTRUMENT_FIELDS = ('name', 'name_ja', 'abbr', 'part', 'staff', 'head', 'mark')


def read_yaml(path: Path) -> dict:
    try:
        value = yaml.safe_load(Path(path).read_text(encoding='utf-8'))
    except FileNotFoundError:
        raise ScoreError(f'找不到文件：{path}') from None
    except yaml.YAMLError as exc:
        raise ScoreError(f'YAML 语法错误：{path}：{exc}') from None
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ScoreError(f'YAML 顶层必须是映射：{path}')
    return value


def make_instrument(ident: str, spec: dict, where: str, base: Instrument | None = None) -> Instrument:
    if not isinstance(spec, dict):
        raise ScoreError(f'{where}: 乐器定义必须是映射')
    unknown = set(spec) - set(INSTRUMENT_FIELDS) - {'as', 'id'}
    if unknown:
        raise ScoreError(f'{where}: 未知字段 {sorted(unknown)}；允许 {", ".join(INSTRUMENT_FIELDS)}')
    values: dict[str, Any] = {k: getattr(base, k) for k in INSTRUMENT_FIELDS} if base else {}
    values.update({k: v for k, v in spec.items() if k in INSTRUMENT_FIELDS})
    for req in ('name', 'part', 'staff', 'head'):
        if not values.get(req):
            raise ScoreError(f'{where}: 缺少必填字段 {req}')
    values.setdefault('name_ja', values['name'])
    values.setdefault('abbr', str(values['name'])[:3])
    values.setdefault('mark', None)
    if values['part'] not in ('hand', 'foot'):
        raise ScoreError(f'{where}: part 只能是 hand 或 foot')
    if values['head'] not in HEADS:
        raise ScoreError(f'{where}: head 只能是 {", ".join(HEADS)}')
    if values['mark'] not in MARKS:
        raise ScoreError(f'{where}: mark 只能是 open、half-open、closed 或留空')
    staff = values['staff']
    if not (isinstance(staff, str) and len(staff) == 1 and staff in STAFF_LETTERS):
        raise ScoreError(f'{where}: staff 必须是 {STAFF_LETTERS[0]}–{STAFF_LETTERS[-1]} 中的一个字母')
    if not re.fullmatch(r'[A-Za-z0-9.+-]{1,4}', str(values['abbr'])):
        raise ScoreError(f'{where}: abbr 只能用 1–4 个 ASCII 字母/数字（谱面图例用）')
    return Instrument(ident, *(values[k] if k != 'name_ja' else str(values[k]) for k in INSTRUMENT_FIELDS))


def load_instruments(path: Path = INSTRUMENTS_FILE) -> dict[str, Instrument]:
    return {key: make_instrument(key, spec, f'{path}: {key}') for key, spec in read_yaml(path).items()}


def _note_number(key: Any, where: str) -> int:
    try:
        note = int(key)
    except (TypeError, ValueError):
        raise ScoreError(f'{where}: MIDI 音符号必须是 0–127 的整数，得到 {key!r}') from None
    if not 0 <= note <= 127:
        raise ScoreError(f'{where}: MIDI 音符号必须在 0–127 之间，得到 {note}')
    return note


def bundled_maps() -> list[str]:
    return sorted(p.stem for p in DRUM_MAP_DIR.glob('*.yaml'))


def resolve_map_path(ref: str | Path, relative_to: Path | None = None) -> Path:
    """A drum-map reference is a bundled name (``gm``, ``fpc-default``) or a YAML path."""
    text = str(ref)
    if re.fullmatch(r'[A-Za-z0-9_-]+', text) and (DRUM_MAP_DIR / f'{text}.yaml').exists():
        return DRUM_MAP_DIR / f'{text}.yaml'
    path = Path(text).expanduser()
    if not path.is_absolute() and relative_to is not None and (relative_to / path).exists():
        path = relative_to / path
    if not path.exists():
        raise ScoreError(f'找不到鼓映射 {text!r}；内置映射有：{", ".join(bundled_maps())}，或给出 YAML 文件路径')
    return path


def instrument_from_spec(spec: Any, instruments: dict[str, Instrument], where: str, note: int) -> Instrument:
    """``spec`` is an instrument id, ``{as: id, <overrides>}`` or a full inline definition."""
    if isinstance(spec, str):
        if spec not in instruments:
            raise ScoreError(f'{where}: 未知乐器 {spec!r}；可用乐器 ID 见 configs/instruments.yaml')
        return instruments[spec]
    if isinstance(spec, dict) and 'as' in spec:
        base_id = spec['as']
        if base_id not in instruments:
            raise ScoreError(f'{where}: 未知乐器 {base_id!r}；可用乐器 ID 见 configs/instruments.yaml')
        overrides = {k: v for k, v in spec.items() if k != 'as'}
        ident = base_id if not overrides else f'{base_id}@{note}'
        return make_instrument(ident, overrides, where, instruments[base_id])
    if isinstance(spec, dict):
        return make_instrument(str(spec.get('id') or f'note-{note}'), spec, where)
    raise ScoreError(f'{where}: 乐器必须写成乐器 ID 或映射')


def load_drum_map(ref: str | Path, instruments: dict[str, Instrument] | None = None,
                  relative_to: Path | None = None, _seen: tuple[Path, ...] = ()) -> DrumMap:
    """Load a drum map; a map may ``extends`` another one and override single notes."""
    instruments = instruments if instruments is not None else load_instruments()
    path = resolve_map_path(ref, relative_to).resolve()
    if path in _seen:
        raise ScoreError('鼓映射循环继承：' + ' → '.join(str(p) for p in (*_seen, path)))
    raw = read_yaml(path)
    unknown = set(raw) - {'name', 'description', 'extends', 'notes'}
    if unknown:
        raise ScoreError(f'{path}: 未知字段 {sorted(unknown)}（允许 name、description、extends、notes）')
    notes: dict[int, Instrument] = {}
    sources: tuple[str, ...] = ()
    if raw.get('extends'):
        parent = load_drum_map(raw['extends'], instruments, path.parent, (*_seen, path))
        notes.update(parent.notes)
        sources = parent.sources
    for key, spec in (raw.get('notes') or {}).items():
        note = _note_number(key, str(path))
        notes[note] = instrument_from_spec(spec, instruments, f'{path}: 音符 {note}', note)
    return DrumMap(str(raw.get('name') or path.stem), notes, (*sources, str(path)))


# --------------------------------------------------------------------------- metadata

TEXT_FIELDS = ('title', 'subtitle', 'artist', 'album', 'composer', 'lyricist', 'arranger',
               'vocal', 'transcriber', 'note', 'copyright')
METADATA_KEYS = set(TEXT_FIELDS) | {
    'slug', 'drum_map', 'note_map', 'midi', 'quantize', 'time_signature', 'tempo_bpm',
    'pickup_beats', 'source_leading_beats', 'dynamics', 'legend', 'credits',
    # legacy keys kept for older metadata files
    'beats', 'beat_type', 'quantize_divisions_per_beat'}


@dataclass
class Settings:
    drum_map: str | Path = DEFAULT_DRUM_MAP
    note_map: dict = field(default_factory=dict)
    tracks: list | None = None      # track-name substrings (case-insensitive) or 0-based indices
    channels: list | None = None    # 1-based MIDI channels
    subdivision: int = 4            # straight grid per quarter: 2 (8ths) or 4 (16ths)
    tuplets: str = 'auto'           # auto | off
    time_signature: tuple[int, int] | None = None
    tempo_bpm: float | None = None
    source_leading_beats: Fraction = Fraction(0)
    pickup_beats: Fraction = Fraction(0)
    ghost_velocity: int | None = None
    accent_velocity: int | None = None
    flam_window: Fraction = Fraction(1, 8)   # in quarter notes; weaker hit this close before a stroke = grace


def _fraction(value: Any, where: str) -> Fraction:
    try:
        return Fraction(str(value))
    except (ValueError, ZeroDivisionError):
        raise ScoreError(f'元数据 {where} 必须是数字，得到 {value!r}') from None


def _as_list(value: Any) -> list | None:
    if value is None:
        return None
    return list(value) if isinstance(value, (list, tuple)) else [value]


def parse_settings(meta: dict, cli: dict | None = None) -> Settings:
    cli = cli or {}
    unknown = set(meta) - METADATA_KEYS
    if unknown:
        raise ScoreError(f'元数据含未知字段 {sorted(unknown)}；字段说明见 docs/metadata.md')
    s = Settings()
    midi = meta.get('midi') or {}
    if not isinstance(midi, dict):
        raise ScoreError('元数据 midi 必须是映射（tracks / channels）')
    s.tracks = _as_list(cli.get('tracks') or midi.get('tracks'))
    channels = _as_list(cli.get('channels') or midi.get('channels'))
    if channels is not None:
        try:
            s.channels = [int(c) for c in channels]
        except (TypeError, ValueError):
            raise ScoreError('midi.channels 必须是 1–16 的整数') from None
        if any(not 1 <= c <= 16 for c in s.channels):
            raise ScoreError('MIDI 通道按 1–16 编号（GM 鼓是 10，FPC 默认导出是 1）')
    s.drum_map = cli.get('drum_map') or meta.get('drum_map') or DEFAULT_DRUM_MAP
    s.note_map = meta.get('note_map') or {}
    if not isinstance(s.note_map, dict):
        raise ScoreError('元数据 note_map 必须是「MIDI 音符号: 乐器」的映射')
    quant = meta.get('quantize') or {}
    if not isinstance(quant, dict):
        raise ScoreError('元数据 quantize 必须是映射')
    s.subdivision = _int(quant.get('subdivision', meta.get('quantize_divisions_per_beat', 4)), 'quantize.subdivision')
    if s.subdivision not in (2, 4):
        raise ScoreError('quantize.subdivision 只支持 4（16 分）或 2（8 分）')
    s.tuplets = str(quant.get('tuplets', 'auto'))
    if s.tuplets not in ('auto', 'off'):
        raise ScoreError('quantize.tuplets 只支持 auto 或 off')
    if 'flam_window' in quant:
        s.flam_window = _fraction(quant['flam_window'], 'quantize.flam_window')
    ts = meta.get('time_signature')
    if ts is None and ('beats' in meta or 'beat_type' in meta):
        ts = f"{meta.get('beats', 4)}/{meta.get('beat_type', 4)}"
    if ts is not None:
        m = re.fullmatch(r'\s*(\d+)\s*/\s*(\d+)\s*', str(ts))
        if not m:
            raise ScoreError(f'time_signature 写法应为 "4/4"，得到 {ts!r}')
        s.time_signature = (int(m.group(1)), int(m.group(2)))
    if meta.get('tempo_bpm') is not None:
        s.tempo_bpm = float(_fraction(meta['tempo_bpm'], 'tempo_bpm'))
        if not 10 <= s.tempo_bpm <= 400:
            raise ScoreError('tempo_bpm 应在 10–400 之间')
    s.pickup_beats = _fraction(meta.get('pickup_beats', 0), 'pickup_beats')
    s.source_leading_beats = _fraction(meta.get('source_leading_beats', s.pickup_beats), 'source_leading_beats')
    if s.pickup_beats < 0 or s.source_leading_beats < s.pickup_beats:
        raise ScoreError('要求 0 ≤ pickup_beats ≤ source_leading_beats')
    if s.pickup_beats.denominator != 1 or s.source_leading_beats.denominator != 1:
        raise ScoreError('pickup_beats 与 source_leading_beats 必须是整数拍（四分音符）')
    dyn = meta.get('dynamics') or {}
    if not isinstance(dyn, dict):
        raise ScoreError('元数据 dynamics 必须是映射（ghost_below / accent_above）')
    for key, attr in (('ghost_below', 'ghost_velocity'), ('accent_above', 'accent_velocity')):
        if dyn.get(key) is not None:
            value = _int(dyn[key], f'dynamics.{key}')
            if not 1 <= value <= 127:
                raise ScoreError(f'dynamics.{key} 必须在 1–127 之间')
            setattr(s, attr, value)
    for key in ('credits',):
        if meta.get(key) is not None and not isinstance(meta[key], dict):
            raise ScoreError(f'元数据 {key} 必须是映射')
    for key in TEXT_FIELDS:
        if meta.get(key) is not None and not isinstance(meta[key], (str, int, float)):
            raise ScoreError(f'元数据 {key} 必须是文字')
    return s


def _int(value: Any, where: str) -> int:
    fraction = _fraction(value, where)
    if fraction.denominator != 1:
        raise ScoreError(f'元数据 {where} 必须是整数，得到 {value!r}')
    return int(fraction)


# --------------------------------------------------------------------------- MIDI input

@dataclass
class SourceHit:
    tick: int
    note: int
    velocity: int
    track: int
    channel: int  # 1-based


@dataclass
class MidiData:
    tpq: int
    hits: list[SourceHit]
    tempos: list[tuple[int, float]]              # (tick, bpm)
    time_signatures: list[tuple[int, int, int]]  # (tick, numerator, denominator)
    groups: dict[tuple[int, int], dict]          # (track, channel) -> {name, count, notes}
    selected: list[tuple[int, int]]
    selection_reason: str


DRUM_TRACK_NAME = re.compile(r'fpc|drum|perc|kit|ドラム|鼓', re.I)


def decode_name(raw: str) -> str:
    """mido decodes meta text as latin-1; DAWs write UTF-8 (FL Studio) or Shift-JIS."""
    try:
        data = raw.encode('latin-1')
    except UnicodeEncodeError:
        return raw
    for codec in ('utf-8', 'cp932'):
        try:
            return data.decode(codec)
        except UnicodeDecodeError:
            continue
    return raw


def read_midi(path: Path, settings: Settings) -> MidiData:
    try:
        midi = mido.MidiFile(path)
    except (OSError, EOFError, ValueError, KeyError) as exc:
        raise ScoreError(f'无法读取 MIDI 文件 {path}：{exc}') from None
    if midi.type == 2:
        raise ScoreError('不支持 SMF type 2（多个独立序列）的 MIDI 文件')
    tpq = midi.ticks_per_beat
    hits: list[SourceHit] = []
    tempos: list[tuple[int, float]] = []
    sigs: list[tuple[int, int, int]] = []
    groups: dict[tuple[int, int], dict] = {}
    for index, track in enumerate(midi.tracks):
        tick = 0
        name = ''
        for msg in track:
            tick += msg.time
            if msg.type == 'track_name' and not name:
                name = decode_name(msg.name)
            elif msg.type == 'set_tempo':
                tempos.append((tick, round(mido.tempo2bpm(msg.tempo), 3)))
            elif msg.type == 'time_signature':
                sigs.append((tick, msg.numerator, msg.denominator))
            elif msg.type == 'note_on' and msg.velocity > 0:
                hit = SourceHit(tick, msg.note, msg.velocity, index, msg.channel + 1)
                hits.append(hit)
                group = groups.setdefault((index, hit.channel), {'name': '', 'count': 0, 'notes': set()})
                group['count'] += 1
                group['notes'].add(msg.note)
        for (t, _ch), group in groups.items():
            if t == index:
                group['name'] = name
    if not hits:
        raise ScoreError('MIDI 中没有任何 note-on 事件')
    selected, reason = select_groups(groups, settings)
    keep = set(selected)
    hits = sorted((h for h in hits if (h.track, h.channel) in keep), key=lambda h: (h.tick, h.note))
    # keep the last event when several share a tick
    tempos = sorted({t: b for t, b in sorted(tempos, key=lambda e: e[0])}.items())
    sigs = sorted({t: (t, n, d) for t, n, d in sorted(sigs, key=lambda e: e[0])}.values())
    return MidiData(tpq, hits, tempos, sigs, groups, selected, reason)


def describe_groups(groups: dict) -> str:
    return '；'.join(f'轨道 {t}「{g["name"] or "无名"}」通道 {c}：{g["count"]} 个音'
                    for (t, c), g in sorted(groups.items()))


def select_groups(groups: dict, settings: Settings) -> tuple[list[tuple[int, int]], str]:
    keys = sorted(groups)
    if settings.tracks is not None or settings.channels is not None:
        chosen = []
        for key in keys:
            track, channel = key
            name = groups[key]['name'] or ''
            if settings.channels is not None and channel not in settings.channels:
                continue
            if settings.tracks is not None and not any(
                    (isinstance(sel, int) and sel == track) or
                    (isinstance(sel, str) and sel.lower() in name.lower()) for sel in settings.tracks):
                continue
            chosen.append(key)
        if not chosen:
            raise ScoreError(f'按指定的 tracks/channels 没有选中任何音符。文件中有：{describe_groups(groups)}')
        return chosen, '按元数据/命令行指定'
    if len(keys) == 1:
        return keys, '文件只有一个含音符的轨道/通道'
    ch10 = [k for k in keys if k[1] == 10]
    if ch10:
        return ch10, 'GM 打击乐通道 10'
    named = [k for k in keys if DRUM_TRACK_NAME.search(groups[k]['name'] or '')]
    if named:
        return named, '轨道名像鼓轨（FPC/Drum/Perc/Kit）'
    raise ScoreError('MIDI 含多个轨道/通道，无法判断哪一个是鼓。请在元数据 midi.tracks 或 midi.channels '
                     f'中指定（或用命令行 --track/--channel）。文件中有：{describe_groups(groups)}')


# --------------------------------------------------------------------------- model

@dataclass
class Hit:
    note: int
    inst: Instrument
    velocity: int
    grace: bool = False
    ghost: bool = False
    accent: bool = False


@dataclass
class Bar:
    index: int                 # 0-based position in the score
    number: int                # printed measure number (0 for a pickup bar)
    beats: int                 # quarter-note beats in this bar
    beat_type: int
    start: int                 # absolute R ticks from score start
    pickup: bool = False
    events: dict[int, dict[int, Hit]] = field(default_factory=dict)  # tick in bar -> note -> hit
    triplet_beats: dict[int, int] = field(default_factory=dict)      # beat index -> 3 or 6
    show_meter: bool = False
    tempo: float | None = None

    @property
    def length(self) -> int:
        return self.beats * R


@dataclass
class Transcription:
    bars: list[Bar]
    drum_map: DrumMap
    metadata: dict
    settings: Settings
    source_hits: int
    grace_hits: int
    duplicate_hits: int
    triplet_beat_count: int
    tempo_bpm: float
    midi: MidiData
    warnings: list[str] = field(default_factory=list)

    @property
    def mapping(self) -> dict[int, Instrument]:
        return self.drum_map.notes

    def instruments_used(self) -> list[tuple[int, Instrument]]:
        seen: dict[int, Instrument] = {}
        for bar in self.bars:
            for hits in bar.events.values():
                for note, hit in hits.items():
                    seen.setdefault(note, hit.inst)
        return sorted(seen.items(), key=lambda item: (-STAFF_LETTERS.index(item[1].staff), item[0]))

    @property
    def engraved_hits(self) -> int:
        return sum(len(h) for bar in self.bars for h in bar.events.values())

    def summary(self) -> str:
        parts = [f'{len(self.bars)} 小节', f'记谱 {self.engraved_hits} 个音', f'源 MIDI {self.source_hits} 次击打',
                 f'装饰音 {self.grace_hits}', f'合并重复 {self.duplicate_hits}',
                 f'三连音拍 {self.triplet_beat_count}', f'选轨：{self.midi.selection_reason}']
        return '，'.join(parts)


def build_score(midi_file: Path, metadata_file: Path | None = None, drum_map: str | Path | None = None,
                *, metadata: dict | None = None, cli: dict | None = None) -> Transcription:
    meta = dict(metadata) if metadata is not None else (read_yaml(metadata_file) if metadata_file else {})
    cli = dict(cli or {})
    if drum_map is not None:
        cli['drum_map'] = drum_map
    settings = parse_settings(meta, cli)
    base_dir = Path(metadata_file).parent if metadata_file else Path.cwd()
    instruments = load_instruments()
    dmap = load_drum_map(settings.drum_map, instruments, base_dir)
    if settings.note_map:
        notes = dict(dmap.notes)
        for key, spec in settings.note_map.items():
            note = _note_number(key, 'note_map')
            notes[note] = instrument_from_spec(spec, instruments, f'note_map 音符 {note}', note)
        dmap = DrumMap(dmap.name + ' + note_map', notes, dmap.sources)
    data = read_midi(Path(midi_file), settings)
    missing = sorted({h.note for h in data.hits} - set(dmap.notes))
    if missing:
        raise ScoreError(f'鼓映射「{dmap.name}」中没有这些 MIDI 音符：{missing}。请在元数据 note_map 中指定，'
                         '例如 note_map: {39: hand-clap}；可用乐器 ID 见 configs/instruments.yaml')
    return transcribe(data, dmap, meta, settings)


def transcribe(data: MidiData, dmap: DrumMap, meta: dict, s: Settings) -> Transcription:
    tpq = data.tpq
    warnings: list[str] = []
    shift = (s.source_leading_beats - s.pickup_beats) * tpq  # source ticks dropped before the score

    # 1. duplicates and graces, per pitch, on raw timing
    by_pitch: dict[int, list[SourceHit]] = defaultdict(list)
    for hit in data.hits:
        by_pitch[hit.note].append(hit)
    window = s.flam_window * tpq
    same_time = Fraction(tpq, 48)  # hits closer than this are one stroke triggered twice
    main_hits: list[tuple[SourceHit, list[SourceHit]]] = []  # (main stroke, its graces)
    grace_count = duplicate_count = 0
    for hs in by_pitch.values():
        hs.sort(key=lambda h: h.tick)
        strokes: list[SourceHit] = []
        cluster: list[SourceHit] = []
        for h in hs + [None]:
            if h is not None and cluster and h.tick - cluster[0].tick <= same_time:
                cluster.append(h)
                continue
            if cluster:
                duplicate_count += len(cluster) - 1
                strokes.append(max(cluster, key=lambda x: (x.velocity, -x.tick)))  # ties: earlier hit
            cluster = [h] if h is not None else []
        # A softer stroke shortly before a louder one is its grace note (flam; two = drag).
        main_of: list[int | None] = [None] * len(strokes)
        for i in range(len(strokes) - 2, -1, -1):
            target = main_of[i + 1] if main_of[i + 1] is not None else i + 1
            if (strokes[target].tick - strokes[i].tick <= window
                    and strokes[i].velocity < strokes[target].velocity):
                main_of[i] = target
        graces: dict[int, list[SourceHit]] = defaultdict(list)
        for i, m in enumerate(main_of):
            if m is not None:
                graces[m].append(strokes[i])
        for m, gs in list(graces.items()):
            if len(gs) > 2:  # a run of rising strokes is not ornamentation: keep every hit
                for i, target in enumerate(main_of):
                    if target == m:
                        main_of[i] = None
                del graces[m]
        for i, stroke in enumerate(strokes):
            if main_of[i] is None:
                grace_count += len(graces.get(i, []))
                main_hits.append((stroke, graces.get(i, [])))

    # 2. per-beat grid choice; positions in quarter beats relative to score start
    triplet_div = 6 if s.subdivision == 4 else 3
    beats_of: dict[int, list[tuple[list[Fraction], SourceHit, bool]]] = defaultdict(list)
    for hit, gs in main_hits:
        main_pos = (Fraction(hit.tick) - shift) / tpq
        beat = math.floor(Fraction(round(main_pos * 12), 12))
        cands = [main_pos] + [(Fraction(g.tick) - shift) / tpq for g in gs]
        beats_of[beat].append((cands, hit, bool(gs)))

    def place(cands: list[Fraction], div: int, beat: int) -> tuple[Fraction, Fraction]:
        """(error, grid position) using the main stroke or, for a flam whose main stroke is
        off the grid, the grace — but only positions that stay inside this beat."""
        best = None
        for p in cands:
            q = Fraction(round(p * div), div)
            if not beat <= q < beat + 1 and not (q == beat + 1 and p is cands[0]):
                continue
            option = (abs(p - q), q)
            if best is None or option[0] < best[0]:
                best = option
        return best if best is not None else (Fraction(1), Fraction(round(cands[0] * div), div))

    quantized: dict[int, dict[int, Hit]] = defaultdict(dict)
    triplet_beats: dict[int, int] = {}
    tol_s, tol_t = Fraction(1, 24), Fraction(1, 32)
    for beat, items in sorted(beats_of.items()):
        if beat < 0:
            raise ScoreError('有音符落在乐谱起点之前：请检查元数据 source_leading_beats / pickup_beats')
        err_s = max(place(c, s.subdivision, beat)[0] for c, _, _ in items)
        err_t = max(place(c, triplet_div, beat)[0] for c, _, _ in items)
        where = f'第 {beat + 1} 拍（从乐谱起点按四分音符计）'
        if err_s <= tol_s:
            div = s.subdivision
        elif s.tuplets == 'auto' and err_t <= tol_t:
            div = triplet_div
        else:
            unit = '16 分' if s.subdivision == 4 else '8 分'
            if s.tuplets == 'off' and err_t <= tol_t:
                reason = '这一拍是三连音，但元数据设置了 quantize.tuplets: off'
            else:
                reason = (f'音符既不在 {unit}网格上，也不在三连音网格上（偏差 {float(min(err_s, err_t)):.3f} 拍）：'
                          '可能是 32 分音符、五连音、同一拍里直拍与三连音混用，或未量化的演奏')
            if s.tuplets == 'off':
                reason += '（当前 quantize.tuplets: off）'
            raise ScoreError(f'{where}无法准确记谱：{reason}。请先在 DAW 中量化，或扩展转换器后再处理。')
        if div != s.subdivision:
            triplet_beats[beat] = div
        for cands, hit, grace in items:
            pos = place(cands, div, beat)[1]
            tick = int(pos * R)
            inst = dmap.notes[hit.note]
            prev = quantized[tick].get(hit.note)
            if prev is not None:
                raise ScoreError(f'{where}：MIDI 音符 {hit.note} 有两次击打量化到同一位置，'
                                 '说明这里的节奏比 16 分音符/三连音更细。请先在 DAW 中量化或删去多余的击打。')
            hand = inst.part == 'hand'
            ghost = hand and s.ghost_velocity is not None and hit.velocity < s.ghost_velocity
            accent = hand and s.accent_velocity is not None and hit.velocity > s.accent_velocity
            quantized[tick][hit.note] = Hit(hit.note, inst, hit.velocity, grace, ghost, accent)
    if duplicate_count:
        warnings.append(f'{duplicate_count} 次几乎同时（相差不到 1/48 拍）的同音高重复触发已合并（保留力度最大者）')

    # 3. bars
    last = max(quantized) if quantized else 0
    bars = make_bars(data, s, shift, last, warnings)
    starts = [b.start for b in bars]
    for tick, hits in quantized.items():
        bar = bars[bisect.bisect_right(starts, tick) - 1]
        offset = tick - bar.start
        if not 0 <= offset < bar.length:
            raise ScoreError(f'内部错误：位置 {tick}/{R} 拍不在任何小节内')
        bar.events[offset] = dict(sorted(hits.items()))
        seen: dict[tuple[str, str], int] = {}
        for note, hit in hits.items():
            key = (hit.inst.part, hit.inst.staff)
            if key in seen:
                other = hits[seen[key]].inst
                same = (other.head, other.mark) == (hit.inst.head, hit.inst.mark)
                warnings.append(f'第 {bar.number} 小节：MIDI 音符 {seen[key]} 与 {note} 同时出现在谱表同一位置'
                                + ('且符头相同，谱面上无法区分' if same else '，符头会重叠')
                                + '；如需区分请在 note_map 中改位置')
            else:
                seen[key] = note
    for beat, div in triplet_beats.items():
        tick = beat * R
        bar = bars[bisect.bisect_right(starts, tick) - 1]
        bar.triplet_beats[(tick - bar.start) // R] = div
    for bar in bars:
        bar.events = dict(sorted(bar.events.items()))

    starting = [bpm for t, bpm in data.tempos if Fraction(t) - shift <= 0]
    midi_tempo = starting[-1] if starting else (data.tempos[0][1] if data.tempos else None)
    tempo = s.tempo_bpm or midi_tempo or 120.0
    if s.tempo_bpm and midi_tempo and abs(midi_tempo - s.tempo_bpm) > 0.5:
        warnings.append(f'元数据 tempo_bpm={s.tempo_bpm:g} 与 MIDI 速度 {midi_tempo:g} 不同，谱面按元数据标注')
    apply_tempo_changes(bars, data, shift, tempo, warnings)
    return Transcription(bars, dmap, meta, s, len(data.hits), grace_count, duplicate_count,
                         len(triplet_beats), tempo, data, warnings)


def make_bars(data: MidiData, s: Settings, shift: Fraction, last_tick: int, warnings: list[str]) -> list[Bar]:
    tpq = data.tpq
    sigs = [(Fraction(t) - shift, n, d) for t, n, d in data.time_signatures]
    if s.time_signature is not None:
        n, d = s.time_signature
        if data.time_signatures:
            first = data.time_signatures[0][1:]
            if tuple(first) != (n, d):
                raise ScoreError(f'元数据拍号 {n}/{d} 与 MIDI 拍号 {first[0]}/{first[1]} 不一致；'
                                 '请改正元数据，或删除 time_signature 以采用 MIDI 拍号')
        else:
            sigs = [(Fraction(-10 ** 9), n, d)]
    if not sigs:
        sigs = [(Fraction(-10 ** 9), 4, 4)]
        warnings.append('MIDI 没有拍号事件，按 4/4 处理（可在元数据 time_signature 中指定）')
    elif data.time_signatures and data.time_signatures[0][0] > 0 and s.time_signature is None:
        sigs.insert(0, (Fraction(-10 ** 9), 4, 4))  # SMF default before the first time-signature event
        warnings.append('MIDI 第一个拍号事件不在开头，之前的部分按 4/4 处理')
    for _, n, d in sigs:
        if d != 4 or not 1 <= n <= 12:
            raise ScoreError(f'暂不支持拍号 {n}/{d}：目前只支持 1/4–12/4（含小节线上的拍号变化）。'
                             '6/8、12/8 等复合拍请在 DAW 中改为 x/4 加三连音，或扩展转换器。')

    def sig_at(pos: Fraction) -> tuple[int, int]:
        current = (sigs[0][1], sigs[0][2])
        for t, n, d in sigs:
            if t <= pos:
                current = (n, d)
        return current

    bars: list[Bar] = []
    pos = Fraction(0)  # source ticks after shift
    end = Fraction(last_tick, R) * tpq
    if s.pickup_beats:
        first_meter = sig_at(s.pickup_beats * tpq)
        if s.pickup_beats >= first_meter[0]:
            raise ScoreError(f'pickup_beats={s.pickup_beats} 不短于第一小节（{first_meter[0]}/{first_meter[1]}），'
                             '弱起小节必须比完整小节短')
        for t, _, _ in sigs:
            if 0 < t < s.pickup_beats * tpq:
                raise ScoreError('MIDI 拍号变化落在弱起小节内部；请检查 pickup_beats / source_leading_beats')
        bars.append(Bar(0, 0, int(s.pickup_beats), 4, 0, pickup=True, show_meter=True))
        pos = s.pickup_beats * tpq
    number = 1
    previous = (bars[-1].beats, 4) if bars else None
    while pos <= end or len(bars) == (1 if s.pickup_beats else 0):
        n, d = sig_at(pos)
        for t, _, _ in sigs:
            if pos < t < pos + n * tpq:
                raise ScoreError(f'MIDI 拍号变化不在小节线上（第 {number} 小节内）；请在 DAW 中修正拍号位置')
        bars.append(Bar(len(bars), number, n, d, int(pos / tpq * R), show_meter=(previous != (n, d))))
        previous = (n, d)
        pos += n * tpq
        number += 1
    return bars


def apply_tempo_changes(bars: list[Bar], data: MidiData, shift: Fraction, initial: float,
                        warnings: list[str] | None = None) -> None:
    current = initial
    bars[0].tempo = initial
    starts = [b.start for b in bars]
    for tick, bpm in data.tempos:
        r = (Fraction(tick) - shift) / data.tpq * R
        if r <= 0 or r >= bars[-1].start + bars[-1].length:
            continue
        bar = bars[bisect.bisect_right(starts, r) - 1]
        if abs(bpm - current) > 0.5:
            if r != bar.start and warnings is not None:
                warnings.append(f'第 {bar.number} 小节中途的速度变化（♩={bpm:g}）标在该小节开头')
            bar.tempo = bpm
            current = bpm


# --------------------------------------------------------------------------- voices, rests, beams

@dataclass
class VoiceItem:
    """A note (chord) or rest in one voice; ``duration`` in R ticks."""
    start: int
    duration: int
    hits: dict[int, Hit] | None   # None = rest
    tuplet: int | None = None      # 3 or 6 inside a triplet beat
    beams: list[tuple[int, str]] = field(default_factory=list)  # [(level, begin|continue|end|forward hook|backward hook)]
    tuplet_edge: str | None = None  # 'start', 'stop' or 'both' for the first/last item of a triplet beat
    tuplet_label: bool = False      # where the tuplet number is printed
    measure_rest: bool = False

    @property
    def is_rest(self) -> bool:
        return self.hits is None


STRAIGHT_VALUES = {R * 4: ('whole', 0), R * 3: ('half', 1), R * 2: ('half', 0), R * 3 // 2: ('quarter', 1),
                   R: ('quarter', 0), R * 3 // 4: ('eighth', 1), R // 2: ('eighth', 0), R // 4: ('16th', 0)}
TRIPLET_VALUES = {R * 2 // 3: ('quarter', 0), R // 2: ('eighth', 1), R // 3: ('eighth', 0), R // 6: ('16th', 0)}


def note_type(item: VoiceItem) -> tuple[str, int]:
    """(MusicXML type name, number of dots) for a note or rest."""
    if item.measure_rest:
        return ('whole', 0)
    table = TRIPLET_VALUES if item.tuplet else STRAIGHT_VALUES
    if item.duration not in table:
        raise ScoreError(f'内部错误：无法记谱的时值 {item.duration}/{R} 拍')
    return table[item.duration]


def beam_level(item: VoiceItem) -> int:
    return {'eighth': 1, '16th': 2}.get(note_type(item)[0], 0)


def voice_hits(bar: Bar, part: str) -> dict[int, dict[int, Hit]]:
    return {t: {n: h for n, h in hs.items() if h.inst.part == part}
            for t, hs in bar.events.items() if any(h.inst.part == part for h in hs.values())}


def _straight_partial(start: int, end: int) -> list[tuple[int, int]]:
    """Rests inside one beat on the straight grid: dotted 8th only from the beat start."""
    out, t = [], start
    while t < end:
        length = end - t
        if t % R == 0 and length >= R * 3 // 4:
            value = R * 3 // 4
        elif t % (R // 2) == 0 and length >= R // 2:
            value = R // 2
        else:
            value = R // 4
        if value > length:
            raise ScoreError(f'内部错误：无法用直拍休止填充 {length}/{R} 拍')
        out.append((t, value))
        t += value
    return out


def _triplet_partial(start: int, end: int) -> list[tuple[int, int]]:
    out, t = [], start
    while t < end:
        value = R // 3 if t % (R // 3) == 0 and end - t >= R // 3 else R // 6
        out.append((t, value))
        t += value
    return out


def voice_tuplets(bar: Bar, part: str) -> dict[int, int]:
    """Tuplet kind per beat for one voice: 3 (8th triplets), 6 (16th sextuplets), or absent
    when this voice plays nothing off the straight grid in that beat (e.g. a kick on the beat
    under hand triplets stays a plain quarter)."""
    result = {}
    for beat in bar.triplet_beats:
        offsets = [t - beat * R for t, hs in bar.events.items()
                   if beat * R <= t < (beat + 1) * R and any(h.inst.part == part for h in hs.values())]
        if any(o % (R // 4) for o in offsets):
            result[beat] = 6 if any(o % (R // 3) for o in offsets) else 3
    return result


def _rests(start: int, end: int, bar: Bar, tuplets: dict[int, int] | None = None) -> list[VoiceItem]:
    tuplets = {} if tuplets is None else tuplets
    out: list[VoiceItem] = []
    t = start
    while t < end:
        beat = t // R
        beat_end = min(end, (beat + 1) * R)
        if beat in tuplets:
            out += [VoiceItem(a, d, None, tuplet=tuplets[beat]) for a, d in _triplet_partial(t, beat_end)]
            t = beat_end
            continue
        if t % R:
            out += [VoiceItem(a, d, None) for a, d in _straight_partial(t, beat_end)]
            t = beat_end
            continue
        stop = t
        while stop + R <= end and (stop // R) not in tuplets:
            stop += R
        if stop == t:  # less than a whole beat left
            out += [VoiceItem(a, d, None) for a, d in _straight_partial(t, beat_end)]
            t = beat_end
            continue
        if t == 0 and stop == bar.length and not bar.pickup:
            out.append(VoiceItem(0, bar.length, None, measure_rest=True))
            t = stop
        elif t == 0 and stop == bar.length and bar.length in STRAIGHT_VALUES:
            out.append(VoiceItem(0, bar.length, None))  # silent pickup bar: one rest
            t = stop
        else:
            while t < stop:
                b = t // R
                if bar.beats == 4 and b in (0, 2) and stop - t >= 2 * R:
                    out.append(VoiceItem(t, 2 * R, None))
                    t += 2 * R
                else:
                    out.append(VoiceItem(t, R, None))
                    t += R
    return out


def voice_items(bar: Bar, part: str) -> list[VoiceItem]:
    """Notes and rests of one voice.

    Drum notation convention: a note lasts until the next onset of the same voice but
    never past the end of its beat (a note on the beat lasts at most a quarter).  The
    remainder is filled with rests, so rhythms always add up beat by beat.  Inside a
    tuplet beat with several strokes a note lasts at most an 8th-note triplet, so the
    group stays beamed."""
    onsets = voice_hits(bar, part)
    tuplets = voice_tuplets(bar, part)
    if not onsets:
        if bar.pickup:
            return _rests(0, bar.length, bar)
        return [VoiceItem(0, bar.length, None, measure_rest=True)]
    times = sorted(onsets)
    items: list[VoiceItem] = []
    cursor = 0
    for i, t in enumerate(times):
        if t > cursor:
            items += _rests(cursor, t, bar, tuplets)
        nxt = times[i + 1] if i + 1 < len(times) else bar.length
        beat = t // R
        beat_end = (beat + 1) * R
        raw = min(nxt, beat_end) - t
        kind = tuplets.get(beat)
        if kind:
            allowed = [R * 2 // 3, R // 2, R // 3, R // 6] if kind == 6 else [R * 2 // 3, R // 3]
            if sum(1 for x in times if beat * R <= x < beat_end) > 1:
                allowed = [v for v in allowed if v <= R // 3]
            dur = max((v for v in allowed if v <= raw), default=min(allowed))
            items.append(VoiceItem(t, dur, onsets[t], tuplet=kind))
        else:
            dur = max(v for v in (R, R * 3 // 4, R // 2, R // 4) if v <= raw)
            items.append(VoiceItem(t, dur, onsets[t]))
        cursor = t + items[-1].duration
    if cursor < bar.length:
        items += _rests(cursor, bar.length, bar, tuplets)
    assign_beams(items, bar)
    return items


def assign_beams(items: list[VoiceItem], bar: Bar) -> None:
    """Beam the notes of each beat together.  The primary beam spans the run of notes
    after any leading rest; secondary beams join consecutive 16ths, and an isolated 16th
    gets a hook (forward on the first note, backward otherwise)."""
    by_beat: dict[int, list[VoiceItem]] = defaultdict(list)
    for item in items:
        if not item.measure_rest:
            by_beat[item.start // R].append(item)
    for beat, group in by_beat.items():
        if any(it.tuplet for it in group):
            group[0].tuplet_edge = 'both' if len(group) == 1 else 'start'
            if len(group) > 1:
                group[-1].tuplet_edge = 'stop'
            middle = beat * R + R // 2
            min(group, key=lambda it: (abs(it.start + it.duration / 2 - middle), it.start)).tuplet_label = True
        first = next((i for i, it in enumerate(group) if not it.is_rest), None)
        if first is None:
            continue
        run: list[VoiceItem] = []
        for it in group[first:]:
            if it.is_rest:
                break
            run.append(it)
        if len(run) < 2 or any(beam_level(it) == 0 for it in run):
            continue
        levels = [beam_level(it) for it in run]
        for i, it in enumerate(run):
            it.beams = [(1, 'begin' if i == 0 else 'end' if i == len(run) - 1 else 'continue')]
        for i, it in enumerate(run):
            if levels[i] < 2:
                continue
            left = i > 0 and levels[i - 1] >= 2
            right = i < len(run) - 1 and levels[i + 1] >= 2
            if left and right:
                it.beams.append((2, 'continue'))
            elif right:
                it.beams.append((2, 'begin'))
            elif left:
                it.beams.append((2, 'end'))
            else:
                it.beams.append((2, 'forward hook' if i == 0 else 'backward hook'))


def item_ratio(item: VoiceItem) -> tuple[int, int]:
    """MusicXML time-modification of a tuplet item: 3:2 for triplets, 6:4 for sextuplets."""
    return (6, 4) if item.tuplet == 6 else (3, 2)


def tuplet_ratio(bar: Bar, beat: int) -> tuple[int, int]:
    """Bar-level ratio of a tuplet beat: 6:4 when any voice uses 16th-triplet positions."""
    kinds = [voice_tuplets(bar, part).get(beat) for part in ('hand', 'foot')]
    return (6, 4) if 6 in kinds else (3, 2)


def tuplet_number(bar: Bar, beat: int) -> int:
    return tuplet_ratio(bar, beat)[0]
