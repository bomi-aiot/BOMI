from setuptools import find_packages, setup


package_name = "bomi_display"


setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        ("share/" + package_name + "/launch", ["launch/display.launch.py"]),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="BOMI Team",
    maintainer_email="gcodms56@gmail.com",
    description="PySide6 기반 BOMI LCD 표정 및 ROS 2 상태 표시기",
    license="Apache-2.0",
    extras_require={"test": ["pytest"]},
    entry_points={
        "console_scripts": [
            "face_display = bomi_display.face_display:main",
        ],
    },
)
