#!/usr/bin/env python3
"""
cryvex_description/urdf/cryvex.urdf.xacro -> isaac/assets/cryvex.urdf

Isaac Sim konteynerinde ROS/xacro yok; bu yuzden xacro'yu burada (ROS ortaminda)
acip duz URDF'yi pakete koyuyoruz. Robotun govdesi/tekerleri degisirse:

    python3 src/cryvex_isaac/tools/export_urdf.py

(Isaac tarafi URDF'nin USD'ye cevrilmis halini onbellege alir ve URDF
degisince kendiliginden yeniden cevirir - ayrica bir sey yapmana gerek yok.)

Isaac icin yapilan iki duzeltme (ROS tarafindaki URDF'ye DOKUNULMAZ,
robot_state_publisher orijinalini kullanmaya devam eder):
  1) <gazebo> bloklari atilir (Gazebo eklentileri; Isaac'te karsiliklari
     run_cafe_sim.py'deki ROS 2 grafigi ve sensorler).
  2) <inertial>'i olmayan linklere (base_footprint, sonar_*, camera_link)
     cok kucuk bir kutle verilir. PhysX kutlesiz rijit cismi sevmez; Gazebo
     bunlari sessizce birlestiriyordu.
"""
import os
import sys
import xml.etree.ElementTree as ET

import xacro

HERE = os.path.dirname(os.path.abspath(__file__))
PKG_ROOT = os.path.dirname(HERE)
SRC_ROOT = os.path.dirname(PKG_ROOT)
XACRO_PATH = os.path.join(SRC_ROOT, 'cryvex_description', 'urdf', 'cryvex.urdf.xacro')
OUT_PATH = os.path.join(PKG_ROOT, 'isaac', 'assets', 'cryvex.urdf')

TINY_MASS = 0.01
TINY_INERTIA = 1e-6


def main():
    doc = xacro.process_file(XACRO_PATH)
    root = ET.fromstring(doc.toxml())

    removed = 0
    for g in root.findall('gazebo'):
        root.remove(g)
        removed += 1

    patched = []
    for link in root.findall('link'):
        if link.find('inertial') is None:
            inertial = ET.SubElement(link, 'inertial')
            ET.SubElement(inertial, 'mass', value=str(TINY_MASS))
            i = str(TINY_INERTIA)
            ET.SubElement(inertial, 'inertia', ixx=i, ixy='0', ixz='0', iyy=i, iyz='0', izz=i)
            patched.append(link.get('name'))

    ET.indent(root, space='  ')
    header = ('<?xml version="1.0"?>\n'
              '<!-- OTOMATIK URETILDI: src/cryvex_isaac/tools/export_urdf.py\n'
              '     Kaynak: cryvex_description/urdf/cryvex.urdf.xacro - elle duzenleme,\n'
              '     xacro\'yu degistirip betigi yeniden calistir. -->\n')
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, 'w', encoding='utf-8') as f:
        f.write(header + ET.tostring(root, encoding='unicode') + '\n')

    print(f'{OUT_PATH} yazildi: {removed} <gazebo> blogu atildi, '
          f'kutle eklenen linkler: {", ".join(patched) or "-"}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
