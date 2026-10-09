"""User material intake only. No implicit browser, OCR, ASR or source validation."""
from pathlib import Path
from urllib.parse import urlsplit


def intake(url=None, screen_recording=None, voice=None, background=None):
    if not url and not screen_recording:
        raise ValueError("공식 링크 또는 앱 화면녹화가 필요합니다")
    if url:
        parsed = urlsplit(url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("Provide an HTTPS source URL without embedded credentials")
    for path in (screen_recording, voice, background):
        if path and not Path(path).is_file():
            raise ValueError("Provided local asset does not exist")
    return {"schema_version": 1, "source_request": {"url": url, "screen_recording": screen_recording},
            "assets": {"voice": voice, "background": background},
            "status": "awaiting_producer_evidence_review", "claims": [],
            "capabilities": {"source_collection": "NOT IMPLEMENTED", "ocr": "NOT IMPLEMENTED", "asr": "NOT IMPLEMENTED"},
            "producer_next_steps": ["공식 조건과 근거 위치 확인", "소재의 중심 질문으로 다섯 형식 선택", "근거 주장표 작성과 대본 검토"],
            "user_timecodes_required": False, "user_coordinates_required": False,
            "editing_status": "효과·속도·자막 스타일·전환·CTA 시각표현은 협의 대기"}


class SourceExtractor:
    def extract(self, request):
        raise NotImplementedError("Source collection/OCR is an explicit stub; producer review required")


class SpeechRecognizer:
    def transcribe(self, path):
        raise NotImplementedError("ASR is an explicit stub; no speech verification performed")
