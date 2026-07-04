# 프롬어스 허브·파이프라인 개편 (강점 강화 + 약점 보완) 구현계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** hub.html 5.3MB 모놀리스를 셸+데이터로 분리해 재방문 즉시 표시를 달성하고, CI 산출물 커밋을 중단해 git 비대화를 멈추고, build_hub.py를 모듈 분리·테스트·증분 빌드 구조로 재편한다.

**Architecture:** (1) GitHub Pages 배포를 "브랜치 커밋" → "Actions artifact 배포"로 전환해 생성물이 git 히스토리에 쌓이지 않게 한다. (2) hub_template.html의 인라인 KB 데이터를 해시 파일명 `kb.<hash>.json`으로 외부화하고, 앱 스크립트를 `type="fu-app"`으로 지연 실행 + sw.js를 stale-while-revalidate로 바꿔 재방문 시 캐시 즉시 표시한다. (3) build_hub.py(1,237줄)를 `hublib/` 패키지 5개 모듈로 분리하고 `--phase collect|render` 2단계 CLI로 만들어 CI에서 파싱·시세조회가 1회만 돌게 한다.

**Tech Stack:** Python 3.11 (BeautifulSoup4/lxml, yfinance, FinanceDataReader), 순수 JS(빌드도구 없음), GitHub Actions + Pages, pytest(신규, 기존 unittest 테스트와 호환 실행).

---

## 사전 컨텍스트 (실행자가 반드시 알아야 할 현재 구조)

- **데이터 흐름:** 카톡 CSV(수동 export) → `generator/update_archive.py` → `chat_kb.json`(2.9MB, 커밋) → push → CI(`.github/workflows/build.yml`)가 `build_index.py` + `build_hub.py`(2회) + `ai_digest.py` 실행 → `index.html`/`hub.html`(5.3MB)/`knowledge_base.json`(5.6MB)/`ai_digest.json`/`trade.html`을 **다시 커밋** → Pages가 main 브랜치를 서빙.
- **`build_hub.py` 핵심 지점:**
  - `parse_report()` L285: 리포트 HTML 1개 파싱 (BeautifulSoup)
  - `aggregate()` L452, `build_search()` L668
  - `fetch_index_series()` L756 (yfinance), `enrich_market_momentum()` L1068 (FinanceDataReader/KRX, 최대 140종목 스냅샷)
  - `main()` L1132: 전체 조립. L1192에서 `merge_hub.merge()`로 chat_kb 병합 (**merge_hub.py는 사용 중 — 삭제 금지**)
  - L1213-1222: `hub_template.html`의 `/*DATA*/…/*ENDDATA*/` 마커에 KB JSON을 통째로 치환 주입 → 5.3MB hub.html
- **`hub_template.html`:** `<script>` 태그는 총 4개 — L12(테마 조기적용), L22(Chart.js CDN), L653 `<script id="kb-data">window.DATA = /*DATA*/{...}/*ENDDATA*/;</script>`, 그리고 **L657의 단일 대형 앱 스크립트 블록(~1,350줄, 파일 끝까지)**. 앱 블록은 `const D = window.DATA || {}`로 시작해 파싱 즉시 실행되며, 블록 끝부분(L2010 부근)에 sw.js 등록 코드가 있음. kb-data 이후의 앱 스크립트는 이 **1개 블록뿐**이다.
- **CI가 `build_hub.py`를 2회 실행하는 이유:** `ai_digest.py`가 `knowledge_base.json`(1차 산출물)을 입력으로 `ai_digest.json`을 만들고, 2차 실행이 이를 hub에 반영하기 때문.
- **git 상태:** `.git` 362MB. 히스토리에 188MB/45MB급 대형 블롭 존재(현재 refs에서 unreachable — `git rev-list --objects --all`에 안 잡힘). "auto: rebuild" 커밋 66회로 생성물이 히스토리에 누적.
- **`generator/refresh.sh`** (루트 아님): 카톡 CSV → chat_kb.json 재생성 → chat_kb.json만 커밋·push하는 스크립트. 이번 개편의 영향을 받지 않아야 한다.
- **미사용 파일(추정):** `hub_template1.html`, `hub_template2.html`, `apply_hub_patch.py` — 삭제 전 grep 재확인 필요.
- **사용자 규칙:** 커밋 메시지는 한글 + conventional commit(`feat:`, `fix:`, `refactor:`, `chore:`, `ci:`, `test:`). 어트리뷰션 푸터 없음. 로컬 빌드 산출물 커밋 금지.

## 검증 명령 모음 (여러 태스크에서 반복 사용)

```bash
# 전체 빌드 스모크 (약 1~3분, 네트워크 필요 — yfinance/KRX 실패해도 빌드는 성공해야 정상)
python3 build_index.py && python3 build_hub.py --src . --out hub_preview.html --json /tmp/kb_check.json

# 테스트 실행
python3 -m pytest tests/ generator/test_parse.py -v

# 로컬 서빙 확인
python3 -m http.server 8899   # → http://localhost:8899/hub.html
```

---

## Phase 0 — 안전망 (베이스라인 고정)

### Task 0: 작업 브랜치 + 특성화(characterization) 베이스라인 기록

**Files:**
- Create: `tests/__init__.py` (빈 파일)
- Create: `tests/test_baseline.py`
- Create: `tests/fixtures/` (실제 리포트 2개 복사)
- Create: `requirements-dev.txt`

- [ ] **Step 1: 브랜치 생성**

```bash
git checkout -b feat/hub-pipeline-overhaul
```

- [ ] **Step 2: 픽스처 준비 — 실제 리포트 2개를 테스트 픽스처로 복사**

```bash
mkdir -p tests/fixtures/reports/daily tests/fixtures/reports/weekly
cp reports/daily/2026-04-06.html tests/fixtures/reports/daily/
cp "$(ls reports/weekly/*.html | head -1)" tests/fixtures/reports/weekly/
touch tests/__init__.py
echo "pytest>=8" > requirements-dev.txt
pip install -r requirements-dev.txt
```

- [ ] **Step 3: 특성화 테스트 작성 — 현재 파서의 실제 출력값을 그대로 고정**

