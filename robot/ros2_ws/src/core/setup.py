from setuptools import find_packages, setup

package_name = 'core'

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
    maintainer='cho-eunchae',
    maintainer_email='gcodms56@gmail.com',
    description='TODO: Package description',
    license='Apache-2.0',
    extras_require={
        'test': [
            'pytest',
        ],
    },
    entry_points={
        "console_scripts": [
            "status_publisher = core.status_publisher:main",
            "mock_motor_driver = core.mock_motor_driver:main",
            "keyboard_teleop = core.keyboard_teleop:main",
        ],
    },
)
