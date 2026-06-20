# chat_kb 생성기 (로컬 전용)

카카오톡 export(`.txt`/`.csv`) → `chat_kb.json`(리포 루트) 생성 파이프라인.
네이버 링크 해제(네트워크)·온톨로지 뷰어를 포함하므로 **로컬에서만** 실행한다(CI 미실행).

## 실행
```bash
# 리포 루트에서 실행 권장
python generator/update_archive.py "~/Downloads/KakaoTalk_Chat_..._프롬어스_*.csv"
# 인자 없으면 cwd·~/Downloads 의 최신 KakaoTalk_* 자동 탐색
python generator/update_archive.py
```
→ 리포 루트 `chat_kb.json` 생성(의견 view/position mention 에 `full` 원문 포함).

## 배포 흐름
1. 위 명령으로 리포 루트 `chat_kb.json` 갱신.
2. `chat_kb.json` 을 **사람이 직접 커밋**(`build.yml` auto-commit 대상 아님).
3. CI(`build.yml`)가 `build_hub.py → merge_hub.merge(chat_kb.json)` 로 `knowledge_base.json` in-place 병합 → Pages 배포.

## 테스트
```bash
python generator/test_parse.py     # parse_csv·find_input·full (단위)
python build/test_merge_hub.py     # merge full 통과 (통합)
```

## 주의
- `chat_kb.json` 은 리포 루트에 쓰인다(generator/ 아님). 그 외 산출물(온톨로지_데이터/·뷰어 HTML·jsonl)은 `generator/.gitignore` 로 제외.
- 현재 `public=False`(실명 산출). 공개 익명화/본문 PII 마스킹은 후속 과제.
- txt 와 csv 는 메시지/멤버 카운트가 다르다(csv 가 시스템메시지 포함) — `build` 메타 수치 차이는 정상.
