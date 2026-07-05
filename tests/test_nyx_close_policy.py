import unittest
from unittest import mock

from core import task_runner


class _Logger:
    def __init__(self):
        self.messages = []

    def info(self, message):
        self.messages.append(("info", message))

    def warning(self, message):
        self.messages.append(("warning", message))


class _Manager:
    def __init__(self):
        self.closed = []

    def open_profile(self, profile_id):
        return "ws://127.0.0.1/devtools/browser/test"

    def close_profile(self, profile_id):
        self.closed.append(profile_id)
        return {"code": 0}


def _creator_factory(*, success=False, last_result="normal", exc=None):
    class _Creator:
        def __init__(self, _endpoint, _logger):
            self.last_result = last_result

        async def start(self):
            return None

        async def run(self, *_args, **_kwargs):
            self.last_result = last_result
            if exc is not None:
                raise exc
            return success

    return _Creator


class NyxClosePolicyTests(unittest.IsolatedAsyncioTestCase):
    async def _run_with_creator(self, creator_cls, **kwargs):
        manager = _Manager()
        logger = _Logger()
        with mock.patch.object(task_runner, "BitmojiCreator", creator_cls), \
                mock.patch.object(task_runner, "PROFILE_START_STAGGER_SECONDS", 0.0):
            result = await task_runner.run_profile_task(
                "k1test",
                "Chloe",
                logger,
                adspower=manager,
                **kwargs,
            )
        return result, manager, logger

    async def test_success_closes_profile(self):
        result, manager, _logger = await self._run_with_creator(
            _creator_factory(success=True, last_result="normal")
        )

        self.assertEqual(result, (True, "normal"))
        self.assertEqual(manager.closed, ["k1test"])

    async def test_unexpected_false_result_leaves_profile_open(self):
        result, manager, logger = await self._run_with_creator(
            _creator_factory(success=False, last_result="normal")
        )

        self.assertEqual(result, (False, "normal"))
        self.assertEqual(manager.closed, [])
        self.assertTrue(any("did not finish cleanly" in msg for _level, msg in logger.messages))

    async def test_unexpected_exception_leaves_profile_open(self):
        manager = _Manager()
        logger = _Logger()
        creator_cls = _creator_factory(
            success=False,
            last_result="normal",
            exc=RuntimeError("selector failed"),
        )
        with mock.patch.object(task_runner, "BitmojiCreator", creator_cls), \
                mock.patch.object(task_runner, "PROFILE_START_STAGGER_SECONDS", 0.0):
            with self.assertRaises(RuntimeError):
                await task_runner.run_profile_task(
                    "k1test",
                    "Chloe",
                    logger,
                    adspower=manager,
                )

        self.assertEqual(manager.closed, [])
        self.assertTrue(any("did not finish cleanly" in msg for _level, msg in logger.messages))

    async def test_terminal_proxy_error_still_closes_profile(self):
        result, manager, _logger = await self._run_with_creator(
            _creator_factory(success=False, last_result="proxy_error")
        )

        self.assertEqual(result, (False, "proxy_error"))
        self.assertEqual(manager.closed, ["k1test"])

    async def test_env_can_restore_close_on_failure(self):
        creator_cls = _creator_factory(success=False, last_result="normal")
        with mock.patch.dict("os.environ", {"NYX_CLOSE_PROFILE_ON_FAILURE": "1"}):
            result, manager, _logger = await self._run_with_creator(creator_cls)

        self.assertEqual(result, (False, "normal"))
        self.assertEqual(manager.closed, ["k1test"])


if __name__ == "__main__":
    unittest.main()
