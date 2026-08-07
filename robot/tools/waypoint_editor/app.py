"""저장된 ROS 지도 위에서 순찰 웨이포인트를 편집하는 Streamlit 앱이다."""

from __future__ import annotations

import base64
from io import BytesIO
import math
from pathlib import Path
import shutil

from PIL import Image, ImageDraw
import streamlit as st

from waypoint_editor.model import (
    MapMetadata,
    Waypoint,
    WaypointEditorError,
    dump_waypoint_document,
    load_map_metadata,
    load_waypoint_document,
    pixel_to_world,
    world_to_pixel,
)


APP_DIR = Path(__file__).resolve().parent
REPOSITORY_ROOT = APP_DIR.parents[1]
MAPS_DIR = REPOSITORY_ROOT / "ros2_ws" / "src" / "mapping" / "maps"
DEFAULT_WAYPOINT_FILE = (
    REPOSITORY_ROOT / "ros2_ws" / "src" / "core" / "config" / "room_waypoints.yaml"
)
MAX_DISPLAY_WIDTH = 900

IMAGE_CLICKER_HTML = """
<img class="waypoint-map" alt="클릭해서 웨이포인트를 지정할 지도" />
"""

IMAGE_CLICKER_CSS = """
.waypoint-map {
    display: block;
    width: 100%;
    height: auto;
    image-rendering: pixelated;
    cursor: crosshair;
    border: 1px solid var(--st-border-color);
    border-radius: 0.5rem;
}
"""

IMAGE_CLICKER_JS = """
export default function(component) {
    const { data, parentElement, setTriggerValue } = component;
    const image = parentElement.querySelector('.waypoint-map');
    image.src = data.source;

    image.onclick = (event) => {
        const bounds = image.getBoundingClientRect();
        const x = (event.clientX - bounds.left) * image.naturalWidth / bounds.width;
        const y = (event.clientY - bounds.top) * image.naturalHeight / bounds.height;
        setTriggerValue('clicked', { x, y, timestamp: Date.now() });
    };
}
"""

image_clicker = st.components.v2.component(
    "bomi_waypoint_image_clicker",
    html=IMAGE_CLICKER_HTML,
    css=IMAGE_CLICKER_CSS,
    js=IMAGE_CLICKER_JS,
)


def _load_editor_document(path: Path) -> None:
    """선택한 웨이포인트 문서를 세션 편집 상태로 불러온다."""

    waypoints, options = load_waypoint_document(path)
    st.session_state.waypoints = waypoints
    st.session_state.patrol_options = options
    st.session_state.loaded_waypoint_path = str(path.resolve())
    st.session_state.editing_waypoint_index = None


def _make_overlay(
    image: Image.Image,
    metadata: MapMetadata,
    waypoints: list[Waypoint],
) -> tuple[Image.Image, float]:
    """웨이포인트 위치와 방향 화살표가 표시된 클릭용 이미지를 만든다."""

    # SLAM 지도는 실측 지도도 100~200px 정도로 작다. 원본에 표식을 그린 뒤
    # 브라우저에서 확대하면 글자와 선 굵기까지 수십 배 커지므로, 먼저 화면용
    # 해상도로 지도를 확대한 다음 고정 크기의 표식을 그린다.
    scale = MAX_DISPLAY_WIDTH / image.width
    display_size = (
        max(1, round(image.width * scale)),
        max(1, round(image.height * scale)),
    )
    overlay = image.convert("RGB").resize(display_size, Image.Resampling.NEAREST)
    draw = ImageDraw.Draw(overlay)
    for index, waypoint in enumerate(waypoints, start=1):
        pixel_x, pixel_y = world_to_pixel(
            waypoint.x, waypoint.y, image.height, metadata
        )
        x = pixel_x * scale
        y = pixel_y * scale
        radius = 9
        color = "#e11d48"
        arrow_length = 34
        end_x = x + arrow_length * math.cos(waypoint.yaw - metadata.origin_yaw)
        end_y = y - arrow_length * math.sin(waypoint.yaw - metadata.origin_yaw)
        draw.line((x, y, end_x, end_y), fill="#2563eb", width=3)
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=color)
        draw.text((x, y), str(index), fill="white", anchor="mm")
    return overlay, scale


