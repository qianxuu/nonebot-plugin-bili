"""测试用假 HTTP 会话与简易 Bot。"""

from __future__ import annotations

from typing import Any, cast
from collections.abc import AsyncIterator

import aiohttp
from yarl import URL
from multidict import CIMultiDict, CIMultiDictProxy


class FakeStreamContent:
    def __init__(self, data: bytes):
        self._data = data

    async def iter_chunked(self, _size: int) -> AsyncIterator[bytes]:
        if self._data:
            yield self._data


class FakeResponse:
    def __init__(
        self,
        status: int = 200,
        *,
        headers: dict[str, str] | None = None,
        payload: dict[str, Any] | None = None,
        body: bytes | None = None,
    ):
        self.status = status
        self._headers = headers or {}
        self._payload = payload
        if body is not None:
            self._body = body
        elif payload is not None:
            self._body = b'{}'
        else:
            self._body = b''
        self.content = FakeStreamContent(self._body)

    @property
    def headers(self) -> dict[str, str]:
        return self._headers

    def raise_for_status(self) -> None:
        if self.status >= 400:
            request_info = aiohttp.RequestInfo(
                URL(),
                'GET',
                cast(CIMultiDictProxy[str], CIMultiDict()),
            )
            raise aiohttp.ClientResponseError(
                request_info=request_info,
                history=(),
                status=self.status,
                message='boom',
            )

    async def read(self) -> bytes:
        return self._body

    async def json(self, content_type: str | None = None) -> Any:
        return self._payload


class FakeGet:
    def __init__(self, response: FakeResponse):
        self._response = response

    async def __aenter__(self) -> FakeResponse:
        return self._response

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


class FakeSession:
    """顺序消费预设响应的假 ClientSession。"""

    def __init__(self, *responses: FakeResponse):
        self._responses = list(responses)
        self.get_calls: list[dict[str, Any]] = []
        self.post_calls: list[dict[str, Any]] = []
        self.closed = False

    def get(self, url: str, **kwargs: Any) -> FakeGet:
        self.get_calls.append({'url': url, **kwargs})
        if not self._responses:
            raise AssertionError(f'unexpected GET: {url}')
        return FakeGet(self._responses.pop(0))

    def post(self, url: str, **kwargs: Any) -> FakeGet:
        self.post_calls.append({'url': url, **kwargs})
        if not self._responses:
            raise AssertionError(f'unexpected POST: {url}')
        return FakeGet(self._responses.pop(0))

    async def close(self) -> None:
        self.closed = True


class FakeClientSessionFactory:
    def __init__(self, session: FakeSession):
        self._session = session
        self.calls = 0

    def __call__(self, *args: Any, **kwargs: Any) -> FakeSessionCM:
        self.calls += 1
        return FakeSessionCM(self._session)


class FakeSessionCM:
    def __init__(self, session: FakeSession):
        self._session = session

    async def __aenter__(self) -> FakeSession:
        return self._session

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


class FakeBot:
    def __init__(self, self_id: str = '10001'):
        self.self_id = self_id
        self.sent: list[Any] = []
        self.group_msgs: list[dict[str, Any]] = []
        self.api_calls: list[dict[str, Any]] = []

    async def send(self, event: Any, message: Any) -> None:
        self.sent.append((event, message))

    async def send_group_msg(self, *, group_id: int, message: Any) -> None:
        self.group_msgs.append({'group_id': group_id, 'message': message})

    async def call_api(self, api: str, **data: Any) -> dict[str, Any]:
        self.api_calls.append({'api': api, **data})
        if api == 'upload_file_stream' and data.get('is_complete'):
            return {'file_path': f'/tmp/uploaded-{data.get("stream_id", "x")}'}
        return {}
