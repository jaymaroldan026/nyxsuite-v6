import sys
import types
import unittest
from unittest import mock


class _RequestsResponse:
    status_code = 200
    ok = True
    text = "{}"

    def json(self):
        return {}

    def raise_for_status(self):
        return None


class _RequestsSession:
    def __init__(self):
        self.trust_env = False

    def get(self, *_args, **_kwargs):
        return _RequestsResponse()

    def post(self, *_args, **_kwargs):
        return _RequestsResponse()


_requests_stub = types.ModuleType("requests")
_requests_stub.Session = _RequestsSession
_requests_stub.get = lambda *_args, **_kwargs: _RequestsResponse()
_requests_stub.post = lambda *_args, **_kwargs: _RequestsResponse()
_requests_stub.exceptions = types.SimpleNamespace(
    ConnectionError=ConnectionError,
    Timeout=TimeoutError,
    RequestException=Exception,
)
sys.modules.setdefault("requests", _requests_stub)
sys.modules.setdefault("dotenv", types.SimpleNamespace(load_dotenv=lambda *_args, **_kwargs: None))
_playwright_pkg = types.ModuleType("playwright")
_playwright_async_api = types.ModuleType("playwright.async_api")
_playwright_async_api.async_playwright = lambda: None
_playwright_async_api.TimeoutError = TimeoutError
sys.modules.setdefault("playwright", _playwright_pkg)
sys.modules.setdefault("playwright.async_api", _playwright_async_api)

import nyxify_runner


class Response:
    def __init__(self, payload=None, ok=True, status_code=200):
        self._payload = payload or {}
        self.ok = ok
        self.status_code = status_code

    def json(self):
        return dict(self._payload)


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        return self.now

    async def sleep(self, seconds):
        self.now += float(seconds)


class BridgeValueWaitTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._old_token = nyxify_runner.NYXIFY_LOCAL_API_TOKEN
        self._old_cached = nyxify_runner._LOCAL_API_TOKEN_CACHED
        nyxify_runner.NYXIFY_LOCAL_API_TOKEN = "token"
        nyxify_runner._LOCAL_API_TOKEN_CACHED = True
        self.addCleanup(self._restore_token)

    def _restore_token(self):
        nyxify_runner.NYXIFY_LOCAL_API_TOKEN = self._old_token
        nyxify_runner._LOCAL_API_TOKEN_CACHED = self._old_cached

    async def test_email_terminal_bridge_error_returns_after_first_status_result(self):
        clock = FakeClock()
        status_calls = []

        def fake_get(url, **_kwargs):
            status_calls.append(url)
            return Response({"ok": True, "done": True, "email": "", "error": "No pending email order."})

        with mock.patch.object(nyxify_runner._requests, "post", return_value=Response({"ok": True})), \
            mock.patch.object(nyxify_runner._requests, "get", side_effect=fake_get), \
            mock.patch.object(nyxify_runner.time, "monotonic", side_effect=clock.monotonic), \
            mock.patch.object(nyxify_runner.asyncio, "sleep", side_effect=clock.sleep):
            email = await nyxify_runner._request_snapboard_email("snapboard:1", timeout_seconds=30)

        self.assertEqual(email, "")
        self.assertEqual(len(status_calls), 1)
        self.assertLess(clock.now, 2)

    async def test_phone_returns_when_bridge_never_dispatches_request(self):
        clock = FakeClock()
        status_calls = []

        def fake_get(_url, **_kwargs):
            status_calls.append(_kwargs)
            return Response({
                "ok": True,
                "done": False,
                "requested": True,
                "dispatched": False,
                "age_seconds": 12,
            })

        with mock.patch.object(nyxify_runner._requests, "post", return_value=Response({"ok": True})), \
            mock.patch.object(nyxify_runner._requests, "get", side_effect=fake_get), \
            mock.patch.object(nyxify_runner.time, "monotonic", side_effect=clock.monotonic), \
            mock.patch.object(nyxify_runner.asyncio, "sleep", side_effect=clock.sleep):
            phone = await nyxify_runner._request_snapboard_phone("snapboard:1", timeout_seconds=120)

        self.assertEqual(phone, "")
        self.assertEqual(len(status_calls), 1)
        self.assertLess(clock.now, 2)

    async def test_email_request_refreshes_stale_token_after_unauthorized_response(self):
        post_headers = []

        def fake_post(_url, json=None, headers=None, **_kwargs):
            post_headers.append(dict(headers or {}))
            token = (headers or {}).get("X-Nyxify-Token")
            if token == "stale":
                return Response({"ok": False, "error": "Unauthorized request."}, ok=False, status_code=401)
            self.assertEqual(json.get("token"), "fresh")
            return Response({"ok": True})

        def fake_get(url, **_kwargs):
            if url.endswith("/token"):
                return Response({"ok": True, "token": "fresh"})
            return Response({"ok": True, "done": True, "email": "fresh@example.com"})

        nyxify_runner.NYXIFY_LOCAL_API_TOKEN = "stale"
        nyxify_runner._LOCAL_API_TOKEN_CACHED = True

        with mock.patch.object(nyxify_runner._requests, "post", side_effect=fake_post), \
            mock.patch.object(nyxify_runner._requests, "get", side_effect=fake_get), \
            mock.patch.object(nyxify_runner.asyncio, "sleep", new=mock.AsyncMock()):
            email = await nyxify_runner._request_snapboard_email("snapboard:1", timeout_seconds=30)

        self.assertEqual(email, "fresh@example.com")
        self.assertEqual(
            [headers.get("X-Nyxify-Token") for headers in post_headers],
            ["stale", "fresh"],
        )


if __name__ == "__main__":
    unittest.main()
