import os

world_path = os.path.join(os.path.dirname(__file__), 'cafe.world')

header = """<?xml version="1.0" ?>
<sdf version="1.6">
  <world name="cafe_world">
    <include><uri>model://sun</uri></include>
    <include><uri>model://ground_plane</uri></include>
    
    <!-- 15x15m Kafenin Dış Duvarları -->
    <model name="cafe_walls">
      <static>true</static>
      <link name="wall_n"><pose>0 7.5 1.5 0 0 0</pose><collision name="c"><geometry><box><size>15 0.2 3</size></box></geometry></collision><visual name="v"><geometry><box><size>15 0.2 3</size></box></geometry><material><ambient>0.8 0.8 0.8 1</ambient></material></visual></link>
      <link name="wall_s"><pose>0 -7.5 1.5 0 0 0</pose><collision name="c"><geometry><box><size>15 0.2 3</size></box></geometry></collision><visual name="v"><geometry><box><size>15 0.2 3</size></box></geometry><material><ambient>0.8 0.8 0.8 1</ambient></material></visual></link>
      <link name="wall_e"><pose>7.5 0 1.5 0 0 1.5708</pose><collision name="c"><geometry><box><size>15 0.2 3</size></box></geometry></collision><visual name="v"><geometry><box><size>15 0.2 3</size></box></geometry><material><ambient>0.8 0.8 0.8 1</ambient></material></visual></link>
      <link name="wall_w"><pose>-7.5 0 1.5 0 0 1.5708</pose><collision name="c"><geometry><box><size>15 0.2 3</size></box></geometry></collision><visual name="v"><geometry><box><size>15 0.2 3</size></box></geometry><material><ambient>0.8 0.8 0.8 1</ambient></material></visual></link>
    </model>
"""

footer = """
  </world>
</sdf>
"""

# Masa Koordinatları (10 Adet)
tables = [
    (-5, -5), (0, -5), (5, -5),
    (-5, 0),           (5, 0),
    (-5, 5),  (0, 5),  (5, 5),
    (-2.5, -2.5), (2.5, 2.5)
]

with open(world_path, 'w') as f:
    f.write(header)
    for i, (tx, ty) in enumerate(tables):
        # Masayı Ekle (Ahşap Rengi)
        f.write(f"""
    <model name="table_{i}">
      <static>true</static>
      <link name="link">
        <pose>{tx} {ty} 0.4 0 0 0</pose>
        <collision name="c"><geometry><cylinder><radius>0.5</radius><length>0.8</length></cylinder></geometry></collision>
        <visual name="v"><geometry><cylinder><radius>0.5</radius><length>0.8</length></cylinder></geometry><material><ambient>0.6 0.4 0.2 1</ambient></material></visual>
      </link>
    </model>""")
        
        # Etrafına 4 Sandalye Ekle (Kırmızı Renk, Ayaklar Lidar'ın tam göreceği şekilde modellendi)
        chair_offsets = [(0, 0.7, 0), (0, -0.7, 3.14), (0.7, 0, -1.57), (-0.7, 0, 1.57)]
        for j, (cx, cy, cyaw) in enumerate(chair_offsets):
            f.write(f"""
    <model name="chair_{i}_{j}">
      <static>true</static>
      <link name="link">
        <pose>{tx+cx} {ty+cy} 0.25 0 0 {cyaw}</pose>
        <collision name="c"><geometry><box><size>0.4 0.4 0.5</size></box></geometry></collision>
        <visual name="v"><geometry><box><size>0.4 0.4 0.5</size></box></geometry><material><ambient>0.8 0.2 0.2 1</ambient></material></visual>
      </link>
    </model>""")
    f.write(footer)

print(f"Başarılı: Kafe dünyası {world_path} konumunda oluşturuldu!")