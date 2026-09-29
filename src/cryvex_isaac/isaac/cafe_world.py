"""
Cryvex - Gazebo kafe dunyasini (cryvex_gazebo/worlds/cafe.world, SDF 1.6) Isaac
Sim sahnesine (USD) cevirir.

Neden cevirici (elle modellemek yerine): kayitli harita (maps/cafe_map.*),
patrol.py'nin masa noktalari ve AMCL baslangic pozu HEP bu dunyanin
koordinatlarina gore. Dunyayi Gazebo'daki ile BIREBIR ayni yerlere koyarsak
Nav2/harita/masa kurulumu hic degismeden Isaac'te de calisir. cafe.world
degisirse bu betik bir sonraki acilista onu da otomatik alir.

Sadece pxr (OpenUSD) kullanir, Isaac'e bagli degil: Isaac olmadan da
denenebilir (pip install usd-core):

    python3 cafe_world.py ../../cryvex_gazebo/worlds/cafe.world /tmp/cafe.usda

Cevrilenler:
  <visual>    -> gorunen prim (RTX LiDAR bunu gorur) + malzeme rengi
  <collision> -> gorunmez prim + UsdPhysics.CollisionAPI (fizik ve sonar
                 isinlari bunlara carpar - Gazebo'daki gibi)
  box/cylinder/sphere geometrileri, model+link+eleman pozlari (x y z r p y)
  <light type="point"> -> UsdLux.SphereLight, model://sun -> DistantLight,
  model://ground_plane -> buyuk zemin kutusu (ust yuzu z=0)
"""
import math
import sys
import xml.etree.ElementTree as ET

from pxr import Gf, Sdf, Usd, UsdGeom, UsdLux, UsdPhysics, UsdShade


def _pose_matrix(text):
    """SDF '<pose>x y z roll pitch yaw</pose>' -> Gf.Matrix4d (SDF: R = Rz*Ry*Rx)."""
    vals = [float(v) for v in (text or '').split()] if text else []
    vals += [0.0] * (6 - len(vals))
    x, y, z, roll, pitch, yaw = vals[:6]
    rot = (Gf.Rotation(Gf.Vec3d(1, 0, 0), math.degrees(roll))
           * Gf.Rotation(Gf.Vec3d(0, 1, 0), math.degrees(pitch))
           * Gf.Rotation(Gf.Vec3d(0, 0, 1), math.degrees(yaw)))
    m = Gf.Matrix4d(1.0)
    m.SetRotateOnly(rot)
    m.SetTranslateOnly(Gf.Vec3d(x, y, z))
    return m


def _pose_of(elem):
    p = elem.find('pose')
    return _pose_matrix(p.text if p is not None else None)


def _safe_name(name):
    out = ''.join(c if (c.isalnum() or c == '_') else '_' for c in name)
    return out if out and not out[0].isdigit() else '_' + out


def _set_xform(prim, matrix, scale=None):
    """matrix -> translate + orient (+ scale) xformOp'lari."""
    xf = UsdGeom.Xformable(prim)
    xf.ClearXformOpOrder()
    xf.AddTranslateOp(UsdGeom.XformOp.PrecisionDouble).Set(matrix.ExtractTranslation())
    q = matrix.ExtractRotationQuat()
    xf.AddOrientOp(UsdGeom.XformOp.PrecisionDouble).Set(Gf.Quatd(q.GetReal(), q.GetImaginary()))
    if scale is not None:
        xf.AddScaleOp(UsdGeom.XformOp.PrecisionDouble).Set(Gf.Vec3d(*scale))


def _define_geometry(stage, path, geom_elem):
    """SDF <geometry> -> USD gprim. (prim, scale) doner; desteklenmeyen tipte (None, None)."""
    shape = geom_elem[0]
    if shape.tag == 'box':
        size = [float(v) for v in shape.findtext('size').split()]
        cube = UsdGeom.Cube.Define(stage, path)
        cube.CreateSizeAttr(1.0)
        return cube.GetPrim(), size
    if shape.tag == 'cylinder':
        cyl = UsdGeom.Cylinder.Define(stage, path)
        cyl.CreateRadiusAttr(float(shape.findtext('radius')))
        cyl.CreateHeightAttr(float(shape.findtext('length')))
        cyl.CreateAxisAttr(UsdGeom.Tokens.z)
        return cyl.GetPrim(), None
    if shape.tag == 'sphere':
        sph = UsdGeom.Sphere.Define(stage, path)
        sph.CreateRadiusAttr(float(shape.findtext('radius')))
        return sph.GetPrim(), None
    return None, None


class _Materials:
    """Ayni renge tek UsdPreviewSurface (73 model, ~15 farkli renk)."""

    def __init__(self, stage, root):
        self.stage = stage
        self.root = root
        self.cache = {}

    def get(self, rgb):
        key = tuple(round(c, 3) for c in rgb)
        if key not in self.cache:
            path = f'{self.root}/Looks/mat_{len(self.cache)}'
            mat = UsdShade.Material.Define(self.stage, path)
            shader = UsdShade.Shader.Define(self.stage, path + '/Shader')
            shader.CreateIdAttr('UsdPreviewSurface')
            shader.CreateInput('diffuseColor', Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*key))
            shader.CreateInput('roughness', Sdf.ValueTypeNames.Float).Set(0.6)
            mat.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), 'surface')
            self.cache[key] = mat
        return self.cache[key]


