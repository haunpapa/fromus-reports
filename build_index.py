#!/usr/bin/env python3
"""
프롬어스 리포트 인덱스 자동 생성기
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
사용법:  python build_index.py
동작:    reports/ 폴더의 HTML 파일을 스캔 → index.html 자동 생성
"""

import os, re, glob
from datetime import datetime

REPORTS_DIR = "reports"
OUTPUT_FILE = "index.html"

WEEKDAY_KR = ["월", "화", "수", "목", "금", "토", "일"]


def extract_date_from_html(filepath):
    """HTML <title> 태그에서 날짜 추출 (2026.04.10 형식)"""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read(2000)  # 앞부분만 읽기
        m = re.search(r"<title>[^<]*?(\d{4})[.\-/](\d{2})[.\-/](\d{2})", content)
        if m:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except:
        pass

    # fallback: 파일명에서 날짜 추출
    basename = os.path.basename(filepath)
    patterns = [
        r"(\d{4})-(\d{2})-(\d{2})",   # 2026-04-10
        r"(\d{4})(\d{2})(\d{2})",      # 20260410
        r"(\d{2})(\d{2})",             # 0410 → 올해로 가정
    ]
    for p in patterns:
        m = re.search(p, basename)
        if m:
            groups = m.groups()
            if len(groups) == 3:
                return datetime(int(groups[0]), int(groups[1]), int(groups[2]))
            elif len(groups) == 2:
                now = datetime.now()
                return datetime(now.year, int(groups[0]), int(groups[1]))
    return None


def extract_summary_from_html(filepath):
    """HTML에서 시장 온도 요약 텍스트 추출 시도"""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read(5000)
        # callout 박스의 첫 텍스트를 요약으로 사용
        m = re.search(r'class="callout[^"]*"[^>]*>.*?</span>\s*(.*?)</div>', content, re.DOTALL)
        if m:
            text = re.sub(r"<[^>]+>", "", m.group(1)).strip()
            if len(text) > 80:
                text = text[:77] + "…"
            return text
    except:
        pass
    return ""


def scan_reports():
    """reports/ 폴더를 스캔하여 리포트 목록 반환"""
    reports = []
    if not os.path.isdir(REPORTS_DIR):
        print(f"⚠️  '{REPORTS_DIR}/' 폴더가 없습니다. 먼저 만들어주세요.")
        return reports

    for filepath in glob.glob(os.path.join(REPORTS_DIR, "*.html")):
        date = extract_date_from_html(filepath)
        if date is None:
            print(f"  ⚠️  날짜 추출 실패, 건너뜀: {filepath}")
            continue
        summary = extract_summary_from_html(filepath)
        reports.append({
            "file": os.path.basename(filepath),
            "date": date,
            "date_str": date.strftime("%Y.%m.%d"),
            "weekday": WEEKDAY_KR[date.weekday()],
            "summary": summary,
        })

    reports.sort(key=lambda x: x["date"], reverse=True)
    return reports


def group_by_week(reports):
    """리포트를 주 단위로 그룹핑"""
    weeks = {}
    for r in reports:
        # ISO week
        year, week_num, _ = r["date"].isocalendar()
        key = f"{year}-W{week_num:02d}"
        if key not in weeks:
            weeks[key] = {"label": f"{r['date'].strftime('%m월')} {week_num - r['date'].isocalendar()[1] + ((r['date'].month - 1) * 4) + 1}주차", "reports": []}
            # 간단하게 월+주차 라벨
            mon = r["date"].month
            # 해당 주의 월요일 기준
            weeks[key]["label"] = f"{mon}월 {week_num}주차"
        weeks[key]["reports"].append(r)
    return weeks


