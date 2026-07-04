# -*- coding: utf-8 -*-
"""프롬어스 허브 빌더 — 아카이브 index.html 허브 버튼 주입."""
import html, os, re


HUB_BTN_CSS = ("\n.hub-btn{display:inline-block;margin-top:22px;padding:11px 24px;"
               "border:1px solid var(--gold-border);border-radius:100px;background:var(--gold-bg);"
               "color:var(--gold);text-decoration:none;font-size:14px;font-weight:600;"
               "transition:all .2s ease}\n"
               ".hub-btn:hover{background:var(--gold);color:#fff;transform:translateY(-1px);"
               "box-shadow:0 4px 14px rgba(184,134,11,.2)}\n")

HUB_BTN_HTML = '\n  <a href="hub.html" class="hub-btn">📊 지식 허브 — 검색·섹터·종목·전략 →</a>'

def inject_hub_button(index_path):
    if not os.path.exists(index_path):
        print(f"ℹ️ index.html 없음({index_path}) — 허브 버튼 주입 생략")
        return
    with open(index_path, encoding="utf-8") as f:
        html = f.read()
    if "hub-btn" in html:
        return  # 이미 주입됨
    changed = False
    if "</style>" in html:
        html = html.replace("</style>", HUB_BTN_CSS + "</style>", 1); changed = True
    m = re.search(r'(<p class="header-sub">.*?</p>)', html, re.S)
    if m:
        html = html[:m.end()] + HUB_BTN_HTML + html[m.end():]; changed = True
    if changed:
        with open(index_path, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"→ {index_path} 에 지식 허브 버튼 주입 완료")
