#!/usr/bin/env bash
# chat_kb.json 재생성 → (변경 있을 때만) 커밋 → 배포(push)
#
# 사용법:
#   ./generator/refresh.sh                  # ~/Downloads·현재폴더의 최신 KakaoTalk_* 자동 선택
#   ./generator/refresh.sh ~/Downloads/KakaoTalk_Chat_..._프롬어스_....csv   # 파일 직접 지정
#
# 동작:
#   1) 원격 동기화(git pull) → 2) chat_kb.json 재생성 → 3) 변경 없으면 종료(빈 커밋 방지)
#   → 4) 변경 있으면 chat_kb.json 커밋 + push(=CI가 빌드·Pages 배포)
#
# 주의: 카톡 .csv export 는 수동입니다. 새 export 가 없으면 "변경 없음"으로 그냥 종료됩니다.
#
# 다방 병합 주의:
#   · 인자 없이 실행  → ~/Downloads 의 모든 KakaoTalk_* 를 방별로 병합(다방 통합)
#   · 파일을 인자로 지정 → 그 파일만 처리(단일 방). 여러 방을 합치려면 인자 없이 실행!
set -uo pipefail

# 리포 루트로 이동(스크립트 위치 = generator/, 부모 = 리포 루트)
cd "$(dirname "${BASH_SOURCE[0]}")/.." || { echo "[refresh] 리포 경로 오류"; exit 1; }

echo "[refresh] 1/4 원격 동기화 (git pull)"
git stash push -q -- .omc 2>/dev/null || true
git pull --ff-only origin main 2>/dev/null || echo "[refresh]    pull 생략(로컬 상태로 진행)"
git stash pop -q 2>/dev/null || true

echo "[refresh] 2/4 chat_kb.json 재생성"
python3 generator/update_archive.py "$@" < /dev/null || { echo "[refresh] 생성 실패 — 중단"; exit 1; }

if git diff --quiet -- chat_kb.json; then
  echo "[refresh] 변경 없음 — 커밋·배포 생략 (새 export 가 없거나 동일 데이터)"
  exit 0
fi

TO=$(python3 -c "import json;print(json.load(open('chat_kb.json'))['build'].get('to',''))" 2>/dev/null)
echo "[refresh] 3/4 커밋 (채팅 ~${TO})"
git add chat_kb.json
git commit -q -m "data: chat_kb.json 최신화 (~${TO})"

echo "[refresh] 4/4 배포 (push) — CI가 빌드·Pages 배포합니다"
git push origin main && echo "[refresh] ✅ 완료"