def generate_html(reports):
    """index.html 생성"""
    total = len(reports)
    latest_date = reports[0]["date_str"] if reports else "-"

    # 주별 그룹핑
    weeks = {}
    for r in reports:
        year, week_num, _ = r["date"].isocalendar()
        key = f"{year}-W{week_num:02d}"
        if key not in weeks:
            mon = r["date"].month
            weeks[key] = {
                "label": f"{mon}월 W{week_num}",
                "reports": [],
                "sort_key": (year, week_num),
            }
        weeks[key]["reports"].append(r)

    sorted_weeks = sorted(weeks.values(), key=lambda w: w["sort_key"], reverse=True)

    # 리포트 카드 HTML 생성
    report_cards_html = ""
    for week in sorted_weeks:
        report_cards_html += f'''
    <div class="week-group">
      <div class="week-label">{week["label"]}</div>
      <div class="week-reports">'''
        for i, r in enumerate(week["reports"]):
            is_new = (r == reports[0])  # 가장 최신이면 NEW 뱃지
            new_badge = '<span class="badge-new">NEW</span>' if is_new else ""
            report_cards_html += f'''
        <a href="reports/{r["file"]}" class="report-card">
          <div class="report-card-left">
            {new_badge}
            <span class="report-date">{r["date_str"]}</span>
            <span class="report-weekday">{r["weekday"]}요일</span>
          </div>
          <div class="report-card-arrow">→</div>
        </a>'''
        report_cards_html += '''
      </div>
    </div>'''

    html = f'''<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>프롬어스 리포트 아카이브</title>
<meta property="og:title" content="프롬어스 Daily Report">
<meta property="og:description" content="프롬어스 투자 커뮤니티 데일리 리포트 아카이브">
<meta property="og:type" content="website">
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;600;700&family=Playfair+Display:ital,wght@0,700;1,600&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>
:root {{
  --bg: #faf8f5; --white: #fff; --surface: #fff; --surface-2: #f5f2ed; --surface-3: #eeebe5;
  --border: #e4dfd6; --border-light: #f0ece5;
  --gold: #b8860b; --gold-bg: #fef9ec; --gold-border: #f5e6b8;
  --text: #1a1612; --text-2: #4a4540; --text-3: #8a847a; --text-4: #b0a898;
}}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
  font-family: 'Noto Sans KR', sans-serif;
  background: var(--bg);
  color: var(--text);
  line-height: 1.85;
  -webkit-font-smoothing: antialiased;
}}

/* ── 헤더 ── */
.header {{
  text-align: center;
  padding: 80px 24px 48px;
  background: linear-gradient(180deg, #fdfcfa 0%, #f8f4ee 100%);
  border-bottom: 1px solid var(--border-light);
}}
.header-label {{
  font-size: 11px;
  letter-spacing: 6px;
  text-transform: uppercase;
  color: var(--gold);
  font-weight: 600;
  margin-bottom: 16px;
}}
.header-title {{
  font-family: 'Playfair Display', serif;
  font-size: clamp(32px, 6vw, 52px);
  font-weight: 700;
  line-height: 1.2;
  margin-bottom: 12px;
}}
.header-title em {{ font-style: italic; color: var(--gold); }}
.header-sub {{
  font-size: 15px;
  color: var(--text-3);
  max-width: 400px;
  margin: 0 auto;
}}
.divider-gold {{
  width: 40px;
  height: 2px;
  background: var(--gold);
  margin: 24px auto;
  opacity: 0.5;
}}

/* ── 통계 ── */
.stats {{
  display: flex;
  gap: 32px;
  justify-content: center;
  flex-wrap: wrap;
  padding: 32px 24px;
}}
.stat-item {{ text-align: center; }}
.stat-val {{
  font-family: 'JetBrains Mono', monospace;
  font-size: 22px;
  font-weight: 600;
  color: var(--gold);
}}
.stat-label {{
  font-size: 11px;
  color: var(--text-3);
  letter-spacing: 1px;
  text-transform: uppercase;
  margin-top: 2px;
}}

/* ── 리포트 목록 ── */
.container {{
  max-width: 640px;
  margin: 0 auto;
  padding: 0 20px 80px;
}}
.week-group {{
  margin-bottom: 32px;
}}
.week-label {{
  font-size: 12px;
  font-weight: 600;
  color: var(--text-3);
  letter-spacing: 2px;
  text-transform: uppercase;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--border-light);
  margin-bottom: 8px;
}}
.week-reports {{
  display: flex;
  flex-direction: column;
  gap: 6px;
}}
.report-card {{
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  background: var(--surface);
  border: 1px solid var(--border-light);
  border-radius: 12px;
  text-decoration: none;
  color: var(--text);
  transition: all 0.2s ease;
}}
.report-card:hover {{
  border-color: var(--gold-border);
  background: var(--gold-bg);
  transform: translateY(-1px);
  box-shadow: 0 2px 8px rgba(184, 134, 11, 0.08);
}}
.report-card-left {{
  display: flex;
  align-items: center;
  gap: 12px;
}}
.report-date {{
  font-family: 'JetBrains Mono', monospace;
  font-size: 15px;
  font-weight: 500;
}}
.report-weekday {{
  font-size: 13px;
  color: var(--text-3);
}}
.report-card-arrow {{
  font-size: 16px;
  color: var(--text-4);
  transition: transform 0.2s ease;
}}
.report-card:hover .report-card-arrow {{
  transform: translateX(3px);
  color: var(--gold);
}}
.badge-new {{
  font-size: 10px;
  font-weight: 600;
  color: var(--gold);
  background: var(--gold-bg);
  border: 1px solid var(--gold-border);
  padding: 2px 8px;
  border-radius: 20px;
  letter-spacing: 1px;
}}

/* ── 푸터 ── */
.footer {{
  text-align: center;
  padding: 40px 24px;
  border-top: 1px solid var(--border-light);
  color: var(--text-3);
  font-size: 13px;
}}
.footer .logo {{
  font-family: 'Playfair Display', serif;
  font-size: 20px;
  font-weight: 700;
  color: var(--text);
  margin-bottom: 8px;
}}

/* ── 반응형 ── */
@media (max-width: 480px) {{
  .header {{ padding: 60px 20px 36px; }}
  .stats {{ gap: 24px; }}
  .report-card {{ padding: 14px 16px; }}
}}
</style>
</head>
<body>

<div class="header">
  <h1 class="header-title"><em>FROM-US</em> Daily Report</h1>
  <div class="divider-gold"></div>
  <p class="header-sub">카카오톡 대화 분석 기반 데일리 리포트 아카이브</p>
</div>

<div class="stats">
  <div class="stat-item">
    <div class="stat-val">{total}</div>
    <div class="stat-label">Total Reports</div>
  </div>
  <div class="stat-item">
    <div class="stat-val">{latest_date}</div>
    <div class="stat-label">Latest</div>
  </div>
</div>

<div class="container">
{report_cards_html}
</div>

<div class="footer">
  <div class="logo">From Us</div>
  <p>프롬어스 리포트 아카이브</p>
  <p style="margin-top:8px;font-size:11px;color:var(--text-4)">본 리포트는 프롬어스 내부 대화를 분석하여 생성되었으며, 투자 권유가 아닙니다.</p>
</div>

</body>
</html>'''
    return html


def main():
    print("━━━ 프롬어스 리포트 인덱스 생성기 ━━━")
    print(f"📂 스캔 폴더: {REPORTS_DIR}/")

    reports = scan_reports()
    if not reports:
        print("❌ 리포트를 찾지 못했습니다.")
        print(f"   '{REPORTS_DIR}/' 폴더에 HTML 파일을 넣어주세요.")
        return

    print(f"✅ {len(reports)}개 리포트 발견:")
    for r in reports:
        print(f"   {r['date_str']} ({r['weekday']}) ← {r['file']}")

    html = generate_html(reports)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"\n🎉 {OUTPUT_FILE} 생성 완료!")
    print(f"   → GitHub에 push하면 자동 배포됩니다.")


if __name__ == "__main__":
    main()