먼저 현재 값 측정:

```bash
python3 - <<'EOF'
import sys; sys.path.insert(0, '.')
from build_hub import parse_report
r = parse_report('tests/fixtures/reports/daily/2026-04-06.html')
print({'type': r['type'], 'date': r['date'], 'n_sections': len(r.get('sections', [])),
       'keys': sorted(r.keys())})
EOF
```

측정된 **실제 값**을 넣어 `tests/test_baseline.py` 작성 (아래 `<측정값>`을 위 출력으로 치환):

```python
# -*- coding: utf-8 -*-
"""리팩토링 안전망: 현재 파서 출력을 고정하는 특성화 테스트.
값이 바뀌면 파서 동작이 바뀐 것 — 의도된 변경일 때만 이 파일을 갱신한다."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

FIXTURE_DAILY = os.path.join(os.path.dirname(__file__), "fixtures/reports/daily/2026-04-06.html")

def _parse_report(path):
    from build_hub import parse_report   # Phase 3 이후 hublib.parse로 바뀌면 여기만 수정
    return parse_report(path)

def test_daily_report_shape():
    r = _parse_report(FIXTURE_DAILY)
    assert r["type"] == "daily"
    assert r["date"] == "<측정값>"          # 예: "2026-04-06"
    assert len(r.get("sections", [])) == "<측정값>"  # 예: 7 — 정수로 기입
    assert sorted(r.keys()) == "<측정값>"    # 측정된 키 리스트 그대로

def test_aggregate_smoke():
    from build_hub import aggregate
    r = _parse_report(FIXTURE_DAILY)
    r["file"] = "daily/2026-04-06.html"
    agg = aggregate([r])
    assert isinstance(agg.get("stocks"), list)
    assert isinstance(agg.get("sectors"), list)
    assert agg["stocks"], "픽스처 리포트에서 종목이 1개도 추출되지 않음"
```

- [ ] **Step 4: 테스트 실행 → 통과 확인**

```bash
python3 -m pytest tests/test_baseline.py -v
```

Expected: 2 passed. (실패하면 측정값 기입 오류 — 재측정)

- [ ] **Step 5: 커밋**

```bash
git add tests/ requirements-dev.txt
git commit -m "test: 파서 특성화 베이스라인 테스트 추가 (리팩토링 안전망)"
```

---

## Phase 1 — 배포 구조 전환: 산출물 커밋 중단 (약점 2 + 강점 1 강화)

> 목적: CI가 매번 11MB 생성물을 커밋하는 구조를 끊는다. Pages를 "Actions artifact 배포"로 전환하고, cron으로 매일 자동 갱신(시세·trade·다이제스트)한다.

### Task 1: 배포 워크플로우를 artifact 방식으로 재작성

**Files:**
- Modify: `.github/workflows/build.yml` (전면 교체)

- [ ] **Step 1: build.yml을 아래 내용으로 교체**

```yaml
# ───────────────────────────────────────────────────────────────
#  Build & Deploy (GitHub Pages — Actions artifact 배포)
#  생성물(index.html/hub.html/knowledge_base.json 등)은 더 이상 커밋하지 않는다.
#  Pages 소스가 "GitHub Actions"로 설정되어 있어야 한다 (Task 2 참고).
# ───────────────────────────────────────────────────────────────
name: Build & Deploy

on:
  push:
    branches: [main]
    paths:
      - 'reports/**'
      - 'chat_kb.json'
      - 'build_index.py'
      - 'build_hub.py'
      - 'ai_digest.py'
      - 'merge_hub.py'
      - 'hub_template.html'
      - 'sw.js'
      - 'hublib/**'
  schedule:
    - cron: '30 22 * * *'   # 매일 07:30 KST — 시세·trade·다이제스트 자동 갱신
  workflow_dispatch:

permissions:
  contents: read
  pages: write
  id-token: write

concurrency:
  group: pages
  cancel-in-progress: true

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6

      - uses: actions/setup-python@v6
        with:
          python-version: '3.11'

      - name: Install deps
        run: pip install beautifulsoup4 lxml yfinance

      - name: Sync 수출입동향 대시보드 (실패 시 리포 내 기존 trade.html 사용)
        run: |
          curl -fsSL -o trade.new.html https://raw.githubusercontent.com/haunpapa/korea-trade-dashboard/main/korea-trade-sector-dashboard.html \
            && tail -c 30 trade.new.html | grep -q '</html>' \
            && mv trade.new.html trade.html \
            || { echo "동기화 실패 — 기존 trade.html 유지"; rm -f trade.new.html; }

      - name: Build index
        run: python build_index.py

      - name: Build hub (1차 — knowledge_base.json)
        run: python build_hub.py --src . --out hub.html --json knowledge_base.json

      - name: AI weekly digest (시크릿 없으면 자동 생략)
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
        run: python ai_digest.py || echo "AI 다이제스트 생략(실패 무시)"

      - name: Build hub (2차 — 다이제스트 반영)
        run: python build_hub.py --src . --out hub.html --json knowledge_base.json

      - name: Assemble site
        run: |
          mkdir -p _site
          cp index.html hub.html knowledge_base.json trade.html manifest.webmanifest sw.js _site/
          cp ai_digest.json _site/ 2>/dev/null || true
          cp kb.*.json _site/ 2>/dev/null || true   # Phase 2 이후 생성됨
          cp -r reports icons _site/

      - uses: actions/configure-pages@v5
      - uses: actions/upload-pages-artifact@v4
        with:
          path: _site

  deploy:
    needs: build
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - id: deployment
        uses: actions/deploy-pages@v4
```

주의: 기존 `stefanzweifel/git-auto-commit-action` 단계와 `contents: write` 권한은 완전히 제거한다. 2차 빌드 2회 실행은 Phase 3의 Task 12에서 제거한다 (여기서는 배포 방식만 바꾼다).

