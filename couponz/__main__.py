"""Script-only interface. No render, upload, publication or automatic collection."""
import argparse
import json
from pathlib import Path
from .evidence import validate
from .intake import intake
from .planner import draft


def main():
    parser = argparse.ArgumentParser(description="쿠폰즈 대본 검토 엔진: 자동 수집·OCR·ASR 미구현, 편집 협의 대기")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("intake")
    p.add_argument("--url")
    p.add_argument("--screen-recording")
    p.add_argument("--voice")
    p.add_argument("--background")
    p.add_argument("--out", required=True)
    p = sub.add_parser("validate")
    p.add_argument("job")
    p.add_argument("--out")
    p = sub.add_parser("draft")
    p.add_argument("job")
    p.add_argument("--out", required=True)
    args = parser.parse_args()
    if args.command == "intake":
        result = intake(args.url, args.screen_recording, args.voice, args.background)
    else:
        job = json.loads(Path(args.job).read_text(encoding="utf-8"))
        result = validate(job) if args.command == "validate" else draft(job)
    if args.out:
        target = Path(args.out)
        if target.exists():
            parser.error("기존 결과는 덮어쓰지 않습니다. 새 버전 경로를 사용하세요")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
