"""BOMI operator console for safe Scenario cancellation and mode recovery."""

from __future__ import annotations

import os

import streamlit as st

from api_client import OperatorApiClient, OperatorApiError


DEFAULT_DEVICE_ID = "bomi-AA001"


def _client() -> OperatorApiClient:
    return OperatorApiClient(
        os.getenv("BOMI_BACKEND_URL", "http://localhost:8080"),
        os.getenv("OPERATOR_SHARED_SECRET", ""),
    )


def _show_flash() -> None:
    flash = st.session_state.pop("flash", None)
    if not flash:
        return
    kind, message = flash
    getattr(st, kind)(message)


def _show_error(error: Exception) -> None:
    if isinstance(error, OperatorApiError):
        prefix = f"HTTP {error.status}: " if error.status is not None else ""
        st.error(prefix + str(error))
    else:
        st.error(str(error))


def _scenario_label(scenario: dict) -> str:
    target = scenario.get("navigationTarget") or "이동 명령 없음"
    return f"{scenario.get('scenarioType', '-')} · {scenario.get('status', '-')} · {target}"


def main() -> None:
    st.set_page_config(page_title="BOMI 운영자 콘솔", page_icon="🛡️", layout="wide")
    st.title("🛡️ BOMI 운영자 콘솔")
    st.caption("진행 중인 내비게이션을 안전하게 취소하고 Robot mode를 복구합니다.")
    _show_flash()

    try:
        client = _client()
    except ValueError as error:
        st.error(str(error))
        st.info("EC2 서버 환경변수에 OPERATOR_SHARED_SECRET을 설정한 뒤 다시 실행하세요.")
        st.stop()

    with st.sidebar:
        st.header("대상 Robot")
        device_id = st.text_input("Device ID", DEFAULT_DEVICE_ID).strip()
        st.button("상태 새로고침", use_container_width=True)
        st.divider()
        st.caption("운영 API Secret은 서버 환경변수에서만 읽으며 화면에 표시하지 않습니다.")

    if not device_id:
        st.warning("Robot Device ID를 입력하세요.")
        st.stop()

    try:
        state = client.runtime_state(device_id)
    except (OperatorApiError, ValueError) as error:
        _show_error(error)
        st.stop()

    mode = state.get("currentMode", "UNKNOWN")
    scenarios = state.get("activeScenarios") or []
    robot_active = bool(state.get("active"))

    mode_column, active_column, scenario_column, occupancy_column = st.columns(4)
    mode_column.metric("Robot mode", mode)
    active_column.metric("Robot 활성", "활성" if robot_active else "비활성")
    scenario_column.metric("활성 Scenario", len(scenarios))
    occupancy_column.metric("재실 상태", state.get("occupancyStatus", "UNKNOWN"))

    if mode == "SAFE_STOP":
        st.warning("Robot이 SAFE_STOP 상태입니다. 실제 정지를 확인한 뒤에만 IDLE로 복구하세요.")
    elif mode == "IDLE":
        st.success("Robot이 IDLE 상태입니다.")
    else:
        st.info(f"현재 Robot mode: {mode}")

    st.subheader("활성 Scenario")
    if scenarios:
        for scenario in scenarios:
            with st.container(border=True):
                st.markdown(f"**{_scenario_label(scenario)}**")
                st.caption(
                    f"Scenario ID: {scenario.get('scenarioId', '-')}  ·  "
                    f"Command ID: {scenario.get('navigationCommandId') or '-'}"
                )
    else:
        st.write("활성 Scenario가 없습니다.")

    cancel_column, recovery_column = st.columns(2, gap="large")

    with cancel_column:
        st.subheader("1. 진행 중 내비게이션 취소")
        st.write("CANCEL 명령을 발행하고 Scenario를 CANCELLED, Robot을 SAFE_STOP으로 변경합니다.")
        cancel_reason = st.text_area(
            "취소 사유",
            "멈춘 내비게이션 시나리오 운영자 취소",
            key="cancel_reason",
            max_chars=500,
        )
        cancel_confirmed = st.checkbox(
            "로봇 주변과 이동 경로의 물리적 안전을 확인했습니다.",
            key="cancel_confirmed",
        )
        cancellable = any(item.get("navigationCommandId") for item in scenarios)
        if st.button(
            "진행 중 내비게이션 취소",
            type="primary",
            use_container_width=True,
            disabled=not (robot_active and cancellable and cancel_confirmed and cancel_reason.strip()),
        ):
            try:
                result = client.cancel_active_scenario(device_id, cancel_reason.strip())
                st.session_state.flash = (
                    "success",
                    f"{result.get('disposition')}: {result.get('message', '취소 요청 완료')}",
                )
                st.rerun()
            except (OperatorApiError, ValueError) as error:
                _show_error(error)

        if scenarios and not cancellable:
            st.caption("현재 Scenario에는 취소할 활성 내비게이션 명령이 없습니다.")

    with recovery_column:
        st.subheader("2. SAFE_STOP → IDLE 복구")
        st.write("Jetson/Nav2에서 Robot이 실제로 정지한 것을 확인한 뒤 실행합니다.")
        recovery_reason = st.text_area(
            "복구 사유",
            "CANCEL 처리 및 Robot 정지 확인",
            key="recovery_reason",
            max_chars=500,
        )
        recovery_confirmed = st.checkbox(
            "Robot의 실제 정지와 주변 안전을 다시 확인했습니다.",
            key="recovery_confirmed",
        )
        recoverable = mode in {"SAFE_STOP", "SCENARIO_ACTIVE", "IDLE"} and not scenarios
        if st.button(
            "IDLE로 복구",
            use_container_width=True,
            disabled=not (robot_active and recoverable and recovery_confirmed and recovery_reason.strip()),
        ):
            try:
                result = client.recover_to_idle(device_id, recovery_reason.strip())
                st.session_state.flash = (
                    "success",
                    f"{result.get('disposition')}: {result.get('message', '복구 완료')}",
                )
                st.rerun()
            except (OperatorApiError, ValueError) as error:
                _show_error(error)

        if scenarios:
            st.caption("활성 Scenario를 먼저 취소해야 IDLE 복구가 가능합니다.")


if __name__ == "__main__":
    main()