**배포 범위 변경 주의:** 현재는 브랜치 서빙이라 리포 전체(build_hub.py, generator/ 등)가 공개 URL로 접근 가능하지만, 전환 후에는 **`_site`에 복사한 것만 서빙**된다 (`index.html, hub.html, knowledge_base.json, ai_digest.json, kb.*.json, trade.html, manifest.webmanifest, sw.js, reports/, icons/`). 소스코드가 더 이상 노출되지 않는 것은 보안상 개선이지만, 외부에서 위 목록 밖의 파일 URL을 참조하고 있었다면 404가 된다 — 전환 전 사용자에게 목록을 보여주고 누락 여부를 확인받는다.

- [ ] **Step 2: YAML 문법 검증**

```bash
python3 -c "import yaml,sys; yaml.safe_load(open('.github/workflows/build.yml')); print('OK')"
```

Expected: `OK` (yaml 모듈 없으면 `pip install pyyaml`)

- [ ] **Step 3: 커밋**

```bash
git add .github/workflows/build.yml
git commit -m "ci: Pages 배포를 artifact 방식으로 전환 (산출물 커밋 중단) + 일일 cron 추가"
```

### Task 2: ⚠️ 사용자 수동 단계 — Pages 소스 전환 (실행자는 안내만)

- [ ] **Step 1: 사용자에게 다음을 안내하고 확인을 기다린다**

> GitHub 리포 **Settings → Pages → Build and deployment → Source**를 **"Deploy from a branch"에서 "GitHub Actions"로** 변경해 주세요. 변경 전까지는 기존 방식으로 계속 서빙되므로 사이트가 끊기지 않습니다.

- [ ] **Step 2: 브랜치를 push하고 PR 생성 (main 머지 후 Actions 실행 확인)**

이 시점에는 아직 머지하지 않는다. Phase 2까지 완료 후 한 번에 PR을 올려도 되고, Phase 1만 먼저 머지해 배포 전환을 검증해도 된다 (**권장: Phase 1 먼저 머지·검증**).

머지 후 검증:
```bash
gh run watch --repo haunpapa/fromus-reports
# 성공 후 브라우저에서 https://haunpapa.github.io/fromus-reports/hub.html 정상 표시 확인
# 그리고 새 "auto: rebuild" 커밋이 더 이상 생기지 않는지 확인:
git pull && git log --oneline -3
```

### Task 3: 생성물 추적 해제 (.gitignore)

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: 추적 해제 + gitignore 추가**

Task 2의 Pages 전환·배포 검증이 **완료된 후에만** 실행한다 (전환 전에 지우면 사이트가 빠진다):

```bash
git rm --cached index.html hub.html knowledge_base.json ai_digest.json
cat >> .gitignore <<'EOF'

# CI 생성물 (Actions artifact로 배포 — 커밋 금지)
index.html
hub.html
knowledge_base.json
ai_digest.json
kb.*.json
EOF
```

`trade.html`은 **추적 유지**한다 — CI의 curl 실패 시 폴백 스냅샷 역할.

- [ ] **Step 2: 로컬 빌드가 여전히 동작하는지 확인**

```bash
python3 build_index.py && python3 build_hub.py --src . --out hub.html --json knowledge_base.json
git status --short   # index.html/hub.html 등이 untracked로 안 뜨는지(ignored) 확인
```

- [ ] **Step 3: 커밋**

```bash
git add .gitignore
git commit -m "chore: CI 생성물 git 추적 해제 (artifact 배포로 이전 완료)"
```

---

## Phase 2 — hub 데이터/셸 분리 + 오프라인 즉시 표시 (약점 1 + 강점 2 강화)

> 목적: hub.html을 ~150KB 셸로 줄이고, KB 데이터는 해시 파일명 `kb.<hash>.json`으로 분리. 재방문 시 sw.js 캐시로 **즉시 표시** 후 백그라운드 갱신. 빌드 상태·데이터 신선도 배지 추가.

### Task 4: 템플릿 — 앱 스크립트 지연 실행 구조로 전환

**Files:**
- Modify: `hub_template.html`

핵심 아이디어: `window.DATA` 인라인 주입을 "URL 마커 + fetch 부트스트랩"으로 바꾼다. 데이터 로딩 전에 앱 코드가 실행되면 안 되므로, kb-data 뒤의 **단일 앱 스크립트 블록(L657)** 을 `<script type="fu-app">`(브라우저가 실행하지 않는 타입)으로 바꾸고, 부트스트랩이 데이터 로딩 완료 후 실행한다. 앱 코드 전체가 한 블록 안에 있으므로 내부 `const`/`let` 참조는 전부 그대로 보존된다. **주의: 앱 코드를 여러 `fu-app` 블록으로 쪼개지 말 것** — 블록 간 `const` 공유에 의존하는 구조를 만들지 않는다(향후 유지보수 함정 방지).

- [ ] **Step 1: kb-data 블록 교체**

L653 부근:
```html
<script id="kb-data">
window.DATA = /*DATA*/{...현재 스텁...}/*ENDDATA*/;
</script>
```
를 아래로 교체:
```html
<script id="kb-data">
window.KB_URL = /*KBURL*/"knowledge_base.json"/*ENDKBURL*/;
</script>
```

- [ ] **Step 2: 로딩 플레이스홀더 추가**

`<script id="kb-data">` 바로 **앞**(body 콘텐츠 끝)에 추가:
```html
<div id="fu-boot" style="position:fixed;inset:0;display:flex;align-items:center;justify-content:center;
  background:var(--bg,#faf8f5);z-index:9999;font-size:14px;color:#8a847a;transition:opacity .2s">
  데이터 불러오는 중…
</div>
```

- [ ] **Step 3: L657의 앱 스크립트 블록 1개를 `<script type="fu-app">`로 변경**

kb-data 이후의 앱 `<script>`는 L657의 **1개뿐**이다 (sw.js 등록 코드도 이 블록 안에 포함 — 데이터 로딩 후 등록되어도 무방). L12 테마 스크립트와 L22 Chart.js CDN은 kb-data **앞**이므로 건드리지 않는다. 확인:
```bash
awk '/<script id="kb-data">/{f=1;next} f && /<script/{c++} END{print c}' hub_template.html
```
Expected: `1` (2 이상이면 템플릿이 변경된 것 — 추가된 블록도 모두 fu-app로 전환)