def _image_data_url(image: Image.Image) -> str:
    """신뢰하는 로컬 지도 이미지를 브라우저에 전달할 PNG data URL로 만든다."""

    buffer = BytesIO()
    image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _move_waypoint(index: int, offset: int) -> None:
    """선택한 웨이포인트의 순찰 순서를 한 칸 이동한다."""

    destination = index + offset
    waypoints = st.session_state.waypoints
    if 0 <= destination < len(waypoints):
        waypoints[index], waypoints[destination] = waypoints[destination], waypoints[index]


def _render_waypoint_edit_form(index: int, waypoints: list[Waypoint]) -> None:
    """선택한 카드 안에서 이름과 방향을 바로 편집한다."""

    selected = waypoints[index]
    with st.form(f"edit-waypoint-form-{index}"):
        edited_name = st.text_input("이름", selected.name)
        edited_yaw = st.slider(
            "바라볼 방향",
            -180,
            180,
            int(round(math.degrees(selected.yaw))),
            5,
            format="%d°",
        )
        apply_edit, cancel_edit = st.columns(2)
        save_edit = apply_edit.form_submit_button(
            "변경 적용", type="primary", use_container_width=True
        )
        cancel = cancel_edit.form_submit_button("취소", use_container_width=True)

    if cancel:
        st.session_state.editing_waypoint_index = None
        st.rerun()
    if save_edit:
        name = edited_name.strip()
        duplicate = any(
            waypoint_index != index and item.name == name
            for waypoint_index, item in enumerate(waypoints)
        )
        if not name or duplicate:
            st.error("비어 있거나 중복된 이름은 사용할 수 없습니다.")
        else:
            waypoints[index] = Waypoint(
                name, selected.x, selected.y, math.radians(edited_yaw)
            )
            st.session_state.editing_waypoint_index = None
            st.rerun()


