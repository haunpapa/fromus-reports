# -*- coding: utf-8 -*-
"""허브 리포에서 1회 실행 → build_hub.py + hub_template.html 을 그 자리에서 채팅결합용으로 패치.
   원본을 재현하지 않고 필요한 부분만 삽입(idempotent: 재실행해도 안전). 사용: python apply_hub_patch.py"""
import os, sys

def patch_build_hub(p="build_hub.py"):
    if not os.path.exists(p): return f"[건너뜀] {p} 없음"
    s=open(p,encoding="utf-8").read()
    if "_merge_chat" in s: return f"[이미적용] {p}"
    anchor='"reports": reports, "search": search, "ai_digest": ai_digest, **agg,\n    }'
    if anchor not in s: return f"[수동필요] {p} — 앵커(**agg) 못찾음"
    hook=anchor+'''

    # -- 채팅 온톨로지 병합 (chat_kb.json 있으면 자동) --
    _here = os.path.dirname(os.path.abspath(__file__))
    _chat_path = next((p for p in ("chat_kb.json", os.path.join(_here, "chat_kb.json"))
                       if os.path.exists(p)), None)
    if _chat_path:
        try:
            from merge_hub import merge as _merge_chat
            with open(_chat_path, encoding="utf-8") as _cf:
                _chat = json.load(_cf)
            data, _added = _merge_chat(data, _chat)
            print(f"chat_kb.json merged -- stocks +{_added}")
        except ImportError as _e:
            print(f"[WARN] merge_hub.py 없음 -- 채팅 병합 생략: {_e}", file=sys.stderr)
            data.setdefault("build", {})["chat_merge_error"] = f"import: {_e}"
        except Exception as _e:
            import traceback as _tb
            print(f"[ERROR] chat_kb.json 병합 실패 -- 비병합 허브 생성됨: {_e}", file=sys.stderr)
            _tb.print_exc()
            data.setdefault("build", {})["chat_merge_error"] = str(_e)'''
    open(p,"w",encoding="utf-8").write(s.replace(anchor,hook,1))
    return f"[패치완료] {p}"

RENDERCHAT = '''function renderChat(s){
  const c=s.chat; if(!c) return '';
  const st=c.stance||{};
  const badge=`<span style="color:#7c3aed">강세 ${st.bullish||0} · 약세 ${st.bearish||0} · 관망 ${st.watch||0}</span>`;
  const ments=(c.recent||[]).map(m=>`<div class="mention"><span class="md">${esc(fmtDate(m.date))}</span><span class="src-pill" style="background:#f5f3ff;color:#7c3aed">\\uD83D\\uDCAC ${esc(m.sharer||'')}</span><span>${esc((m.snippet||'').slice(0,120))}</span></div>`).join('');
  const news=(c.news||[]).slice(0,4).map(n=>`<div class="mention"><span class="md">${esc(fmtDate(n.date))}</span><span class="src-pill \\uD14C\\uB9C8">\\uB274\\uC2A4</span><span>${esc(n.title)} <a class="src" href="${esc(n.url)}" target="_blank" rel="noopener">${esc(n.outlet||'\\uC5F4\\uAE30')}\\u2197</a></span></div>`).join('');
  return `<div style="margin-top:10px;border-top:1px dashed var(--border);padding-top:8px"><div style="font-size:11.5px;font-weight:700;color:#7c3aed;margin-bottom:4px">\\uD83D\\uDCAC \\uCC44\\uD305 \\uADFC\\uAC70 \\u00B7 ${c.count}\\uD68C \\u00B7 \\uC2DC\\uADF8\\uB110 ${c.signals} \\u00B7 ${badge}</div>${ments}${news}</div>`;
}
'''

_CHATPILL_DEF=("  const chatPill = s.chat ? `<span class=\"pill\" style=\"background:#f5f3ff;"
               "color:#7c3aed\">\\uD83D\\uDCAC ${s.chat.count}</span>` : '';\n"
               "  return `<div class=\"strow\">")

def patch_template(p="hub_template.html"):
    if not os.path.exists(p): return f"[건너뜀] {p} 없음"
    s=open(p,encoding="utf-8").read()
    if "renderChat" in s: return f"[이미적용] {p}"
    # 4개 앵커를 모두 사전 검증 — 하나라도 없으면 아무것도 쓰지 않음(all-or-nothing)
    anchors={
        "stockRow 함수": "function stockRow(s){",
        "chatPill 삽입위치(strow 반환)": '  return `<div class="strow">',
        "strow-mini 종단(${tp}</span>)": "${tp}</span>",
        "strow-detail(${ments})": "      ${ments}\n    </div>",
    }
    missing=[k for k,v in anchors.items() if v not in s]
    if missing: return f"[수동필요] {p} — 앵커 없음: {missing} (파일 미변경)"
    s2=s
    s2=s2.replace("function stockRow(s){", RENDERCHAT+"function stockRow(s){", 1)   # 1) renderChat 정의
    s2=s2.replace('  return `<div class="strow">', _CHATPILL_DEF, 1)                 # 2) chatPill 정의
    s2=s2.replace('${tp}</span>', '${tp}${chatPill}</span>', 1)                      # 3) 미니행에 pill
    s2=s2.replace("      ${ments}\n    </div>", "      ${ments}${renderChat(s)}\n    </div>", 1)  # 4) 상세에 renderChat
    # 4곳이 실제로 치환됐는지 사후 검증 — 하나라도 누락이면 쓰지 않음(반쪽 패치 방지)
    need=["function renderChat(s){", "const chatPill = s.chat", "${tp}${chatPill}</span>", "${renderChat(s)}"]
    miss2=[n for n in need if n not in s2]
    if miss2: return f"[실패] {p} — 치환 누락: {miss2} (파일 미변경)"
    open(p,"w",encoding="utf-8").write(s2)
    return f"[패치완료] {p}"

if __name__=="__main__":
    print(patch_build_hub())
    print(patch_template())
    print("끝. (merge_hub.py·chat_kb.json·.github/workflows/chat-hub.yml 도 리포에 두세요)")
