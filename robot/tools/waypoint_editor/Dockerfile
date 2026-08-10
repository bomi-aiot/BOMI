FROM python:3.12-slim

WORKDIR /app
COPY tools/waypoint_editor/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt \
    && useradd --create-home --uid 10002 waypoint-editor

COPY --chown=waypoint-editor:waypoint-editor tools/waypoint_editor /app/tools/waypoint_editor
COPY --chown=waypoint-editor:waypoint-editor ros2_ws/src/mapping/maps /app/ros2_ws/src/mapping/maps
COPY --chown=waypoint-editor:waypoint-editor \
    ros2_ws/src/core/config/room_waypoints.yaml \
    /app/ros2_ws/src/core/config/room_waypoints.yaml

WORKDIR /app/tools/waypoint_editor
EXPOSE 8501
USER waypoint-editor
CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501"]
