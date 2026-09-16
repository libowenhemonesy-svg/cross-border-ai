import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "gangweiceshi/data_extractors"))
import bili_api


@pytest.mark.parametrize("failed_request", [None, 1, 2])
def test_folder_list_api_error_is_not_empty_success(monkeypatch, failed_request):
    fetcher = bili_api.BiliFavoritesFetcher.__new__(bili_api.BiliFavoritesFetcher)
    fetcher._ensure_wbi_keys = AsyncMock()
    fetcher._img_key = fetcher._sub_key = "test"
    fetcher._headers = {}
    monkeypatch.setattr(bili_api, "sign_params", lambda params, *args: params)
    calls = 0

    def respond(request):
        nonlocal calls
        calls += 1
        payload = {"code": -101, "message": "PRIVATE_PROVIDER_ERROR"} if calls == failed_request else {
            "code": 0, "data": {"list": []},
        }
        return httpx.Response(200, json=payload)

    original = httpx.AsyncClient
    monkeypatch.setattr(bili_api.httpx, "AsyncClient", lambda **kwargs: original(
        transport=httpx.MockTransport(respond), **kwargs,
    ))
    if failed_request:
        with pytest.raises(RuntimeError, match="收藏夹列表读取失败") as error:
            asyncio.run(fetcher.list_folders(1))
        assert "PRIVATE_PROVIDER_ERROR" not in str(error.value)
    else:
        assert asyncio.run(fetcher.list_folders(1)) == []
