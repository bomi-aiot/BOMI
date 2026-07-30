from setuptools import find_packages, setup

package_name = 'bridge'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='wdg',
    maintainer_email='wdg0434@naver.com',
    description='백엔드 MQTT와 로봇 내부 ROS 2 토픽을 잇는 통역 브릿지 패키지',
    license='Apache-2.0',
    extras_require={
        'test': [
            'pytest',
        ],
    },
    entry_points={
        "console_scripts": [
            "mqtt_bridge = bridge.mqtt_bridge_node:main",
        ],
    },
)