- [ ] **Step 4: 파일 맨 끝 `</body>` 직전에 부트스트랩 추가 (즉시 실행되는 유일한 스크립트)**

```html
<script>
(async function(){
  const boot = document.getElementById('fu-boot');
  try{
    const r = await fetch(window.KB_URL);
    if(!r.ok) throw new Error('HTTP ' + r.status);
    window.DATA = await r.json();
  }catch(e){
    console.error('KB 로딩 실패:', e);
    if(boot) boot.innerHTML = '데이터를 불러오지 못했습니다.<br>' +
      '<a href="javascript:location.reload()" style="color:#b8860b">새로고침</a>';
    return;
  }
  document.querySelectorAll('script[type="fu-app"]').forEach(s=>{
    const n = document.createElement('script');
    n.textContent = s.textContent;
    document.body.appendChild(n);   // 동기 실행 — 원래 순서 보장
  });
  if(boot){ boot.style.opacity = '0'; setTimeout(()=>boot.remove(), 200); }
})();
</script>
```

- [ ] **Step 5: 커밋**

```bash
git add hub_template.html
git commit -m "feat: 허브 템플릿을 KB fetch 지연 로딩 구조로 전환"
```

### Task 5: build_hub.py — kb.<hash>.json 산출 + KBURL 마커 치환

**Files:**
- Modify: `build_hub.py:1209-1223` (템플릿 주입부)

- [ ] **Step 1: 렌더 로직 변경**

교체 범위를 정확히 지킨다:
- **교체 대상: L1209~L1225** — `tpl = args.template or ...`부터 `else: print(f"⚠ 템플릿 없음...")`까지의 if/else 전체.
- **보존 대상: L1227~L1234** — `inject_hub_button(index_path)` 호출부와 `[요약]` print는 **수정 없이 그대로 남긴다** (지우면 index.html 허브 버튼 주입이 조용히 사라진다).
- 파일 상단 import 줄(L21 부근, `import argparse, json, os, re, sys, glob, ...`)에 `hashlib`를 추가한다 (`glob`은 이미 있음).

L1209-1225를 아래로 교체 (else 분기 포함 완결 코드):

```python
    tpl = args.template or os.path.join(os.path.dirname(os.path.abspath(__file__)), "hub_template.html")
    if os.path.exists(tpl):
        with open(tpl, encoding="utf-8") as f:
            shell = f.read()
        payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        kb_hash = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:10]
        kb_name = f"kb.{kb_hash}.json"
        out_dir = os.path.dirname(os.path.abspath(args.out)) or "."
        # 이전 해시 파일 정리 후 새 파일 기록
        for old in glob.glob(os.path.join(out_dir, "kb.*.json")):
            os.remove(old)
        with open(os.path.join(out_dir, kb_name), "w", encoding="utf-8") as f:
            f.write(payload)
        if "/*KBURL*/" in shell and "/*ENDKBURL*/" in shell:
            shell = re.sub(r"/\*KBURL\*/.*?/\*ENDKBURL\*/",
                           f'/*KBURL*/"{kb_name}"/*ENDKBURL*/', shell, count=1, flags=re.S)
        else:
            sys.exit("템플릿에 /*KBURL*/ … /*ENDKBURL*/ 마커가 없습니다.")
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(shell)
        print(f"→ {args.out} 셸 빌드 완료 ({os.path.getsize(args.out)//1024} KB) + {kb_name} ({len(payload)//1024//1024}MB)")
    else:
        print(f"⚠ 템플릿 없음({tpl}) — JSON만 생성했습니다.")
```

- [ ] **Step 2: 빌드 스모크 + 크기 검증**

```bash
python3 build_hub.py --src . --out hub.html --json knowledge_base.json
ls -lh hub.html kb.*.json
```

Expected: `hub.html`이 **300KB 미만**, `kb.<hash>.json`이 ~5MB.

- [ ] **Step 3: 브라우저 동작 검증 (핵심 검증 — 생략 금지)**

```bash
python3 -m http.server 8899 &
```

http://localhost:8899/hub.html 접속 후 확인 (playwright MCP 또는 수동):
1. 로딩 플레이스홀더가 잠깐 표시된 후 사라짐
2. 홈 탭 콘텐츠(센티멘트/스탠스) 정상 렌더
3. 탭 전환(종목/섹터/검색/관계망) 각 1회 — 콘솔 에러 0건
4. 검색창에 "삼성전자" 입력 → 결과 표시

콘솔 에러가 있으면 원인은 대부분 fu-app 전환 누락(어떤 `<script>`가 즉시 실행됨) 또는 실행 순서 문제 — Task 4 Step 3 재확인.

- [ ] **Step 4: 커밋**

```bash
git add build_hub.py
git commit -m "feat: KB 데이터를 해시 파일(kb.<hash>.json)로 외부화 — hub.html 셸 300KB 미만"
```

### Task 6: sw.js — stale-while-revalidate + 해시 데이터 cache-first

**Files:**
- Modify: `sw.js` (전면 교체)

- [ ] **Step 1: sw.js 교체**

```javascript
/* From Us Knowledge Hub — Service Worker v2
   셸(html): stale-while-revalidate — 캐시 즉시 표시 + 백그라운드 갱신
   kb.<hash>.json: cache-first — 해시가 바뀌면 URL이 바뀌므로 영구 캐시 안전 */
const CACHE = 'fu-hub-v2';

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(['./hub.html'])).then(() => self.skipWaiting()));
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', e => {
  if (e.request.method !== 'GET' || !e.request.url.startsWith(self.location.origin)) return;
  const path = new URL(e.request.url).pathname;

  // 불변 데이터 (해시 파일명) — cache-first + 구버전 해시 파일 정리
  if (/\/kb\.[0-9a-f]{6,}\.json$/.test(path)) {
    e.respondWith(
      caches.match(e.request).then(m => m || fetch(e.request).then(r => {
        if (r && r.ok) {
          const cp = r.clone();
          caches.open(CACHE).then(async c => {
            // 새 해시를 캐시하면서 다른 kb.*.json 항목은 삭제 (캐시 무한 누적 방지)
            const keys = await c.keys();
            await Promise.all(keys
              .filter(k => /\/kb\.[0-9a-f]{6,}\.json$/.test(new URL(k.url).pathname) && k.url !== e.request.url)
              .map(k => c.delete(k)));
            c.put(e.request, cp);
          });
        }
        return r;
      }))
    );
    return;
  }

  // 나머지 — stale-while-revalidate
  e.respondWith(
    caches.match(e.request, {ignoreSearch: true}).then(cached => {
      const net = fetch(e.request).then(r => {
        if (r && r.ok) { const cp = r.clone(); caches.open(CACHE).then(c => c.put(e.request, cp)); }
        return r;
      }).catch(() => cached || caches.match('./hub.html'));
      return cached || net;
    })
  );
});
```

