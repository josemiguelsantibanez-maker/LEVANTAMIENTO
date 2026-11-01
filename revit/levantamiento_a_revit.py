# -*- coding: utf-8 -*-
"""
Levantamiento -> Revit  (Dynamo 3.x, motor CPython3 — Revit 2025)

Lee el archivo "..._revit.json" que exporta la app de levantamiento y crea, en el nivel más bajo
del modelo (o en el nivel indicado en IN[1]):
  - Tipos de muro "Levantamiento NN cm" (una capa, según espesor) y muros nativos por su eje, con su altura.
  - Puertas, ventanas y ventanales: duplica un tipo de la familia cargada con el ancho y alto medidos.
  - Vanos vacíos: aberturas rectangulares en el muro.
  - Habitaciones con el nombre y la altura de cada recinto.

Entradas:
  IN[0]  ruta del archivo .json (nodo File Path)
  IN[1]  (opcional) nombre del nivel. Vacío = nivel más bajo
  IN[2]  (opcional) texto que contenga el nombre de la familia de puertas a usar
  IN[3]  (opcional) texto que contenga el nombre de la familia de ventanas a usar
Ejecutar UNA sola vez en modo Manual: cada ejecución vuelve a crear los elementos.
"""
import clr, json
clr.AddReference('RevitAPI')
from Autodesk.Revit.DB import *
from Autodesk.Revit.DB.Structure import StructuralType
clr.AddReference('RevitServices')
from RevitServices.Persistence import DocumentManager
from RevitServices.Transactions import TransactionManager

doc = DocumentManager.Instance.CurrentDBDocument

def _in(i, default=None):
    try:
        v = IN[i]
        return v if v not in (None, '') else default
    except Exception:
        return default

path = _in(0)
level_name = _in(1)
door_hint = (_in(2) or '').lower()
win_hint = (_in(3) or '').lower()

FT = 1.0 / 0.3048
def ft(m): return float(m) * FT

report = []

def type_name(e):
    p = e.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)
    return p.AsString() if p else ''

def family_name(sym):
    try:
        return sym.Family.Name
    except Exception:
        p = sym.get_Parameter(BuiltInParameter.SYMBOL_FAMILY_NAME_PARAM)
        return p.AsString() if p else ''

with open(path, encoding='utf-8') as f:
    data = json.load(f)

# ---------- nivel ----------
levels = sorted(FilteredElementCollector(doc).OfClass(Level).ToElements(), key=lambda l: l.Elevation)
level = levels[0]
if level_name:
    for l in levels:
        if l.Name == level_name:
            level = l
z0 = level.Elevation

# ---------- tipos de muro ----------
basic_types = [t for t in FilteredElementCollector(doc).OfClass(WallType).ToElements() if t.Kind == WallKind.Basic]
wall_types = {}
def wall_type(thk):
    cm = int(round(thk * 100))
    if cm in wall_types:
        return wall_types[cm]
    name = 'Levantamiento %d cm' % cm
    for t in basic_types:
        if type_name(t) == name:
            wall_types[cm] = t
            return t
    nt = doc.GetElement(basic_types[0].Duplicate(name).Id)
    cs = CompoundStructure.CreateSingleLayerCompoundStructure(MaterialFunctionAssignment.Structure, ft(thk), ElementId.InvalidElementId)
    nt.SetCompoundStructure(cs)
    wall_types[cm] = nt
    report.append('Tipo de muro creado: ' + name)
    return nt

# ---------- tipos de puerta / ventana ----------
def symbols(cat, hint):
    syms = list(FilteredElementCollector(doc).OfClass(FamilySymbol).OfCategory(cat).ToElements())
    if hint:
        pref = [s for s in syms if hint in family_name(s).lower()]
        if pref:
            return pref
    return syms

def set_len(elem, names, bips, value):
    for b in bips:
        bip = getattr(BuiltInParameter, b, None)
        if bip is None:
            continue
        p = elem.get_Parameter(bip)
        if p and not p.IsReadOnly:
            p.Set(value)
            return True
    for n in names:
        p = elem.LookupParameter(n)
        if p and not p.IsReadOnly and p.StorageType == StorageType.Double:
            p.Set(value)
            return True
    return False

