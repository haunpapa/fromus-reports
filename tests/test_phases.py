# -*- coding: utf-8 -*-
"""2단계 빌드(--phase collect|render) 통합 테스트."""
import json
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _run(args, cwd):
    # 검증 레이어는 tests/test_verify.py 가 전담한다 — 2단계 빌드 테스트는 네트워크와 무관해야 한다
    env = {**os.environ, "VERIFY_SKIP": "1"}
    return subprocess.run([sys.executable, os.path.join(ROOT, "build_hub.py")] + args,
                          cwd=cwd, capture_output=True, text=True, timeout=300, env=env)


def test_collect_then_render(tmp_path):
    # 픽스처 리포트만으로 미니 사이트 구성
    src = tmp_path / "site"
    shutil.copytree(os.path.join(ROOT, "tests", "fixtures", "reports"), src / "reports")
    shutil.copy(os.path.join(ROOT, "hub_template.html"), src / "hub_template.html")

    # collect: knowledge_base.json 생성
    r1 = _run(["--phase", "collect", "--src", ".", "--json", "kb_raw.json"], cwd=str(src))
    assert r1.returncode == 0, r1.stderr
    assert (src / "kb_raw.json").exists()
    kb = json.loads((src / "kb_raw.json").read_text(encoding="utf-8"))
    assert kb["ai_digest"] is None          # collect 단계에서는 다이제스트 미주입
    assert kb["build"]["reports"] >= 1
    assert kb["build"]["schema"] == 2       # 스키마 버전 필드

    # 가짜 다이제스트를 두고 render — 주입되는지 확인
    (src / "ai_digest.json").write_text(
        json.dumps({"digest": {"title": "테스트다이제스트"}}, ensure_ascii=False), encoding="utf-8")
    r2 = _run(["--phase", "render", "--json", "kb_raw.json", "--out", "hub.html",
               "--template", "hub_template.html"], cwd=str(src))
    assert r2.returncode == 0, r2.stderr
    assert (src / "hub.html").exists()

    kb_files = list(src.glob("kb.*.json"))
    assert len(kb_files) == 1, f"해시 KB 파일이 정확히 1개여야 함: {kb_files}"
    data = json.loads(kb_files[0].read_text(encoding="utf-8"))
    assert data["ai_digest"]["digest"]["title"] == "테스트다이제스트"
    # 셸에 해시 URL 이 박혔는지
    assert kb_files[0].name in (src / "hub.html").read_text(encoding="utf-8")
    # render 가 knowledge_base.json 에도 다이제스트를 반영했는지
    kb2 = json.loads((src / "kb_raw.json").read_text(encoding="utf-8"))
    assert kb2["ai_digest"]["digest"]["title"] == "테스트다이제스트"


def test_render_reuses_existing_kb_without_recollect(tmp_path):
    # collect 로 만든 kb 를 두 번 render 해도 안전하고, 해시 파일이 항상 1개로 유지되는지
    src = tmp_path / "site"
    shutil.copytree(os.path.join(ROOT, "tests", "fixtures", "reports"), src / "reports")
    shutil.copy(os.path.join(ROOT, "hub_template.html"), src / "hub_template.html")
    assert _run(["--phase", "collect", "--src", ".", "--json", "kb_raw.json"], cwd=str(src)).returncode == 0
    for _ in range(2):
        r = _run(["--phase", "render", "--json", "kb_raw.json", "--out", "hub.html",
                  "--template", "hub_template.html"], cwd=str(src))
        assert r.returncode == 0, r.stderr
    assert len(list(src.glob("kb.*.json"))) == 1


def test_hub_template_has_kb_retry_fallback():
    """배포 직후 구 셸이 사라진 kb.<구해시> 404 를 만나면 1회 캐시버스터 재로드해야 한다."""
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[1]
    tpl = (root / "hub_template.html").read_text(encoding="utf-8")
    sw = (root / "sw.js").read_text(encoding="utf-8")
    assert "kbRetried" in tpl and "?nosw=" in tpl, "부트 재시도는 SW 탈출구(?nosw=)를 써야 함"
    assert "searchParams.has('nosw')" in sw, "sw.js 에 ?nosw= 패스스루 없음"
    assert "fu-hub-v3" in sw, "SW 캐시 버전 v3 아님"
    assert "cache: 'reload'" in sw, "install 프리캐시가 HTTP 캐시를 우회해야 함(stale 셸 고착 방지)"
