#!/usr/bin/env python3
"""Autonomous Batch 4 Studio Audio & WebVTT Build Pipeline for PDEUE University.

Extracts all 25 canonical narration beats directly from `backend/app/api/v1/companion.html`
(Chapter 0 orientation, 18 core curriculum beats across Chapters 1-6, and 6 Deep-Dive
Library modules), synthesizes static `.mp3` narration tracks + synchronized `.vtt` WebVTT
caption files for Studio Mentors Maya (`mentor_f_aa`) and Marcus (`mentor_m_aa`), and writes
`backend/app/static/media/companion/manifest.json`.

Supported TTS providers:
  - `mock`     : Offline, $0, zero-network valid MPEG-1 Layer 3 `.mp3` + `.vtt` generator
                 (for CI, Playwright verification, and local smoke tests).
  - `deepgram` : Deepgram Aura-2 / Flux TTS REST API (`DEEPGRAM_API_KEY` env var required).
  - `deepseek` : DeepSeek TTS REST API (`DEEPSEEK_API_KEY` env var required).

SECURITY INVARIANTS (NON-NEGOTIABLE):
  - Zero hardcoded secrets: API keys are read strictly from environment variables at runtime.
  - Zero runtime API calls: PDEUE University serves strictly local static `.mp3` + `.vtt`
    files via FastAPI `/static/media/companion/*` and `GET /api/v1/portal/companion/state`.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

import httpx

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_COMPANION_HTML = REPO_ROOT / "backend" / "app" / "api" / "v1" / "companion.html"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "backend" / "app" / "static" / "media" / "companion"
DEFAULT_URL_PREFIX = "/static/media/companion"

DEEPGRAM_DEFAULT_URL = "https://api.deepgram.com/v1/speak"
DEEPSEEK_DEFAULT_URL = "https://api.deepseek.com/v1/audio/speech"

# MPEG-1 Layer 3 128 kbps, 44.1 kHz, stereo, no padding:
# Frame size = floor(144 * 128000 / 44100) + 0 = 417 bytes, duration = 1152 / 44100 s.
_MOCK_MP3_FRAME_HEADER = b"\xff\xfb\x90\x00"
_MOCK_MP3_FRAME_SIZE = 417
_MOCK_MP3_FRAME = _MOCK_MP3_FRAME_HEADER + (b"\x00" * (_MOCK_MP3_FRAME_SIZE - len(_MOCK_MP3_FRAME_HEADER)))
_MOCK_MP3_FRAME_DURATION_S = 1152.0 / 44100.0

_MPEG1_L3_BITRATES_KBPS = (
    0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 0
)
_MPEG2_L3_BITRATES_KBPS = (
    0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160, 0
)
_MPEG1_SAMPLE_RATES = (44100, 48000, 32000, 0)
_MPEG2_SAMPLE_RATES = (22050, 24000, 16000, 0)
_MPEG25_SAMPLE_RATES = (11025, 12000, 8000, 0)
_MPEG_SAMPLE_RATES_BY_VERSION: Dict[int, Tuple[int, int, int, int]] = {
    3: _MPEG1_SAMPLE_RATES,   # MPEG Version 1
    2: _MPEG2_SAMPLE_RATES,   # MPEG Version 2
    0: _MPEG25_SAMPLE_RATES,  # MPEG Version 2.5
}


@dataclass(frozen=True)
class VoiceProfile:
    id: str
    label: str
    description: str
    deepgram_default_model: str
    deepseek_default_voice: str


VOICE_PROFILES: Tuple[VoiceProfile, ...] = (
    VoiceProfile(
        id="mentor_f_aa",
        label="Studio Mentor: Maya (African American Female)",
        description="Warm, clear kitchen-table mentor cadence",
        deepgram_default_model="aura-2-thalia-en",
        deepseek_default_voice="maya",
    ),
    VoiceProfile(
        id="mentor_m_aa",
        label="Studio Mentor: Marcus (African American Male)",
        description="Steady, grounded family mentor cadence",
        deepgram_default_model="aura-2-orion-en",
        deepseek_default_voice="marcus",
    ),
)
VOICE_BY_ID: Dict[str, VoiceProfile] = {v.id: v for v in VOICE_PROFILES}


@dataclass(frozen=True)
class NarrationBeat:
    id: str
    title: str
    text: str
    kind: str  # "orientation" | "chapter_beat" | "deep_dive"
    chapter: Optional[int] = None

    @property
    def text_sha256(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()


def _unescape_js_single_quoted(raw: str) -> str:
    return (
        raw.replace("\\'", "'")
        .replace('\\"', '"')
        .replace("\\n", " ")
        .replace("\\r", " ")
        .replace("\\\\", "\\")
        .strip()
    )


def _extract_js_block(html_text: str, start_marker: str, end_marker: str) -> str:
    start_idx = html_text.find(start_marker)
    if start_idx == -1:
        raise ValueError(f"Could not locate JS block starting with {start_marker!r} in companion.html")
    end_idx = html_text.find(end_marker, start_idx + len(start_marker))
    if end_idx == -1:
        raise ValueError(f"Could not locate JS block ending with {end_marker!r} in companion.html")
    return html_text[start_idx:end_idx]


def extract_narration_beats(companion_html_path: Path = DEFAULT_COMPANION_HTML) -> List[NarrationBeat]:
    """Parse ORIENTATION_BEAT, 18 core beats, and 6 DEEP_DIVE_MODULES from companion.html."""
    html_text = companion_html_path.read_text(encoding="utf-8")
    extracted: List[NarrationBeat] = []

    # 1. Chapter 0 Orientation beat
    orient_block = _extract_js_block(html_text, "const ORIENTATION_BEAT=", "const beats=")
    orient_id = re.search(r"id:'((?:\\.|[^'])*)'", orient_block)
    orient_title = re.search(r"title:'((?:\\.|[^'])*)'", orient_block)
    orient_text = re.search(r"text:'((?:\\.|[^'])*)'", orient_block)
    if not (orient_id and orient_title and orient_text):
        raise ValueError("Failed to parse ORIENTATION_BEAT from companion.html")
    extracted.append(
        NarrationBeat(
            id=_unescape_js_single_quoted(orient_id.group(1)),
            title=_unescape_js_single_quoted(orient_title.group(1)),
            text=_unescape_js_single_quoted(orient_text.group(1)),
            kind="orientation",
            chapter=0,
        )
    )

    # 2. 18 core beats across Chapters 1..6
    beats_block = _extract_js_block(html_text, "const beats=[", "const DEEP_DIVE_MODULES=[")
    beat_pattern = re.compile(
        r"\{id:'([^']+)'[^\n]*?ch:(\d+)[^\n]*?title:'((?:\\.|[^'])*)'\s*,\s*text:'((?:\\.|[^'])*)'\}"
    )
    core_beats: List[NarrationBeat] = []
    for match in beat_pattern.finditer(beats_block):
        core_beats.append(
            NarrationBeat(
                id=match.group(1).strip(),
                title=_unescape_js_single_quoted(match.group(3)),
                text=_unescape_js_single_quoted(match.group(4)),
                kind="chapter_beat",
                chapter=int(match.group(2)) + 1,
            )
        )
    if len(core_beats) < 18:
        raise ValueError(f"Expected 18 core curriculum beats in companion.html, found {len(core_beats)}")
    extracted.extend(core_beats)

    # 3. 6 Deep-Dive Library modules (concatenated beats[].body matches companion.html playDeepDiveBtn)
    dd_block = _extract_js_block(html_text, "const DEEP_DIVE_MODULES=[", "const timeline=")
    module_chunks = re.split(r"(?=\n\s*\{\s*\n\s*id:'dd_)", dd_block)
    deep_dives: List[NarrationBeat] = []
    for chunk in module_chunks:
        mod_id = re.search(r"id:'(dd_[^']+)'", chunk)
        mod_title = re.search(r"title:'((?:\\.|[^'])*)'", chunk)
        if not (mod_id and mod_title):
            continue
        bodies = [
            _unescape_js_single_quoted(m.group(1))
            for m in re.finditer(r"body:'((?:\\.|[^'])*)'", chunk)
        ]
        if not bodies:
            raise ValueError(f"Deep-dive module {mod_id.group(1)} has no narration beat bodies")
        deep_dives.append(
            NarrationBeat(
                id=mod_id.group(1).strip(),
                title=_unescape_js_single_quoted(mod_title.group(1)),
                text=" ".join(bodies),
                kind="deep_dive",
                chapter=None,
            )
        )
    if len(deep_dives) < 6:
        raise ValueError(f"Expected at least 6 DEEP_DIVE_MODULES in companion.html, found {len(deep_dives)}")
    extracted.extend(deep_dives)

    return extracted


def estimate_speech_duration_seconds(text: str, words_per_minute: float = 150.0) -> float:
    words = max(1, len(re.findall(r"\S+", text)))
    return round(max(2.0, (words / max(60.0, words_per_minute)) * 60.0), 3)


def build_mock_mp3_bytes(duration_seconds: float = 1.2) -> bytes:
    """Build valid, decodable silent MPEG-1 Layer 3 frames with zero external dependencies."""
    clamped = max(0.5, min(3.0, float(duration_seconds)))
    frame_count = max(16, int(round(clamped / _MOCK_MP3_FRAME_DURATION_S)))
    return _MOCK_MP3_FRAME * frame_count


def estimate_mp3_duration_seconds(mp3_bytes: bytes, fallback_text: str) -> float:
    """Compute MP3 duration by scanning MPEG-1, MPEG-2, and MPEG-2.5 Layer III frame headers (pure Python)."""
    if not mp3_bytes:
        return estimate_speech_duration_seconds(fallback_text)

    idx = 0
    total_len = len(mp3_bytes)

    # Skip optional ID3v2 header
    if total_len >= 10 and mp3_bytes[:3] == b"ID3":
        size_bytes = mp3_bytes[6:10]
        id3_size = (
            ((size_bytes[0] & 0x7F) << 21)
            | ((size_bytes[1] & 0x7F) << 14)
            | ((size_bytes[2] & 0x7F) << 7)
            | (size_bytes[3] & 0x7F)
        )
        idx = min(total_len, 10 + id3_size)

    # Exclude optional trailing 128-byte ID3v1 tag if present
    end_idx = total_len
    if end_idx - idx >= 128 and mp3_bytes[end_idx - 128 : end_idx - 125] == b"TAG":
        end_idx -= 128

    frames = 0
    total_seconds = 0.0
    while idx + 4 <= end_idx:
        b0 = mp3_bytes[idx]
        b1 = mp3_bytes[idx + 1]
        if b0 != 0xFF or (b1 & 0xE0) != 0xE0:
            idx += 1
            continue
        version_bits = (b1 >> 3) & 0x03
        layer_bits = (b1 >> 1) & 0x03
        b2 = mp3_bytes[idx + 2]
        bitrate_idx = (b2 >> 4) & 0x0F
        sample_idx = (b2 >> 2) & 0x03
        padding = (b2 >> 1) & 0x01

        if version_bits in _MPEG_SAMPLE_RATES_BY_VERSION and layer_bits == 1:  # MPEG-1/2/2.5 Layer III
            is_mpeg1 = version_bits == 3
            bitrate_table = _MPEG1_L3_BITRATES_KBPS if is_mpeg1 else _MPEG2_L3_BITRATES_KBPS
            bitrate_kbps = bitrate_table[bitrate_idx]
            sample_rate = _MPEG_SAMPLE_RATES_BY_VERSION[version_bits][sample_idx]
            if bitrate_kbps > 0 and sample_rate > 0:
                samples_per_frame = 1152 if is_mpeg1 else 576
                frame_coef = 144 if is_mpeg1 else 72
                frame_len = ((frame_coef * bitrate_kbps * 1000) // sample_rate) + padding
                if frame_len >= 4 and idx + frame_len <= end_idx:
                    frames += 1
                    total_seconds += samples_per_frame / sample_rate
                    idx += frame_len
                    continue
        idx += 1

    if frames >= 4 and total_seconds > 0.1:
        return round(total_seconds, 3)
    return estimate_speech_duration_seconds(fallback_text)


def _format_vtt_timestamp(seconds: float) -> str:
    ms_total = max(0, int(round(seconds * 1000)))
    hours, rem = divmod(ms_total, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, millis = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"


def split_caption_cues(text: str, max_chars: int = 92) -> List[str]:
    """Split prose into concise, readable WebVTT caption cues at natural boundaries."""
    normalized = re.sub(r"\s+", " ", text).strip()
    if not normalized:
        return [""]

    sentences = re.split(r"(?<=[.!?])\s+", normalized)
    cues: List[str] = []
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        if len(sentence) <= max_chars:
            cues.append(sentence)
            continue
        # Split longer sentences cleanly on punctuation/dashes or word boundaries
        clauses = re.split(r"(?<=[,;—–:])\s+", sentence)
        for clause in clauses:
            clause = clause.strip()
            if not clause:
                continue
            if len(clause) <= max_chars:
                cues.append(clause)
                continue
            words = clause.split(" ")
            buf: List[str] = []
            buf_len = 0
            for word in words:
                added = len(word) + (1 if buf else 0)
                if buf and buf_len + added > max_chars:
                    cues.append(" ".join(buf))
                    buf = [word]
                    buf_len = len(word)
                else:
                    buf.append(word)
                    buf_len += added
            if buf:
                cues.append(" ".join(buf))
    return cues or [normalized]


def generate_webvtt(text: str, duration_seconds: float) -> str:
    """Generate a strictly monotonic, standards-compliant WebVTT caption file."""
    cues = split_caption_cues(text)
    total_duration = max(0.5, float(duration_seconds))
    weights = [max(1, len(c)) for c in cues]
    total_weight = float(sum(weights))

    lines: List[str] = ["WEBVTT", ""]
    cursor = 0.0
    min_step = min(0.05, total_duration / max(1, len(cues) * 2))
    for idx, (cue_text, weight) in enumerate(zip(cues, weights), start=1):
        if idx == len(cues):
            end = max(total_duration, cursor + 0.01)
        else:
            remaining_cues = len(cues) - idx
            max_end = max(cursor + 0.01, total_duration - remaining_cues * min_step)
            slice_dur = total_duration * (weight / total_weight)
            end = min(max_end, cursor + max(min_step, slice_dur))
        if end <= cursor:
            end = cursor + 0.01
        lines.append(f"{idx}")
        lines.append(f"{_format_vtt_timestamp(cursor)} --> {_format_vtt_timestamp(end)}")
        lines.append(cue_text)
        lines.append("")
        cursor = end
    return "\n".join(lines)


class BaseTTSProvider:
    name: str = "base"

    def model_for_voice(self, voice: VoiceProfile) -> str:
        raise NotImplementedError

    def synthesize_mp3(self, text: str, voice: VoiceProfile) -> bytes:
        raise NotImplementedError


class MockTTSProvider(BaseTTSProvider):
    """Offline deterministic valid MPEG-1 Layer 3 generator ($0 cost, zero network)."""

    name = "mock"

    def model_for_voice(self, voice: VoiceProfile) -> str:
        return "mock-mpeg1-l3-silent"

    def synthesize_mp3(self, text: str, voice: VoiceProfile) -> bytes:
        # Compact ~1.2s valid MPEG-1 Layer 3 file so Chromium decodes cleanly while staying tiny
        return build_mock_mp3_bytes(duration_seconds=1.2)


class DeepgramTTSProvider(BaseTTSProvider):
    """Deepgram Aura-2 / Flux TTS REST provider reading DEEPGRAM_API_KEY strictly from env."""

    name = "deepgram"

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        endpoint_url: Optional[str] = None,
        female_model: Optional[str] = None,
        male_model: Optional[str] = None,
        timeout_seconds: float = 60.0,
        max_retries: int = 3,
        http_client: Optional[httpx.Client] = None,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        resolved_key = (api_key if api_key is not None else os.getenv("DEEPGRAM_API_KEY", "")).strip()
        if not resolved_key:
            raise RuntimeError(
                "DEEPGRAM_API_KEY environment variable is required for --provider deepgram. "
                "Export DEEPGRAM_API_KEY in your shell; never commit API keys to the repository."
            )
        self._api_key = resolved_key
        self._endpoint_url = (
            endpoint_url or os.getenv("DEEPGRAM_TTS_URL") or DEEPGRAM_DEFAULT_URL
        ).strip()
        self._voice_models: Dict[str, str] = {
            "mentor_f_aa": (
                female_model
                or os.getenv("DEEPGRAM_VOICE_FEMALE")
                or VOICE_BY_ID["mentor_f_aa"].deepgram_default_model
            ).strip(),
            "mentor_m_aa": (
                male_model
                or os.getenv("DEEPGRAM_VOICE_MALE")
                or VOICE_BY_ID["mentor_m_aa"].deepgram_default_model
            ).strip(),
        }
        self._timeout = timeout_seconds
        self._max_retries = max(1, int(max_retries))
        self._client = http_client
        self._sleep = sleep_fn

    def model_for_voice(self, voice: VoiceProfile) -> str:
        return self._voice_models.get(voice.id, voice.deepgram_default_model)

    def synthesize_mp3(self, text: str, voice: VoiceProfile) -> bytes:
        model = self.model_for_voice(voice)
        headers = {
            "Authorization": f"Token {self._api_key}",
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        }
        params = {"model": model, "encoding": "mp3"}
        payload = {"text": text}
        target_url = self._endpoint_url
        if model.startswith("flux-") and target_url.rstrip("/").endswith("/v1/speak"):
            target_url = target_url.rstrip("/")[:-len("/v1/speak")] + "/v2/speak"
        return _post_tts_with_retries(
            provider_name=self.name,
            url=target_url,
            headers=headers,
            params=params,
            json_body=payload,
            timeout=self._timeout,
            max_retries=self._max_retries,
            client=self._client,
            sleep_fn=self._sleep,
        )


class DeepSeekTTSProvider(BaseTTSProvider):
    """DeepSeek TTS REST provider reading DEEPSEEK_API_KEY strictly from env."""

    name = "deepseek"

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        endpoint_url: Optional[str] = None,
        model: Optional[str] = None,
        female_voice: Optional[str] = None,
        male_voice: Optional[str] = None,
        timeout_seconds: float = 60.0,
        max_retries: int = 3,
        http_client: Optional[httpx.Client] = None,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        resolved_key = (api_key if api_key is not None else os.getenv("DEEPSEEK_API_KEY", "")).strip()
        if not resolved_key:
            raise RuntimeError(
                "DEEPSEEK_API_KEY environment variable is required for --provider deepseek. "
                "Export DEEPSEEK_API_KEY in your shell; never commit API keys to the repository."
            )
        self._api_key = resolved_key
        self._endpoint_url = (
            endpoint_url or os.getenv("DEEPSEEK_TTS_URL") or DEEPSEEK_DEFAULT_URL
        ).strip()
        self._model = (model or os.getenv("DEEPSEEK_TTS_MODEL") or "deepseek-tts").strip()
        self._voice_names: Dict[str, str] = {
            "mentor_f_aa": (
                female_voice
                or os.getenv("DEEPSEEK_VOICE_FEMALE")
                or VOICE_BY_ID["mentor_f_aa"].deepseek_default_voice
            ).strip(),
            "mentor_m_aa": (
                male_voice
                or os.getenv("DEEPSEEK_VOICE_MALE")
                or VOICE_BY_ID["mentor_m_aa"].deepseek_default_voice
            ).strip(),
        }
        self._timeout = timeout_seconds
        self._max_retries = max(1, int(max_retries))
        self._client = http_client
        self._sleep = sleep_fn

    def voice_name(self, voice: VoiceProfile) -> str:
        return self._voice_names.get(voice.id, voice.deepseek_default_voice)

    def model_for_voice(self, voice: VoiceProfile) -> str:
        return f"{self._model}:{self.voice_name(voice)}"

    def synthesize_mp3(self, text: str, voice: VoiceProfile) -> bytes:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        }
        payload = {
            "model": self._model,
            "input": text,
            "voice": self.voice_name(voice),
            "response_format": "mp3",
        }
        return _post_tts_with_retries(
            provider_name=self.name,
            url=self._endpoint_url,
            headers=headers,
            params=None,
            json_body=payload,
            timeout=self._timeout,
            max_retries=self._max_retries,
            client=self._client,
            sleep_fn=self._sleep,
        )


def _post_tts_with_retries(
    *,
    provider_name: str,
    url: str,
    headers: Dict[str, str],
    params: Optional[Dict[str, str]],
    json_body: Dict[str, Any],
    timeout: float,
    max_retries: int,
    client: Optional[httpx.Client],
    sleep_fn: Callable[[float], None],
) -> bytes:
    last_error: Optional[Exception] = None
    owns_client = client is None
    active_client = client or httpx.Client(timeout=timeout)
    try:
        for attempt in range(1, max_retries + 1):
            try:
                resp = active_client.post(url, headers=headers, params=params, json=json_body, timeout=timeout)
                if resp.status_code in {429, 500, 502, 503, 504} and attempt < max_retries:
                    sleep_fn(min(8.0, 0.5 * (2 ** (attempt - 1))))
                    continue
                if resp.status_code >= 400:
                    raise RuntimeError(
                        f"{provider_name} TTS request failed with HTTP {resp.status_code} "
                        f"(body length={len(resp.content)})"
                    )
                if not resp.content:
                    raise RuntimeError(f"{provider_name} TTS returned empty audio payload")
                return bytes(resp.content)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = exc
                if attempt < max_retries:
                    sleep_fn(min(8.0, 0.5 * (2 ** (attempt - 1))))
                    continue
                raise RuntimeError(f"{provider_name} TTS network failure after {max_retries} attempts: {exc}") from exc
        raise RuntimeError(f"{provider_name} TTS failed after {max_retries} attempts: {last_error}")
    finally:
        if owns_client:
            active_client.close()


def create_provider(
    provider_name: str,
    *,
    deepgram_female_model: Optional[str] = None,
    deepgram_male_model: Optional[str] = None,
    deepseek_model: Optional[str] = None,
    deepseek_female_voice: Optional[str] = None,
    deepseek_male_voice: Optional[str] = None,
    http_client: Optional[httpx.Client] = None,
) -> BaseTTSProvider:
    normalized = provider_name.strip().lower()
    if normalized == "mock":
        return MockTTSProvider()
    if normalized == "deepgram":
        return DeepgramTTSProvider(
            female_model=deepgram_female_model,
            male_model=deepgram_male_model,
            http_client=http_client,
        )
    if normalized == "deepseek":
        return DeepSeekTTSProvider(
            model=deepseek_model,
            female_voice=deepseek_female_voice,
            male_voice=deepseek_male_voice,
            http_client=http_client,
        )
    raise ValueError(f"Unsupported TTS provider {provider_name!r}; expected one of: mock, deepgram, deepseek")


def _load_existing_manifest(manifest_path: Path) -> Dict[str, Any]:
    if not manifest_path.is_file():
        return {}
    try:
        parsed = json.loads(manifest_path.read_text(encoding="utf-8"))
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def build_companion_audio(
    *,
    provider: BaseTTSProvider,
    companion_html_path: Path = DEFAULT_COMPANION_HTML,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    url_prefix: str = DEFAULT_URL_PREFIX,
    voice_ids: Optional[Sequence[str]] = None,
    only_beat_ids: Optional[Sequence[str]] = None,
    force: bool = False,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Build `.mp3` + `.vtt` assets for selected Studio Mentors & beats and write manifest.json."""
    beats = extract_narration_beats(companion_html_path)
    if only_beat_ids:
        wanted = {b.strip() for b in only_beat_ids if b.strip()}
        beats = [b for b in beats if b.id in wanted]
        if not beats:
            raise ValueError(f"No matching narration beats found for --only={sorted(wanted)}")

    selected_voices: List[VoiceProfile] = []
    if voice_ids:
        for vid in voice_ids:
            cleaned = vid.strip()
            if cleaned not in VOICE_BY_ID:
                raise ValueError(f"Unknown voice id {cleaned!r}; valid voices: {sorted(VOICE_BY_ID)}")
            selected_voices.append(VOICE_BY_ID[cleaned])
    else:
        selected_voices = list(VOICE_PROFILES)

    output_dir = output_dir.resolve()
    manifest_path = output_dir / "manifest.json"
    existing_manifest = _load_existing_manifest(manifest_path)
    existing_tracks = (
        existing_manifest.get("tracks") if isinstance(existing_manifest.get("tracks"), dict) else {}
    )

    clean_prefix = url_prefix.rstrip("/")
    tracks_manifest: Dict[str, Dict[str, Dict[str, Any]]] = {}
    synthesized_count = 0
    skipped_cached_count = 0

    for voice in selected_voices:
        voice_dir = output_dir / voice.id
        if not dry_run:
            voice_dir.mkdir(parents=True, exist_ok=True)
        voice_model = provider.model_for_voice(voice)
        prev_voice_tracks = (
            existing_tracks.get(voice.id) if isinstance(existing_tracks.get(voice.id), dict) else {}
        )
        voice_tracks: Dict[str, Dict[str, Any]] = {}

        for beat in beats:
            mp3_path = voice_dir / f"{beat.id}.mp3"
            vtt_path = voice_dir / f"{beat.id}.vtt"
            mp3_url = f"{clean_prefix}/{voice.id}/{beat.id}.mp3"
            vtt_url = f"{clean_prefix}/{voice.id}/{beat.id}.vtt"

            prev_entry = prev_voice_tracks.get(beat.id) if isinstance(prev_voice_tracks.get(beat.id), dict) else None
            can_reuse = (
                not force
                and prev_entry is not None
                and prev_entry.get("text_sha256") == beat.text_sha256
                and prev_entry.get("provider") == provider.name
                and prev_entry.get("model") == voice_model
                and mp3_path.is_file()
                and mp3_path.stat().st_size > 0
                and vtt_path.is_file()
                and vtt_path.stat().st_size > 0
            )
            if can_reuse:
                reused = dict(prev_entry)
                reused["mp3"] = mp3_url
                reused["vtt"] = vtt_url
                voice_tracks[beat.id] = reused
                skipped_cached_count += 1
                continue

            if dry_run:
                est_dur = estimate_speech_duration_seconds(beat.text)
                voice_tracks[beat.id] = {
                    "id": beat.id,
                    "title": beat.title,
                    "kind": beat.kind,
                    "chapter": beat.chapter,
                    "mp3": mp3_url,
                    "vtt": vtt_url,
                    "provider": provider.name,
                    "model": voice_model,
                    "duration_seconds": est_dur,
                    "text_sha256": beat.text_sha256,
                    "dry_run": True,
                }
                continue

            mp3_bytes = provider.synthesize_mp3(beat.text, voice)
            duration_s = estimate_mp3_duration_seconds(mp3_bytes, beat.text)
            vtt_content = generate_webvtt(beat.text, duration_s)

            mp3_path.write_bytes(mp3_bytes)
            vtt_path.write_text(vtt_content, encoding="utf-8")

            mp3_sha256 = hashlib.sha256(mp3_bytes).hexdigest()
            vtt_sha256 = hashlib.sha256(vtt_content.encode("utf-8")).hexdigest()

            voice_tracks[beat.id] = {
                "id": beat.id,
                "title": beat.title,
                "kind": beat.kind,
                "chapter": beat.chapter,
                "mp3": mp3_url,
                "vtt": vtt_url,
                "provider": provider.name,
                "model": voice_model,
                "duration_seconds": duration_s,
                "bytes": len(mp3_bytes),
                "sha256": mp3_sha256,
                "vtt_sha256": vtt_sha256,
                "text_sha256": beat.text_sha256,
            }
            synthesized_count += 1

        tracks_manifest[voice.id] = voice_tracks

    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    voices_manifest = []
    for voice in VOICE_PROFILES:
        v_tracks = tracks_manifest.get(voice.id, {})
        voices_manifest.append(
            {
                "id": voice.id,
                "label": voice.label,
                "description": voice.description,
                "provider": provider.name if v_tracks else None,
                "model": provider.model_for_voice(voice) if v_tracks else None,
                "audio_ready": bool(v_tracks) and not dry_run,
                "track_count": len(v_tracks),
            }
        )

    manifest: Dict[str, Any] = {
        "schema_version": "1.0",
        "status": "studio_audio_ready" if (not dry_run and any(tracks_manifest.values())) else "ready_for_batch4_audio",
        "provider": provider.name,
        "generated_at_utc": generated_at,
        "zero_runtime_tts_api": True,
        "track_count_per_voice": len(beats),
        "voices": voices_manifest,
        "tracks": tracks_manifest,
    }

    if not dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)
        tmp_path = output_dir / "manifest.json.tmp"
        tmp_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        os.replace(tmp_path, manifest_path)

    return {
        "manifest": manifest,
        "manifest_path": str(manifest_path),
        "synthesized_count": synthesized_count,
        "skipped_cached_count": skipped_cached_count,
        "beat_count": len(beats),
        "voice_count": len(selected_voices),
        "dry_run": dry_run,
    }