sym_cache = {}
def symbol_for(kind, w, h):
    cat = BuiltInCategory.OST_Doors if kind == 'door' else BuiltInCategory.OST_Windows
    hint = door_hint if kind == 'door' else win_hint
    base_list = symbols(cat, hint)
    if not base_list:
        return None
    base = base_list[0]
    fam = family_name(base)
    name = '%s %dx%d' % ('Lev', int(round(w * 100)), int(round(h * 100)))
    key = (fam, name)
    if key in sym_cache:
        return sym_cache[key]
    for s in base_list:
        if family_name(s) == fam and type_name(s) == name:
            sym_cache[key] = s
            return s
    ns = doc.GetElement(base.Duplicate(name).Id)
    okw = set_len(ns, ['Width', 'Anchura', 'Ancho'], ['DOOR_WIDTH', 'WINDOW_WIDTH', 'FAMILY_WIDTH_PARAM'], ft(w))
    okh = set_len(ns, ['Height', 'Altura', 'Alto'], ['DOOR_HEIGHT', 'WINDOW_HEIGHT', 'FAMILY_HEIGHT_PARAM'], ft(h))
    if not (okw and okh):
        report.append('Aviso: no se pudo fijar ancho/alto en la familia "%s"; revisa el tipo %s' % (fam, name))
    if not ns.IsActive:
        ns.Activate()
    sym_cache[key] = ns
    return ns

def P3(x, y, z=0.0):
    return XYZ(ft(x), ft(y), z0 + ft(z))

# ---------- crear ----------
TransactionManager.Instance.EnsureInTransaction(doc)

walls = {}
for w in data.get('walls', []):
    try:
        a = P3(w['start'][0], w['start'][1]); b = P3(w['end'][0], w['end'][1])
        if a.DistanceTo(b) < 0.01:
            continue
        wt = wall_type(float(w['thickness']))
        wall = Wall.Create(doc, Line.CreateBound(a, b), wt.Id, level.Id, ft(w['height']), 0.0, False, False)
        c = wall.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
        if c:
            c.Set('%s (levantamiento)' % w['name'])
        walls[w['id']] = (wall, a, b)
    except Exception as ex:
        report.append('Error en muro %s: %s' % (w.get('name'), ex))
doc.Regenerate()
report.append('Muros creados: %d' % len(walls))

n_inst = 0; n_open = 0
for o in data.get('openings', []):
    try:
        if o['wall'] not in walls:
            continue
        wall, a, b = walls[o['wall']]
        d = b.Subtract(a).Normalize()
        c = a.Add(d.Multiply(ft(o['center'])))
        width = float(o['width']); height = float(o['height']); sill = float(o.get('sill', 0) or 0)
        if o['kind'] == 'opening':
            p1 = c.Subtract(d.Multiply(ft(width / 2))).Add(XYZ(0, 0, ft(sill)))
            p2 = c.Add(d.Multiply(ft(width / 2))).Add(XYZ(0, 0, ft(sill + height)))
            doc.Create.NewOpening(wall, p1, p2)
            n_open += 1
            continue
        kind = 'door' if o['kind'] == 'door' else 'window'
        sym = symbol_for(kind, width, height)
        if sym is None:
            report.append('No hay familias de %s cargadas: se omitió %s' % ('puertas' if kind == 'door' else 'ventanas', o['name']))
            continue
        doc.Regenerate()
        inst = doc.Create.NewFamilyInstance(XYZ(c.X, c.Y, z0), sym, wall, level, StructuralType.NonStructural)
        if kind == 'window':
            p = inst.get_Parameter(BuiltInParameter.INSTANCE_SILL_HEIGHT_PARAM)
            if p and not p.IsReadOnly:
                p.Set(ft(sill))
        else:
            fl = int(o.get('flip', 0))
            try:
                if fl & 1: inst.flipHand()
                if fl & 2: inst.flipFacing()
            except Exception:
                pass
        m = inst.get_Parameter(BuiltInParameter.ALL_MODEL_MARK)
        if m:
            m.Set(o['name'])
        n_inst += 1
    except Exception as ex:
        report.append('Error en vano %s: %s' % (o.get('name'), ex))
report.append('Puertas y ventanas: %d · Vanos vacíos: %d' % (n_inst, n_open))

doc.Regenerate()
n_rooms = 0
for r in data.get('rooms', []):
    try:
        room = doc.Create.NewRoom(level, UV(ft(r['at'][0]), ft(r['at'][1])))
        p = room.get_Parameter(BuiltInParameter.ROOM_NAME)
        if p:
            p.Set(r['name'])
        if r.get('height'):
            up = room.get_Parameter(BuiltInParameter.ROOM_UPPER_OFFSET)
            if up:
                up.Set(ft(r['height']))
        n_rooms += 1
    except Exception as ex:
        report.append('Habitación "%s" no creada: %s' % (r.get('name'), ex))
report.append('Habitaciones: %d' % n_rooms)

TransactionManager.Instance.TransactionTaskDone()

if not data.get('project', {}).get('rectified'):
    report.insert(0, 'Aviso: la planta no estaba rectificada; las medidas pueden no ser a escala.')
OUT = report