**알려진 트레이드오프 (사용자에게 고지):** 셸이 SWR이므로 데이터 갱신 직후 첫 재방문은 캐시된 구버전 hub.html(=구 KB_URL)을 표시하고, 백그라운드에서 새 셸을 받아둔다. 즉 **새 데이터는 그다음 방문부터 보인다** (하루 1회 갱신되는 사이트 특성상 수용 가능한 지연). 이 지연이 문제가 되면 후속 개선으로 "새 버전 있음 → 새로고침" 토스트를 부트스트랩에 추가한다 (이번 범위 아님).

- [ ] **Step 2: 동작 검증**

http.server로 서빙 후: 첫 방문 → 새로고침(캐시에서 즉시 표시되는지 DevTools Network에서 `(ServiceWorker)` 확인) → 서버 끈 상태에서 새로고침(오프라인 표시 확인) → 데이터 변경 후 재빌드하고 2회 새로고침(두 번째에 새 데이터 반영 + DevTools Application 탭에서 구 kb.*.json 캐시 삭제 확인).

- [ ] **Step 3: 커밋**

```bash
git add sw.js
git commit -m "feat: 서비스워커 v2 — SWR 셸 + 해시 데이터 영구 캐시"
```

### Task 7: 빌드 상태·데이터 신선도 배지 (강점 2 강화 — 조용한 폴백의 가시화)

**Files:**
- Modify: `hub_template.html` (푸터 영역)

`data.build`에는 이미 `generated`, `index_source`("yfinance"|"report"), `market_momentum.enabled`, `chat_merge_error`(병합 실패 시)가 들어 있다. 이를 사용자에게 노출한다.

- [ ] **Step 1: 푸터에 배지 컨테이너 추가 + 렌더 코드 작성**

템플릿 푸터 영역에 `<div id="fu-status"></div>` 추가 후, 앱 스크립트(fu-app 블록 중 초기 렌더 담당 블록) 끝에:

```javascript
(function(){
  const el = document.getElementById('fu-status'); if(!el) return;
  const b = D.build || {};
  const warns = [];
  if (b.index_source === 'report') warns.push('지수 시세: 리포트 추출값 대체(yfinance 실패)');
  if (b.market_momentum && b.market_momentum.enabled === false) warns.push('시장 모멘텀: 비활성(' + (b.market_momentum.reason||'') + ')');
  if (b.chat_merge_error) warns.push('채팅 병합 실패: ' + b.chat_merge_error);
  el.innerHTML = '<span style="font-size:11px;color:#8a847a">빌드 ' + esc(b.generated||'?') + ' KST</span>' +
    (warns.length ? '<div style="font-size:11px;color:#b45309;margin-top:4px">⚠ ' + warns.map(esc).join(' · ') + '</div>' : '');
})();
```

- [ ] **Step 2: 검증 — 정상 케이스와 폴백 케이스 둘 다**

```bash
python3 build_hub.py --src . --out hub.html --json knowledge_base.json   # 정상
# 폴백 유도: 네트워크 차단 대신 chat_kb.json을 임시로 옮겨 병합 생략 케이스 확인
```
브라우저에서 푸터에 빌드 시각 표시 확인.

- [ ] **Step 3: 커밋**

```bash
git add hub_template.html
git commit -m "feat: 허브 푸터에 빌드 시각·폴백 경고 배지 추가"
```

### Task 8: Phase 1+2 통합 검증 및 PR

- [ ] **Step 1: 전체 빌드 + 전체 테스트**

```bash
python3 -m pytest tests/ generator/test_parse.py -v
python3 build_index.py && python3 build_hub.py --src . --out hub.html --json knowledge_base.json
```

- [ ] **Step 2: push + PR 생성 (사용자 규칙: 전체 diff 분석 후 포괄적 요약, 한글)**

```bash
git push -u origin feat/hub-pipeline-overhaul
gh pr create --title "feat: 허브 데이터/셸 분리 + Pages artifact 배포 전환" --body "..."
```

- [ ] **Step 3: 머지 후 실배포 검증**

Actions 성공 → https://haunpapa.github.io/fromus-reports/hub.html 에서 Task 5 Step 3의 4개 항목 재확인. **모바일(실기기)에서 재방문 시 즉시 표시되는지 확인.**

---

## Phase 3 — build_hub.py 모듈 분리 + 2단계 빌드 + 증분 캐시 (약점 3)

> 목적: 1,237줄 단일 파일을 `hublib/` 5개 모듈로 분리(파일당 200-400줄 규칙), CI 이중 실행 제거, 리포트 파싱 증분 캐시. **동작 변경 없는 순수 이동 → 특성화 테스트가 안전망.**

### Task 9: hublib 패키지 분리 (순수 코드 이동)

**Files:**
- Create: `hublib/__init__.py`, `hublib/config.py`, `hublib/parse.py`, `hublib/aggregate.py`, `hublib/momentum.py`, `hublib/render.py`
- Modify: `build_hub.py` (얇은 CLI로 축소)

이동 맵 (build_hub.py 기준 줄번호, **함수 본문은 수정 없이 그대로 이동**). 마지막 열은 각 모듈이 import해야 할 것 — 이동 후 각 모듈을 `python3 -c "import hublib.<모듈>"`로 즉시 확인하고, NameError가 나면 해당 이름의 소속 모듈에서 명시적으로 import한다 (`from hublib.config import *` 같은 와일드카드 금지):