def _color_of(visual):
    mat = visual.find('material')
    if mat is None:
        return (0.7, 0.7, 0.7)
    txt = mat.findtext('diffuse') or mat.findtext('ambient')
    if not txt:
        return (0.7, 0.7, 0.7)
    return tuple(float(v) for v in txt.split()[:3])


def build_cafe(stage, world_path, root='/World/Cafe'):
    """cafe.world'u stage'e root altina kurar. Olusan prim sayilarini doner."""
    world = ET.parse(world_path).getroot().find('world')
    if world is None:
        raise ValueError(f'{world_path}: <world> bulunamadi')

    UsdGeom.Xform.Define(stage, root)
    mats = _Materials(stage, root)
    stats = {'visual': 0, 'collision': 0, 'light': 0, 'skipped': 0}

    # --- include'lar: gunes ve zemin ---
    for inc in world.findall('include'):
        uri = (inc.findtext('uri') or '').strip()
        if uri == 'model://sun':
            sun = UsdLux.DistantLight.Define(stage, f'{root}/Sun')
            sun.CreateIntensityAttr(2500.0)
            sun.CreateAngleAttr(0.53)
            _set_xform(sun.GetPrim(), _pose_matrix('0 0 10 0 0.6 0.3'))
            stats['light'] += 1
        elif uri == 'model://ground_plane':
            path = f'{root}/GroundPlane'
            ground = UsdGeom.Cube.Define(stage, path)
            ground.CreateSizeAttr(1.0)
            ground.CreateDisplayColorAttr([Gf.Vec3f(0.35, 0.35, 0.35)])
            _set_xform(ground.GetPrim(), _pose_matrix('0 0 -0.05 0 0 0'), scale=(100.0, 100.0, 0.1))
            UsdPhysics.CollisionAPI.Apply(ground.GetPrim())
            stats['collision'] += 1

    # Gazebo'nun varsayilan ortam isigina yakin yumusak dolgu isigi
    dome = UsdLux.DomeLight.Define(stage, f'{root}/AmbientDome')
    dome.CreateIntensityAttr(400.0)
    stats['light'] += 1

    # --- tavan lambalari ---
    for light in world.findall('light'):
        if light.get('type') != 'point':
            stats['skipped'] += 1
            continue
        sl = UsdLux.SphereLight.Define(stage, f"{root}/Lights/{_safe_name(light.get('name'))}")
        sl.CreateRadiusAttr(0.1)
        sl.CreateIntensityAttr(30000.0)
        diffuse = light.findtext('diffuse')
        if diffuse:
            sl.CreateColorAttr(Gf.Vec3f(*[float(v) for v in diffuse.split()[:3]]))
        _set_xform(sl.GetPrim(), _pose_of(light))
        stats['light'] += 1

    # --- modeller ---
    for model in world.findall('model'):
        mname = _safe_name(model.get('name'))
        model_m = _pose_of(model)
        UsdGeom.Xform.Define(stage, f'{root}/{mname}')
        for link in model.findall('link'):
            lname = _safe_name(link.get('name'))
            link_m = _pose_of(link) * model_m          # USD satir-vektor: once cocuk sonra ebeveyn
            UsdGeom.Xform.Define(stage, f'{root}/{mname}/{lname}')
            for tag in ('visual', 'collision'):
                for i, elem in enumerate(link.findall(tag)):
                    geom = elem.find('geometry')
                    if geom is None or len(geom) == 0:
                        stats['skipped'] += 1
                        continue
                    ename = _safe_name(elem.get('name') or f'{tag}_{i}')
                    path = f'{root}/{mname}/{lname}/{tag}_{ename}'
                    prim, scale = _define_geometry(stage, path, geom)
                    if prim is None:
                        stats['skipped'] += 1
                        continue
                    # Gazebo'da her sey statik - dunya pozunu dogrudan yaz
                    _set_xform(prim, _pose_of(elem) * link_m, scale=scale)
                    if tag == 'visual':
                        UsdShade.MaterialBindingAPI.Apply(prim).Bind(mats.get(_color_of(elem)))
                    else:
                        UsdGeom.Imageable(prim).MakeInvisible()
                        UsdPhysics.CollisionAPI.Apply(prim)
                    stats[tag] += 1

    # Link/model Xform'lari pozsuz; gprim'ler dunya pozunu tasir. Link Xform'larina
    # poz yazmadigimiz icin hiyerarsi sadece duzen amacli.
    return stats


def main(argv):
    if len(argv) != 3:
        print(__doc__)
        return 2
    stage = Usd.Stage.CreateNew(argv[2])
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    UsdGeom.Xform.Define(stage, '/World')
    stage.SetDefaultPrim(stage.GetPrimAtPath('/World'))
    stats = build_cafe(stage, argv[1])
    stage.GetRootLayer().Save()
    print(f'{argv[2]} yazildi: {stats}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
