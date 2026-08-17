# Run: py -3 -m unittest tests.test_fal_common_logic
# Pure-logic tests for fal_common subscribe retry and download timeout (no network).

from __future__ import print_function

import os
import sys
import tempfile
import types
import unittest
import urllib.error

_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
_PYTHON_DIR = os.path.join(_ROOT, "nuke", "python")
if _PYTHON_DIR not in sys.path:
    sys.path.insert(0, _PYTHON_DIR)

import fal_common


class FalClientHTTPError(Exception):
    def __init__(self, message, status_code=None):
        Exception.__init__(self, message)
        self.status_code = status_code


class _FakeClient(object):
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def subscribe(self, endpoint_id, arguments=None):
        self.calls.append((endpoint_id, arguments))
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


class TestSubscribeWithRetry(unittest.TestCase):
    def setUp(self):
        self._old_sleep = fal_common.time.sleep
        fal_common.time.sleep = lambda _s: None
        self._old_random = fal_common.random.random
        fal_common.random.random = lambda: 0.5
        self._install_fake_fal_client()

    def tearDown(self):
        fal_common.time.sleep = self._old_sleep
        fal_common.random.random = self._old_random
        self._restore_fal_client()

    def _install_fake_fal_client(self):
        self._prev_fal = sys.modules.get("fal_client")
        self._prev_fal_client = sys.modules.get("fal_client.client")
        fake_pkg = types.ModuleType("fal_client")
        fake_client = types.ModuleType("fal_client.client")
        fake_client.FalClientHTTPError = FalClientHTTPError
        sys.modules["fal_client"] = fake_pkg
        sys.modules["fal_client.client"] = fake_client

    def _restore_fal_client(self):
        if self._prev_fal is None:
            sys.modules.pop("fal_client", None)
        else:
            sys.modules["fal_client"] = self._prev_fal
        if self._prev_fal_client is None:
            sys.modules.pop("fal_client.client", None)
        else:
            sys.modules["fal_client.client"] = self._prev_fal_client

    def test_retries_retryable_error_then_succeeds(self):
        client = _FakeClient(
            [
                FalClientHTTPError("internal server error 500 ", status_code=500),
                {"ok": True},
            ]
        )
        result = fal_common.subscribe_with_retry(
            client,
            "fal-ai/example",
            {"prompt": "x"},
            max_retries=3,
            retry_base_seconds=0.25,
        )
        self.assertEqual(result, {"ok": True})
        self.assertEqual(len(client.calls), 2)

    def test_non_retryable_error_does_not_loop(self):
        client = _FakeClient(
            [
                FalClientHTTPError("bad request", status_code=400),
                {"ok": True},
            ]
        )
        with self.assertRaises(FalClientHTTPError):
            fal_common.subscribe_with_retry(
                client,
                "fal-ai/example",
                {"prompt": "x"},
                max_retries=3,
                retry_base_seconds=0.25,
            )
        self.assertEqual(len(client.calls), 1)

    def test_other_exception_does_not_retry(self):
        client = _FakeClient([ValueError("boom"), {"ok": True}])
        with self.assertRaises(ValueError):
            fal_common.subscribe_with_retry(
                client,
                "fal-ai/example",
                {"prompt": "x"},
                max_retries=3,
                retry_base_seconds=0.25,
            )
        self.assertEqual(len(client.calls), 1)

    def test_max_retries_three_means_four_tries(self):
        err = FalClientHTTPError("internal server error 500 ", status_code=500)
        client = _FakeClient([err, err, err, err, {"ok": True}])
        with self.assertRaises(FalClientHTTPError):
            fal_common.subscribe_with_retry(
                client,
                "fal-ai/example",
                {},
                max_retries=3,
                retry_base_seconds=0.25,
            )
        self.assertEqual(len(client.calls), 4)


class _FakeResponse(object):
    def __init__(self, payload, fail_reads=0):
        self._payload = payload
        self._fail_reads = fail_reads
        self._sent = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self, _size):
        if self._fail_reads > 0:
            self._fail_reads -= 1
            raise OSError("read failed")
        if self._sent:
            return b""
        self._sent = True
        return self._payload


class TestDownloadRetry(unittest.TestCase):
    def setUp(self):
        self._old_sleep = fal_common.time.sleep
        fal_common.time.sleep = lambda _s: None
        self._old_random = fal_common.random.random
        fal_common.random.random = lambda: 0.5
        self._old_urlopen = fal_common.urllib.request.urlopen
        self._urlopen_calls = []

    def tearDown(self):
        fal_common.time.sleep = self._old_sleep
        fal_common.random.random = self._old_random
        fal_common.urllib.request.urlopen = self._old_urlopen

    def test_retries_urlerror_then_succeeds(self):
        payload = b"hello-image"

        def fake_urlopen(req, timeout=None):
            self._urlopen_calls.append(timeout)
            if len(self._urlopen_calls) == 1:
                raise urllib.error.URLError("timed out")
            return _FakeResponse(payload)

        fal_common.urllib.request.urlopen = fake_urlopen
        with tempfile.TemporaryDirectory() as td:
            out_path = os.path.join(td, "out.bin")
            fal_common.download("http://example.invalid/file", out_path, user_agent="test")
            with open(out_path, "rb") as f:
                self.assertEqual(f.read(), payload)
            self.assertFalse(os.path.exists(out_path + ".part"))
        self.assertEqual(self._urlopen_calls, [60, 60])

    def test_timeout_is_passed_to_urlopen(self):
        def fake_urlopen(req, timeout=None):
            self._urlopen_calls.append(timeout)
            return _FakeResponse(b"x")

        fal_common.urllib.request.urlopen = fake_urlopen
        with tempfile.TemporaryDirectory() as td:
            out_path = os.path.join(td, "out.bin")
            fal_common.download(
                "http://example.invalid/file",
                out_path,
                user_agent="test",
                timeout_seconds=12,
            )
        self.assertEqual(self._urlopen_calls, [12])


if __name__ == "__main__":
    unittest.main()
