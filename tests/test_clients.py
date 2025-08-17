from __future__ import annotations

from pathlib import Path

import responses

from fpl_data.clients import get_json


@responses.activate
def test_get_json_caches_and_retries(tmp_path: Path):
    url = "https://fantasy.premierleague.com/api/bootstrap-static/"
    cache_dir = tmp_path / "cache"

    # 第一次请求：先 500 再 200，触发重试
    responses.add(responses.GET, url, status=500)
    responses.add(
        responses.GET,
        url,
        status=200,
        json={"ok": True, "elements": [], "teams": []},
        content_type="application/json",
    )

    data = get_json(url, cache_dir=cache_dir, ttl_hours=24)
    assert data["ok"] is True
    # 已写入缓存
    assert any(p.suffix == ".json" for p in cache_dir.iterdir())

    # 第二次：不再注册 responses，走缓存也应成功
    responses.reset()
    data2 = get_json(url, cache_dir=cache_dir, ttl_hours=24)
    assert data2["ok"] is True