def main() -> None:
    """지도 선택부터 YAML 저장까지 웨이포인트 편집 화면을 구성한다."""

    st.set_page_config(page_title="BOMI 웨이포인트 편집기", page_icon="🗺️", layout="wide")
    st.title("BOMI 웨이포인트 편집기")
    st.caption("저장된 지도에서 위치를 클릭하고 로봇이 바라볼 방향을 지정하세요.")

    map_files = sorted(MAPS_DIR.glob("*.yaml"))
    if not map_files:
        st.error(f"지도 YAML이 없습니다: {MAPS_DIR}")
        st.stop()

    with st.sidebar:
        st.header("파일")
        selected_map = st.selectbox(
            "지도",
            map_files,
            format_func=lambda path: path.name,
        )
        waypoint_text = st.text_input("웨이포인트 YAML", str(DEFAULT_WAYPOINT_FILE))
        waypoint_path = Path(waypoint_text).expanduser()
        if not waypoint_path.is_absolute():
            waypoint_path = REPOSITORY_ROOT / waypoint_path

        if st.button("웨이포인트 다시 불러오기", use_container_width=True):
            try:
                _load_editor_document(waypoint_path)
                st.success("불러왔습니다.")
            except WaypointEditorError as error:
                st.error(str(error))

    try:
        metadata = load_map_metadata(selected_map)
        source_image = Image.open(metadata.image_path)
        source_image.load()
        map_key = str(metadata.yaml_path)
        if st.session_state.get("loaded_map_path") != map_key:
            st.session_state.loaded_map_path = map_key
            st.session_state.pending_position = None
        document_key = str(waypoint_path.resolve())
        if st.session_state.get("loaded_waypoint_path") != document_key:
            _load_editor_document(waypoint_path)
    except (OSError, WaypointEditorError) as error:
        st.error(str(error))
        st.stop()

    waypoints: list[Waypoint] = st.session_state.waypoints
    map_column, controls_column = st.columns([3, 2], gap="large")

    with map_column:
        st.subheader("지도")
        st.caption("빨간 번호는 순찰 순서, 파란 선은 로봇이 바라볼 방향입니다.")
        overlay, display_scale = _make_overlay(source_image, metadata, waypoints)
        click_result = image_clicker(
            data={"source": _image_data_url(overlay)},
            width="stretch",
            height="content",
            key=f"map-click-{selected_map.name}-{len(waypoints)}",
            on_clicked_change=lambda: None,
        )
        click = click_result.clicked
        if click is not None:
            original_x = float(click["x"]) / display_scale
            original_y = float(click["y"]) / display_scale
            world_x, world_y = pixel_to_world(
                original_x, original_y, source_image.height, metadata
            )
            st.session_state.pending_position = (world_x, world_y)

        pending = st.session_state.get("pending_position")
        if pending:
            st.info(f"선택 위치: x={pending[0]:.3f} m, y={pending[1]:.3f} m")
        else:
            st.info("지도에서 새 웨이포인트 위치를 클릭하세요.")

    with controls_column:
        add_tab, route_tab = st.tabs(["새 지점", f"순찰 순서 ({len(waypoints)})"])
        with add_tab:
            new_name = st.text_input("이름", placeholder="예: living_room_search")
            yaw_degrees = st.slider("바라볼 방향", -180, 180, 0, 5, format="%d°")
            if st.button("선택 위치 추가", type="primary", use_container_width=True):
                pending = st.session_state.get("pending_position")
                if pending is None:
                    st.error("먼저 지도에서 위치를 클릭하세요.")
                elif not new_name.strip():
                    st.error("웨이포인트 이름을 입력하세요.")
                elif any(item.name == new_name.strip() for item in waypoints):
                    st.error("같은 이름의 웨이포인트가 이미 있습니다.")
                else:
                    waypoints.append(
                        Waypoint(
                            new_name.strip(),
                            pending[0],
                            pending[1],
                            math.radians(yaw_degrees),
                        )
                    )
                    st.session_state.pending_position = None
                    st.rerun()

        with route_tab:
            st.caption("위에서 아래 순서로 이동합니다.")
            if not waypoints:
                st.write("등록된 웨이포인트가 없습니다.")
            else:
                with st.container(height=620, border=False):
                    for index, waypoint in enumerate(waypoints):
                        with st.container(border=True):
                            info, up, down, edit, remove = st.columns(
                                [3.4, 1, 1, 1.1, 1.1], vertical_alignment="center"
                            )
                            info.markdown(
                                f"**{index + 1}. {waypoint.name}**  \n"
                                f"`{waypoint.x:.2f}, {waypoint.y:.2f}` · "
                                f"`{math.degrees(waypoint.yaw):.0f}°`"
                            )
                            if up.button(
                                "↑",
                                key=f"move-up-{index}",
                                help="한 단계 위로",
                                use_container_width=True,
                                disabled=index == 0,
                            ):
                                _move_waypoint(index, -1)
                                st.session_state.editing_waypoint_index = None
                                st.rerun()
                            if down.button(
                                "↓",
                                key=f"move-down-{index}",
                                help="한 단계 아래로",
                                use_container_width=True,
                                disabled=index == len(waypoints) - 1,
                            ):
                                _move_waypoint(index, 1)
                                st.session_state.editing_waypoint_index = None
                                st.rerun()
                            if edit.button(
                                "편집",
                                key=f"edit-{index}",
                                use_container_width=True,
                            ):
                                st.session_state.editing_waypoint_index = index
                                st.rerun()
                            with remove.popover("삭제", use_container_width=True):
                                st.write(f"**{waypoint.name}** 지점을 삭제할까요?")
                                if st.button(
                                    "삭제 확인",
                                    key=f"confirm-remove-{index}",
                                    type="primary",
                                    use_container_width=True,
                                ):
                                    waypoints.pop(index)
                                    st.session_state.editing_waypoint_index = None
                                    st.rerun()

                            if st.session_state.get("editing_waypoint_index") == index:
                                _render_waypoint_edit_form(index, waypoints)

    st.divider()
    yaml_text = dump_waypoint_document(waypoints, st.session_state.patrol_options)
    save_column, download_column = st.columns(2)
    if save_column.button("room_waypoints.yaml에 저장", type="primary", use_container_width=True):
        try:
            backup_path = waypoint_path.with_suffix(waypoint_path.suffix + ".bak")
            if waypoint_path.exists():
                shutil.copy2(waypoint_path, backup_path)
            waypoint_path.write_text(yaml_text, encoding="utf-8")
            st.success(f"저장했습니다. 이전 파일: {backup_path.name}")
        except OSError as error:
            st.error(f"저장하지 못했습니다: {error}")
    download_column.download_button(
        "YAML 다운로드",
        yaml_text,
        file_name=waypoint_path.name,
        mime="application/x-yaml",
        use_container_width=True,
    )
    with st.expander("생성될 YAML 미리보기"):
        st.code(yaml_text, language="yaml")


if __name__ == "__main__":
    main()