| 대상 모듈 | 이동할 것 | 의존 (import) |
|---|---|---|
| `hublib/config.py` | KST 상수(L24 부근), `_now_kst/_today_kst/_fmt_kst`(L26-34), 파일 상단 상수·타소노미 테이블 전부 (L40~143 부근: 종목 별칭/스톱워드/ETF 브랜드/섹터 매핑/원칙 버킷/요일 등 — 실제 상수명은 이동 시 확인) | 표준 라이브러리만 |
| `hublib/parse.py` | `is_supply_card, supply_tag`(L109-143), `txt, txt_tight, classes, parse_target_prices, parse_num`(L144-182), `normalize_stock, expand_stock_names, sector_theme`(L183-206), `detect_report`(L207), `section_kind`(L244), `card_is_glossary`(L273), `parse_report`(L285), `split_stock_token`(L422), `discover`(L704) + BeautifulSoup import 가드(L36-38) | `hublib.config`의 타소노미 상수 전부 |
| `hublib/aggregate.py` | `aggregate`(L452-667), `build_search`(L668-703) | `hublib.config` (+ parse의 헬퍼를 쓰면 `hublib.parse`) |
| `hublib/momentum.py` | `fetch_index_series`(L756)부터 `enrich_market_momentum`(L1068)까지 보조함수 포함 전부 (L756-1130). yfinance/FinanceDataReader import는 함수 내부 지연 import 유지 | `hublib.config`의 `_today_kst` 등 |
| `hublib/render.py` | `inject_hub_button`(L731-755), 그리고 `main()`에서 "data 조립 + chat 병합 + json/hub 기록" 부분을 `collect(...)`/`render(...)` 두 함수로 추출 (Task 10에서 상세) | `hublib.parse`, `hublib.aggregate`, `hublib.momentum`, 루트의 `merge_hub` |

- [ ] **Step 1: 모듈 생성 및 함수 이동** — BeautifulSoup import 가드(L36-38)는 `hublib/parse.py`로. 각 모듈 상호 import는 `from hublib.config import ...` 형태.

- [ ] **Step 2: build_hub.py를 하위호환 re-export + CLI만 남기기**

```python
#!/usr/bin/env python3
"""프롬어스 Knowledge Hub 빌더 — CLI. 로직은 hublib/ 패키지에 있다."""
import argparse, sys
# 하위호환 re-export (tests/test_baseline.py 등에서 from build_hub import parse_report 사용)
from hublib.parse import parse_report, discover
from hublib.aggregate import aggregate, build_search
from hublib.render import collect, render, inject_hub_button

def main():
    ...  # 기존 main의 인자 파싱 + collect/render 호출 (Task 10)
```

- [ ] **Step 3: 특성화 테스트로 동작 불변 확인**

```bash
python3 -m pytest tests/test_baseline.py -v
```
Expected: PASS — 값이 달라졌으면 이동 중 실수. diff로 원인 추적.

- [ ] **Step 4: 전체 빌드 스모크 → 출력 요약 라인(종목 N·섹터 M…)이 이동 전과 동일한지 비교**

- [ ] **Step 5: 커밋**

```bash
git add hublib/ build_hub.py
git commit -m "refactor: build_hub.py를 hublib 패키지 5개 모듈로 분리 (동작 불변)"
```

### Task 10: `--phase collect|render|all` 2단계 CLI

**Files:**
- Modify: `hublib/render.py`, `build_hub.py`
- Test: `tests/test_phases.py`

설계:
- `collect(src, json_out)`: 파싱→집계→시세→chat 병합→`knowledge_base.json` 기록 (무거운 단계 전부)
- `render(json_in, out, template, index_path)`: `knowledge_base.json` + `ai_digest.json`(있으면 `data["ai_digest"]`에 주입) 로드 → `kb.<hash>.json` + `hub.html` 기록 + `knowledge_base.json`에 digest 반영 재기록 + **`inject_hub_button(index_path)` 호출 포함** (index.html이 없으면 기존 동작대로 경고만 출력하고 계속 — `inject_hub_button` 내부 동작 확인)
- `--phase all`(기본값): collect → render. 기존 호출 방식과 100% 호환.

- [ ] **Step 1: 실패하는 테스트 먼저 작성** (`tests/test_phases.py`)

```python
# -*- coding: utf-8 -*-
import json, os, subprocess, sys, tempfile, shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def _run(args, cwd):
    return subprocess.run([sys.executable, os.path.join(ROOT, "build_hub.py")] + args,
                          cwd=cwd, capture_output=True, text=True, timeout=300)

def test_collect_then_render(tmp_path):
    # 픽스처 리포트만으로 미니 사이트 구성
    src = tmp_path / "site"
    shutil.copytree(os.path.join(ROOT, "tests/fixtures/reports"), src / "reports")
    shutil.copy(os.path.join(ROOT, "hub_template.html"), src / "hub_template.html")

    r1 = _run(["--phase", "collect", "--src", ".", "--json", "kb_raw.json"], cwd=src)
    assert r1.returncode == 0, r1.stderr
    assert (src / "kb_raw.json").exists()

    # 가짜 다이제스트를 두고 render — 주입되는지 확인
    (src / "ai_digest.json").write_text(json.dumps({"digest": {"title": "테스트다이제스트"}}), encoding="utf-8")
    r2 = _run(["--phase", "render", "--json", "kb_raw.json", "--out", "hub.html",
               "--template", "hub_template.html"], cwd=src)
    assert r2.returncode == 0, r2.stderr
    assert (src / "hub.html").exists()
    kb_files = list(src.glob("kb.*.json"))
    assert len(kb_files) == 1
    data = json.loads(kb_files[0].read_text(encoding="utf-8"))
    assert data["ai_digest"]["digest"]["title"] == "테스트다이제스트"
    # 셸에 해시 URL이 박혔는지
    assert kb_files[0].name in (src / "hub.html").read_text(encoding="utf-8")
```

- [ ] **Step 2: 실행 → FAIL 확인** (`--phase` 미구현이므로)

