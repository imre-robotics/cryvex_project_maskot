cmake_minimum_required(VERSION 3.8)
project(cryvex_isaac)

find_package(ament_cmake REQUIRED)

# isaac/ klasoru Isaac Sim konteynerinde dogrudan src'den calisir (bkz. docker/compose.yaml);
# burada sadece ROS tarafinin ihtiyaci olanlar kurulur.
install(DIRECTORY launch foxglove DESTINATION share/${PROJECT_NAME})

ament_package()
