import os
import sys
import logging
from datetime import datetime
from collections import OrderedDict

import bpy
import bmesh

# Global Variables
C = bpy.context
D = bpy.data
O = bpy.ops

logging.basicConfig(level='DEBUG', format='%(asctime)s %(levelname)-10s %(message)s')
log = logging.getLogger('archilogic')

data3d_format_version = 1
addon_version = '?'

def export_images():
    ...

def parse_materials(export_objects):
    # From Metadata
    # Fallback: from Cycles or Blender internal
    # Don't forget Lightmapdata
    # Retun json material dictionary for writing

    materials = OrderedDict()
    bl_materials = []

    def get_material_json(bl_mat):
        al_mat = {}
        # Get Material from Archilogic MetaData
        if 'Data3d Material Settings' in bl_mat:
            al_mat = bl_mat['Data3d Material Settings'].to_dict()
            # FIXME Lightmaps and Image Export and texture Paths
        else:
            al_mat['colorDiffuse'] = list(bl_mat.diffuse_color)
            al_mat['colorSpecular'] = list(bl_mat.specular_color)
            al_mat['specularCoef'] = int(bl_mat.specular_hardness)

            if bl_mat.emit > 0.0:
                al_mat['lightEmissionCoef'] = bl_mat.emit
            if bl_mat.use_transparency:
                al_mat['opacity'] = bl_mat.alpha

            for tex_slot in bl_mat.texture_slots:
                if tex_slot is not None and tex_slot.texture.type == 'IMAGE':
                    file = os.path.basename(tex_slot.texture.image.filepath)
                    if tex_slot.use_map_color_diffuse:
                        al_mat['mapDiffuse'] = file
                    elif tex_slot.use_map_specular:
                        al_mat['mapSpecular'] = file
                    elif tex_slot.use_map_normal:
                        al_mat['mapNormal'] = file
                    elif tex_slot.use_map_alpha:
                        al_mat['mapAlpha'] = file
                    elif tex_slot:
                        al_mat['mapLight'] = file
                    else:
                        log.info('Texture type not supported for export: %s', file)
                #FIXME Filepaths and Image export

            # FIXME how/if to determine size?

        return al_mat

    for obj in export_objects:
        bl_materials.extend([slot.material for slot in obj.material_slots if slot.material != None])

    # Distinct the List
    bl_materials = list(set(bl_materials))
    for mat in bl_materials:
        materials[mat.name] = get_material_json(mat)

    # TODO export textures

    return materials

def parse_geometry(context, export_objects):
    # Prepare Mesh, tesselation, apply modifiers (...)
    # obj.to_mesh(context.scene, apply_modifiers=True, settings='RENDER' (, calc_tessface=True, calc_undeformed=False))
    ...
    """ Triangulate the specified mesh, calculate normals & tessfaces, apply export matrix
    """
    def get_obj_mesh_pair(obj):
        log.debug('Transforming object into mesh: %s', obj.name)
        mesh = obj.to_mesh(context.scene, apply_modifiers=True, settings='RENDER')
        mesh.name = obj.name
        #FIXME matrix transformation from operator settings
        mesh.transform(Matrix.Rotation(-math.pi / 2, 4, 'X') * obj.matrix_world)

        # FIXME check these steps
        # (compatability with split normals / apply modifier) make optional for calling the method
        # Split normals get LOST when transforming to bmesh.
        bm = bmesh.new()
        bm.from_mesh(mesh)

        bmesh.to_mesh(mesh)
        bm.free()
        del bm

        mesh.calc_normals()
        mesh.calc_tessface()

        return (obj, mesh)

    def serialize_meshes(meshes, object_map):
        for mesh in meshes:
            obj = object_map
            log.debug('Parsing mesh to json: %s', mesh.name)
            mesh_materials = [m for m in mesh.materials if m]

            json_object = OrderedDict()
            json_object['name'] = obj.name

            mat_count = len(mesh_materials)
            if mat_count == 0:
                # No Material Mesh
                ...
            elif mat_count == 1:
                # Single Material Mesh
                ...
            else:
                # Multimaterial Mesh
                ...



            


    obj_mesh_pairs = [get_obj_mesh_pair(obj) for obj in export_objects]
    object_map = {}
    meshes = [mesh for (obj, mesh) in export_objects]

    # FIXME Create a dictionary for obj mesh pairs where mesh.name is obj
    for (obj, mesh) in obj_mesh_pairs:
        objectMap[mesh.name] = obj
        # meshes.append(mesh)

    json_objects = serialize_meshes(meshes, object_map)






    return {}


def to_json(o, level=0):
    """
        Python's native JSON module adds a newline to every array element, since we
        deal with large arrays, we want the items in a row
        Args:
            level (int)
    """
    json_indent = 4
    json_space = ' '
    json_quote = '"'
    json_newline = '\n'

    ret = ''
    if isinstance(o, dict):
        ret += '{' + json_newline
        comma = ''
        for k, v in o.items():
            ret += comma
            comma = ',' + json_newline
            ret += json_space * json_indent * (level + 1)
            ret += json_quote + str(k) + json_quote + ':' + json_space
            ret += to_json(v, level+1)
        ret += json_newline + json_space * json_indent * level + '}'
    elif isinstance(o, list):
        ret += '[' + ','.join([to_json(e, level + 1) for e in o]) + ']'
    elif isinstance(o, str):
        ret += json_quote + o + json_quote
    elif isinstance(o, bool):
        ret += 'true' if o else 'false'
    elif isinstance(o, int):
        ret += str(o)
    elif isinstance(o, float):
        ret += '%.7g' % o
    #elif isinstance(o, numpy.ndarray) ...:
    else:
        raise TypeError("Unknown type '%s' for json serialization" % str(type(o)))

    return ret


def _write(context, output_path, EXPORT_GLOBAL_MATRIX, EXPORT_SEL_ONLY):
    try:
        if not os.path.exists(os.path.dirname(output_path)):
            os.makedirs(os.path.dirname(output_path))
        log.info('Exporting Scene: %s', output_path)

        if EXPORT_SEL_ONLY:
            export_objects = [obj for obj in context.selected_objects if obj.type == 'MESH']
        else:
            export_objects = [obj for obj in context.selectable_objects if obj.type == 'MESH']

        export_data = OrderedDict()
        meta = export_data['meta'] = OrderedDict()
        meta['version'] = str(data3d_format_version)
        meta['exporter'] = 'Archilogic Data3d Exporter Version: ' + addon_version
        meta['timestamp'] = str(datetime.utcnow())

        data3d = export_data['data3d'] = OrderedDict()
        meshes = data3d['mesh'] = parse_geometry(context, export_objects)
        materials = data3d['materials'] = parse_materials(export_objects)
        materials['test1'] = {'diffuse':'mymap2', 'specular':'myspecmap'}
        materials['test2'] = {'diffuse':'diffüs', 'specular':'specülar'}

        data3d['meshKeys'] = [key for key in meshes.keys()]
        data3d['materialKeys'] = [key for key in materials.keys()]


        with open(output_path, 'w', encoding='utf-8') as file:
            file.write(to_json(export_data))
        ...

    except:
        raise Exception('Export Scene failed. ', sys.exc_info())


def save(operator, context, filepath='', check_existing=True, use_selection=False, global_matrix=None):
    """ Called by the user interface or another script.
        (...)
    """
    # Fixme Remove unused variables operator, context, check_existing
    if global_matrix is None:
        global_matrix = mathutils.Matrix()

    _write(context, filepath, EXPORT_GLOBAL_MATRIX=global_matrix, EXPORT_SEL_ONLY=use_selection)

    return {'FINISHED'}
