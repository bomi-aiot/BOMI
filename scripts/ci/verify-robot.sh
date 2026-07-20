#!/usr/bin/env bash
set -Eeuo pipefail

readonly SOURCE_DIR="${BOMI_SOURCE_DIR:-$(git rev-parse --show-toplevel)}"
readonly ROBOT_DIR="$SOURCE_DIR/robot"
[[ -d "$ROBOT_DIR" ]] || { echo '[verify-robot] robot/ directory is missing' >&2; exit 1; }

docker run --rm \
  --volume "$ROBOT_DIR:/workspace:ro" \
  --env PYTHONPYCACHEPREFIX=/tmp/pycache \
  python:3.10-slim \
  sh -ec '
    python -m compileall -q /workspace
    if [ -f /workspace/requirements.txt ]; then
      python -m venv /venv
      /venv/bin/pip install --quiet -r /workspace/requirements.txt
    fi
  '

if find "$ROBOT_DIR/ros2_ws/src" -name package.xml -print -quit 2>/dev/null | grep -q .; then
  docker run --rm \
    --volume "$ROBOT_DIR/ros2_ws:/workspace:ro" \
    ros:humble-ros-base \
    bash -ec '
      apt-get update -qq
      apt-get install -y -qq python3-colcon-common-extensions >/dev/null
      cp -a /workspace /build_ws
      cd /build_ws
      source /opt/ros/humble/setup.bash
      colcon build --event-handlers console_direct+
    '
else
  echo '[verify-robot] No ROS 2 packages yet; colcon build skipped'
fi
