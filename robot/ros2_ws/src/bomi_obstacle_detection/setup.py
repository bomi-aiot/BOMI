"""bomi_obstacle_detection ROS 2 패키지의 설치 정보를 정의한다."""

from glob import glob
import os

from setuptools import find_packages, setup


package_name = "bomi_obstacle_detection"


setup(
    name=package_name,
    version="0.0.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        (
            "share/ament_index/resource_index/packages",
            ["resource/" + package_name],
        ),
        (
            "share/" + package_name,
            ["package.xml"],
        ),
        (
            os.path.join("share", package_name, "launch"),
            glob("launch/*.launch.py"),
        ),
        (
            os.path.join("share", package_name, "config"),
            glob("config/*.yaml"),
        ),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="ssafy",
    maintainer_email="ssafy@example.com",
    description="BOMI LiDAR 전방 장애물 거리 측정 패키지",
    license="Apache-2.0",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            (
                "front_distance_node = "
                "bomi_obstacle_detection.front_distance_node:main"
            ),
        ],
    },
)