def resync_companion_vtt_only(
    *,
    companion_html_path: Path = DEFAULT_COMPANION_HTML,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    url_prefix: str = DEFAULT_URL_PREFIX,
    voice_ids: Optional[Sequence[str]] = None,
    only_beat_ids: Optional[Sequence[str]] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Re-measure existing local `.mp3` tracks and regenerate synced `.vtt` captions + manifest.json ($0 API cost)."""
    beats = extract_narration_beats(companion_html_path)
    if only_beat_ids:
        wanted = {b.strip() for b in only_beat_ids if b.strip()}
        beats = [b for b in beats if b.id in wanted]
        if not beats:
            raise ValueError(f"No matching narration beats found for --only={sorted(wanted)}")

    selected_voices: List[VoiceProfile] = []
    if voice_ids:
        for vid in voice_ids:
            cleaned = vid.strip()
            if cleaned not in VOICE_BY_ID:
                raise ValueError(f"Unknown voice id {cleaned!r}; valid voices: {sorted(VOICE_BY_ID)}")
            selected_voices.append(VOICE_BY_ID[cleaned])
    else:
        selected_voices = list(VOICE_PROFILES)

    output_dir = output_dir.resolve()
    manifest_path = output_dir / "manifest.json"
    existing_manifest = _load_existing_manifest(manifest_path)
    existing_tracks = (
        existing_manifest.get("tracks") if isinstance(existing_manifest.get("tracks"), dict) else {}
    )
    existing_voices_by_id: Dict[str, Dict[str, Any]] = {}
    if isinstance(existing_manifest.get("voices"), list):
        for entry in existing_manifest["voices"]:
            if isinstance(entry, dict) and entry.get("id"):
                existing_voices_by_id[str(entry["id"])] = entry

    manifest_provider = str(existing_manifest.get("provider") or "local_static")
    clean_prefix = url_prefix.rstrip("/")
    tracks_manifest: Dict[str, Dict[str, Dict[str, Any]]] = {}
    # Preserve untouched voices/tracks when running with --voices or --only
    for vid, vmap in existing_tracks.items():
        if isinstance(vmap, dict):
            tracks_manifest[vid] = {k: dict(v) for k, v in vmap.items() if isinstance(v, dict)}

    resynced_count = 0
    for voice in selected_voices:
        voice_dir = output_dir / voice.id
        prev_voice_tracks = (
            existing_tracks.get(voice.id) if isinstance(existing_tracks.get(voice.id), dict) else {}
        )
        prev_voice_meta = existing_voices_by_id.get(voice.id, {})
        voice_tracks: Dict[str, Dict[str, Any]] = dict(tracks_manifest.get(voice.id, {}))

        for beat in beats:
            mp3_path = voice_dir / f"{beat.id}.mp3"
            vtt_path = voice_dir / f"{beat.id}.vtt"
            if not mp3_path.is_file() or mp3_path.stat().st_size == 0:
                raise FileNotFoundError(
                    f"Existing MP3 track missing or empty for --resync-vtt-only: {mp3_path}"
                )

            mp3_bytes = mp3_path.read_bytes()
            duration_s = estimate_mp3_duration_seconds(mp3_bytes, beat.text)
            vtt_content = generate_webvtt(beat.text, duration_s)

            if not dry_run:
                vtt_path.write_text(vtt_content, encoding="utf-8")

            prev_entry = prev_voice_tracks.get(beat.id) if isinstance(prev_voice_tracks.get(beat.id), dict) else {}
            track_provider = str(prev_entry.get("provider") or prev_voice_meta.get("provider") or manifest_provider)
            track_model = str(
                prev_entry.get("model") or prev_voice_meta.get("model") or voice.deepgram_default_model
            )

            voice_tracks[beat.id] = {
                "id": beat.id,
                "title": beat.title,
                "kind": beat.kind,
                "chapter": beat.chapter,
                "mp3": f"{clean_prefix}/{voice.id}/{beat.id}.mp3",
                "vtt": f"{clean_prefix}/{voice.id}/{beat.id}.vtt",
                "provider": track_provider,
                "model": track_model,
                "duration_seconds": duration_s,
                "bytes": len(mp3_bytes),
                "sha256": hashlib.sha256(mp3_bytes).hexdigest(),
                "vtt_sha256": hashlib.sha256(vtt_content.encode("utf-8")).hexdigest(),
                "text_sha256": beat.text_sha256,
            }
            resynced_count += 1

        tracks_manifest[voice.id] = voice_tracks

    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    voices_manifest = []
    for voice in VOICE_PROFILES:
        v_tracks = tracks_manifest.get(voice.id, {})
        prev_voice_meta = existing_voices_by_id.get(voice.id, {})
        sample_track = next(iter(v_tracks.values()), {}) if v_tracks else {}
        voices_manifest.append(
            {
                "id": voice.id,
                "label": voice.label,
                "description": voice.description,
                "provider": sample_track.get("provider") or prev_voice_meta.get("provider") or (manifest_provider if v_tracks else None),
                "model": sample_track.get("model") or prev_voice_meta.get("model") or (voice.deepgram_default_model if v_tracks else None),
                "audio_ready": bool(v_tracks) and not dry_run,
                "track_count": len(v_tracks),
            }
        )

    manifest: Dict[str, Any] = {
        "schema_version": "1.0",
        "status": "studio_audio_ready" if any(tracks_manifest.values()) else "ready_for_batch4_audio",
        "provider": manifest_provider,
        "generated_at_utc": generated_at,
        "zero_runtime_tts_api": True,
        "track_count_per_voice": max((len(v) for v in tracks_manifest.values()), default=len(beats)),
        "voices": voices_manifest,
        "tracks": tracks_manifest,
    }

    if not dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)
        tmp_path = output_dir / "manifest.json.tmp"
        tmp_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        os.replace(tmp_path, manifest_path)

    return {
        "manifest": manifest,
        "manifest_path": str(manifest_path),
        "resynced_count": resynced_count,
        "synthesized_count": 0,
        "skipped_cached_count": 0,
        "beat_count": len(beats),
        "voice_count": len(selected_voices),
        "dry_run": dry_run,
    }


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build PDEUE University local static Studio Mentor audio (.mp3) and WebVTT captions (.vtt)."
    )
    parser.add_argument(
        "--provider",
        choices=("mock", "deepgram", "deepseek"),
        default="mock",
        help="TTS synthesis backend (default: mock for offline zero-cost verification).",
    )
    parser.add_argument(
        "--companion-html",
        type=Path,
        default=DEFAULT_COMPANION_HTML,
        help="Path to canonical companion.html containing curriculum beats.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory where manifest.json and <voice>/<beat>.{mp3,vtt} are written.",
    )
    parser.add_argument(
        "--url-prefix",
        default=DEFAULT_URL_PREFIX,
        help="Static URL prefix written into manifest.json (default: /static/media/companion).",
    )
    parser.add_argument(
        "--voices",
        default="",
        help="Comma-separated subset of voice IDs (e.g. mentor_f_aa,mentor_m_aa).",
    )
    parser.add_argument(
        "--only",
        default="",
        help="Comma-separated subset of beat IDs (e.g. ch0_orientation,ch1_b1).",
    )
    parser.add_argument(
        "--deepgram-female-model",
        default=None,
        help="Override Deepgram Aura-2 model for mentor_f_aa (or env DEEPGRAM_VOICE_FEMALE).",
    )
    parser.add_argument(
        "--deepgram-male-model",
        default=None,
        help="Override Deepgram Aura-2 model for mentor_m_aa (or env DEEPGRAM_VOICE_MALE).",
    )
    parser.add_argument(
        "--deepseek-model",
        default=None,
        help="Override DeepSeek TTS model name (or env DEEPSEEK_TTS_MODEL).",
    )
    parser.add_argument(
        "--deepseek-female-voice",
        default=None,
        help="Override DeepSeek TTS voice for mentor_f_aa (or env DEEPSEEK_VOICE_FEMALE).",
    )
    parser.add_argument(
        "--deepseek-male-voice",
        default=None,
        help="Override DeepSeek TTS voice for mentor_m_aa (or env DEEPSEEK_VOICE_MALE).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-synthesize tracks even if text_sha256, provider, and model match existing files.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse beats and plan outputs without making API calls or writing files.",
    )
    parser.add_argument(
        "--resync-vtt-only",
        action="store_true",
        help="Read existing local .mp3 files without API calls, recompute exact durations, update manifest.json, and regenerate synced .vtt captions.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    voice_ids = [v.strip() for v in args.voices.split(",") if v.strip()] or None
    only_beats = [b.strip() for b in args.only.split(",") if b.strip()] or None

    if args.resync_vtt_only:
        summary = resync_companion_vtt_only(
            companion_html_path=args.companion_html,
            output_dir=args.output_dir,
            url_prefix=args.url_prefix,
            voice_ids=voice_ids,
            only_beat_ids=only_beats,
            dry_run=args.dry_run,
        )
        print(
            f"[PDEUE Batch 4 Audio] mode=resync_vtt_only beats={summary['beat_count']} "
            f"voices={summary['voice_count']} resynced={summary['resynced_count']} "
            f"dry_run={summary['dry_run']} manifest={summary['manifest_path']}"
        )
        return 0

    if args.dry_run and args.provider != "mock":
        # Dry-run never contacts external APIs or requires live credentials
        provider: BaseTTSProvider = MockTTSProvider()
    else:
        provider = create_provider(
            args.provider,
            deepgram_female_model=args.deepgram_female_model,
            deepgram_male_model=args.deepgram_male_model,
            deepseek_model=args.deepseek_model,
            deepseek_female_voice=args.deepseek_female_voice,
            deepseek_male_voice=args.deepseek_male_voice,
        )

    summary = build_companion_audio(
        provider=provider,
        companion_html_path=args.companion_html,
        output_dir=args.output_dir,
        url_prefix=args.url_prefix,
        voice_ids=voice_ids,
        only_beat_ids=only_beats,
        force=args.force,
        dry_run=args.dry_run,
    )
    print(
        f"[PDEUE Batch 4 Audio] provider={args.provider} beats={summary['beat_count']} "
        f"voices={summary['voice_count']} synthesized={summary['synthesized_count']} "
        f"cached={summary['skipped_cached_count']} dry_run={summary['dry_run']} "
        f"manifest={summary['manifest_path']}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"[PDEUE Batch 4 Audio] ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