- [ ] **Step 3: 구현** — `main()`에 `--phase` 인자 추가, collect/render 분리. render 단계는 네트워크·bs4 불필요해야 한다 (import를 함수 안으로 지연시켜 render만 실행 시 yfinance 미설치여도 동작).

- [ ] **Step 4: 테스트 PASS + 특성화 테스트 PASS 확인 후 커밋**

```bash
python3 -m pytest tests/ -v
git add hublib/ build_hub.py tests/test_phases.py
git commit -m "feat: build_hub 2단계 빌드(--phase collect|render) — 다이제스트 반영 시 재파싱 제거"
```

### Task 11: 리포트 파싱 증분 캐시

**Files:**
- Create: `hublib/cache.py`
- Modify: `hublib/render.py`(collect 경로)
- Test: `tests/test_cache.py`

- [ ] **Step 1: 실패하는 테스트 먼저** (`tests/test_cache.py`)

```python
# -*- coding: utf-8 -*-
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from hublib.cache import ParseCache

def test_cache_hit_and_invalidation(tmp_path):
    cache_file = tmp_path / "parse_cache.json"
    target = tmp_path / "r.html"
    target.write_text("<html>v1</html>", encoding="utf-8")

    c = ParseCache(str(cache_file))
    calls = []
    def parser(p):
        calls.append(p); return {"parsed": "v1"}

    assert c.get_or_parse(str(target), parser) == {"parsed": "v1"}
    assert c.get_or_parse(str(target), parser) == {"parsed": "v1"}
    assert len(calls) == 1                      # 두 번째는 캐시 히트

    target.write_text("<html>v2</html>", encoding="utf-8")   # 내용 변경 → 무효화
    c.get_or_parse(str(target), parser)
    assert len(calls) == 2

    c.save()
    c2 = ParseCache(str(cache_file))            # 디스크에서 복원돼도 히트
    c2.get_or_parse(str(target), parser)
    assert len(calls) == 2
```

- [ ] **Step 2: FAIL 확인 → 구현** (`hublib/cache.py`, sha1(파일내용) 키, `build/parse_cache.json` 기본 경로, 40줄 내외)

```python
# -*- coding: utf-8 -*-
"""리포트 파싱 결과 증분 캐시 — 파일 내용 sha1 기준 무효화."""
import hashlib, json, os

class ParseCache:
    def __init__(self, path="build/parse_cache.json"):
        self.path = path
        try:
            with open(path, encoding="utf-8") as f:
                self.data = json.load(f)
        except Exception:
            self.data = {}
        self.dirty = False

    def get_or_parse(self, filepath, parser):
        with open(filepath, "rb") as f:
            digest = hashlib.sha1(f.read()).hexdigest()
        entry = self.data.get(filepath)
        if entry and entry.get("sha1") == digest:
            return entry["parsed"]
        parsed = parser(filepath)
        self.data[filepath] = {"sha1": digest, "parsed": parsed}
        self.dirty = True
        return parsed

    def save(self):
        if not self.dirty:
            return
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False)
```

주의: `parse_report` 반환값에 JSON 비직렬화 객체(datetime 등)가 있으면 캐시 기록 전 확인 필요 — `json.dumps(parsed)` 라운드트립이 되는지 collect 경로에서 검증하고, 안 되면 sort_date 등만 문자열로 정규화.

- [ ] **Step 3: collect 경로에 연결 + `.gitignore`에 `build/parse_cache.json` 추가 + 전체 빌드 2회 실행으로 체감 확인**

```bash
time python3 build_hub.py --phase collect --src . --json /tmp/kb1.json   # cold
time python3 build_hub.py --phase collect --src . --json /tmp/kb2.json   # warm — 파싱 구간 단축 확인
python3 -c "import json; a=json.load(open('/tmp/kb1.json')); b=json.load(open('/tmp/kb2.json')); a['build']=b['build']={}; print('IDENTICAL' if a==b else 'DIFF')"
```
Expected: `IDENTICAL` (build 메타 제외 완전 동일)

- [ ] **Step 4: 커밋**

```bash
git add hublib/cache.py hublib/render.py tests/test_cache.py .gitignore
git commit -m "perf: 리포트 파싱 증분 캐시 (파일 sha1 기준) — 리포트 67개 재파싱 제거"
```

### Task 12: CI를 2단계 빌드 + 캐시로 최적화

**Files:**
- Modify: `.github/workflows/build.yml`

- [ ] **Step 1: 빌드 스텝 교체**

기존 "1차 빌드 → digest → 2차 빌드"를:

```yaml
      - name: Restore parse cache
        uses: actions/cache@v4
        with:
          path: build/parse_cache.json
          key: parse-cache-${{ hashFiles('reports/**/*.html', 'hublib/parse.py') }}
          restore-keys: parse-cache-

      - name: Collect (파싱·집계·시세 — 1회만)
        run: python build_hub.py --phase collect --src . --json knowledge_base.json

      - name: AI weekly digest (시크릿 없으면 자동 생략)
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
        run: python ai_digest.py || echo "AI 다이제스트 생략(실패 무시)"

      - name: Render (hub.html + kb.<hash>.json)
        run: python build_hub.py --phase render --json knowledge_base.json --out hub.html
```

- [ ] **Step 2: 테스트 스텝 추가** (Assemble 전에)

```yaml
      - name: Run tests
        run: pip install pytest && python -m pytest tests/ generator/test_parse.py -q
```

- [ ] **Step 3: 커밋 + push 후 Actions 실행시간 이전 대비 확인**

```bash
git add .github/workflows/build.yml
git commit -m "ci: 2단계 빌드 전환 — build_hub 이중 실행 제거 + 파싱 캐시 + 테스트 게이트"
```

---

## Phase 4 — git 저장소 다이어트 (약점 2 마무리) ⚠️ 파괴적 — 사용자 승인 필수

### Task 13: 대형 블롭 식별 → 로컬 정리 → (필요시에만) 히스토리 재작성

- [ ] **Step 1: 대형 블롭 정체 확인 (프라이버시 점검 — 카톡 원본 여부)**

