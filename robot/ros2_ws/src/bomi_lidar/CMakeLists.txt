cmake_minimum_required(VERSION 3.8)
project(bomi_lidar)

# ROS 2 CMake 패키지 빌드 시스템을 사용한다.
find_package(ament_cmake REQUIRED)

# LiDAR 실행 파일, 센서 설정 및 RViz 설정을 설치한다.
install(
  DIRECTORY
    launch
    config
  DESTINATION share/${PROJECT_NAME}
)

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  ament_lint_auto_find_test_dependencies()
endif()

ament_package()
