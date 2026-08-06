"""MQTT callback 밖에서 NAVIGATE를 한 번에 하나만 실행하는 경계를 검증한다."""

import threading

from bridge.mqtt_client import SingleFlightExecutor


def test_submit_runs_in_worker_and_rejects_second_task() -> None:
    executor = SingleFlightExecutor()
    started = threading.Event()
    release = threading.Event()
    finished = threading.Event()

    def task() -> None:
        started.set()
        release.wait(timeout=1.0)
        finished.set()

    assert executor.submit(task) is True
    assert started.wait(timeout=1.0)
    assert executor.submit(lambda: None) is False

    release.set()
    executor.shutdown()

    assert finished.is_set()


def test_shutdown_rejects_new_tasks() -> None:
    executor = SingleFlightExecutor()
    executor.shutdown()

    assert executor.submit(lambda: None) is False