```bash
git cat-file -p f81c1f84c3784b7161a961a7353879f5eb21f9db | head -c 300
git cat-file -p 62802ebbbec69534ccaa57d8b5d148927b1f38e0 | head -c 300
```
카톡 대화 원본(실명 포함)이면 아래 정리의 우선순위가 "용량"에서 "프라이버시"로 격상된다.

- [ ] **Step 2: 로컬 gc (unreachable 블롭은 이것만으로 제거될 수 있음)**

```bash
git reflog expire --expire=now --all
git gc --aggressive --prune=now
du -sh .git    # 362MB → 얼마나 줄었는지 기록
```

- [ ] **Step 3: 원격 히스토리 오염 여부 판정**

```bash
git clone --bare git@github.com:haunpapa/fromus-reports.git /tmp/fr-bare && du -sh /tmp/fr-bare
```
- 수십 MB 수준이면: 원격은 깨끗 → **여기서 종료** (로컬 gc로 충분).
- 수백 MB이거나 Step 1에서 카톡 원본 확인 시: Step 4 진행.

- [ ] **Step 4: ⚠️ 사용자 승인 후에만 — filter-repo로 대형 블롭 제거 + force push**

사용자에게 고지할 것: 전체 히스토리 재작성, 모든 클론 재클론 필요, 열린 PR 무효화. 승인 후:

```bash
pip install git-filter-repo
git clone --mirror git@github.com:haunpapa/fromus-reports.git /tmp/fr-mirror-backup   # 백업
cd /tmp && git clone git@github.com:haunpapa/fromus-reports.git fr-clean && cd fr-clean
git filter-repo --strip-blobs-bigger-than 8M
git remote add origin git@github.com:haunpapa/fromus-reports.git
git push origin --force --all && git push origin --force --tags
```
이후 로컬 작업 리포는 재클론. GitHub Support에 dangling 객체 gc 요청(프라이버시 사안일 경우)도 안내.

---

## Phase 5 — 자산 정리 + 스키마 버전 (강점 3 강화)

### Task 14: 데드 파일 정리

**Files:**
- Delete: `hub_template1.html`, `hub_template2.html`, `apply_hub_patch.py`

- [ ] **Step 1: 참조 0건 재확인 (merge_hub.py는 삭제 금지 — build_hub가 사용 중)**

```bash
grep -rn 'hub_template1\|hub_template2\|apply_hub_patch' \
  --include='*.py' --include='*.yml' --include='*.sh' --include='*.html' . | grep -v '.venv\|docs/'
```
Expected: 출력 없음 (docs/ 내 과거 계획 문서 언급은 무시)

- [ ] **Step 2: 삭제 + 빌드 스모크 + 커밋**

```bash
git rm hub_template1.html hub_template2.html apply_hub_patch.py
python3 build_hub.py --phase all --src . --out hub.html --json knowledge_base.json
git commit -m "chore: 미사용 템플릿·패치 스크립트 제거"
```

### Task 15: KB 스키마 버전 + 문서화

**Files:**
- Modify: `hublib/render.py` (build 메타에 `"schema": 2` 추가)
- Modify: `generator/README.md` (스키마 문서 섹션 추가 — 새 .md 생성 금지, 기존 README에 추가)

- [ ] **Step 1: `data["build"]["schema"] = 2` 추가 + 특성화 테스트의 키 목록 갱신**

- [ ] **Step 2: generator/README.md에 "knowledge_base.json 스키마 v2" 섹션 작성** — 최상위 키(build/reports/search/stocks/sectors/stance/principles/glossary/events/sentiment/series/chat/ai_digest)별 1-2줄 설명 + "키 추가는 마이너, 키 의미 변경·삭제는 schema 증가" 규칙 명시.

- [ ] **Step 3: 커밋**

```bash
git add hublib/render.py generator/README.md tests/test_baseline.py
git commit -m "docs: KB 스키마 v2 버전 필드·문서화 — 외부 소비자 대비"
```

### Task 16: 최종 통합 검증

- [ ] **Step 1:** `python3 -m pytest tests/ generator/test_parse.py -v` → 전체 PASS
- [ ] **Step 2:** 로컬 풀빌드 + 브라우저에서 Task 5 Step 3 체크리스트 재확인
- [ ] **Step 3:** PR 생성(사용자 규칙 준수), 머지 후 Actions 성공 + 실사이트 확인
- [ ] **Step 4:** `generator/refresh.sh`(카톡 갱신 경로)가 여전히 동작하는지 확인 — chat_kb.json만 커밋하는 구조라 영향 없어야 정상

---

## 리스크 및 롤백

| 리스크 | 대응 |
|---|---|
| Pages 소스 전환 타이밍에 사이트 공백 | 전환 전까지 구 방식 서빙 유지. Task 3(추적 해제)은 반드시 배포 검증 후 |
| fu-app 전환 누락으로 hub 백지화 | Task 5 Step 3 브라우저 검증 필수. 실패 시 `git revert`로 템플릿만 원복하면 구 방식으로 즉시 복귀 (DATA 마커 렌더 코드가 남아있는 커밋으로) |
| sw.js v2 캐시 꼬임 | CACHE 이름 v2 → activate에서 구 캐시 전부 삭제됨. 문제 시 v3로 올려 재배포 |
| 캐시된 파싱 결과 스키마 불일치(파서 수정 후) | actions/cache 키에 `hublib/parse.py` 해시 포함 — 파서 변경 시 캐시 자동 무효화. 로컬은 `rm build/parse_cache.json` |
| filter-repo 사고 | mirror 백업 선행 + 사용자 승인 게이트. Step 3에서 원격이 깨끗하면 아예 실행 안 함 |

## 명시적 비목표 (YAGNI)

- KB 월별 샤딩(핫/콜드 분리): 해시 파일 + SW 캐시로 우선 해결. 데이터가 15MB를 넘거나 첫 로딩이 다시 문제 되면 그때 별도 계획으로.
- 리포트 생성 자동화, 카톡 export 자동화: 별개 프로젝트 범위.
- 프론트 프레임워크 도입·번들러: 현행 순수 JS 유지.
