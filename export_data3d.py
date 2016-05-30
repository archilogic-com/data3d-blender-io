import os
import sys
import logging
from datetime import datetime
from collections import OrderedDict

import math
from mathutils import Matrix

import bpy
import bmesh
from bpy_extras.io_utils import unpack_list

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
        bmesh.ops.triangulate(bm, faces=bm.faces)
        bm.to_mesh(mesh)
        bm.free()
        del bm

        mesh.calc_normals()
        mesh.calc_tessface()

        return (obj, mesh)

    def serialize_objects(bl_meshes):
        json_objects = []

        for bl_mesh in bl_meshes:
            log.debug('Parsing blender mesh to json: %s', bl_mesh.name)

            json_object = OrderedDict()
            json_object['name'] = bl_mesh.name

            json_meshes = OrderedDict()
            mesh_materials = [m for m in bl_mesh.materials if m]

            if len(mesh_materials) == 0:
                # No Material Mesh
                json_meshes[bl_mesh.name] = parse_mesh(bl_mesh)
                json_object['meshes'] = json_meshes
                json_object['materials'] = {}
                json_object['materialKeys'] = []
                json_object['meshKeys'] = []

            else:
                # Multimaterial Mesh
                for i, material in enumerate(mesh_materials):
                    faces = [face for face in bl_mesh.polygons if face.material_index == i]
                    if len(faces) > 0:
                        json_mesh = parse_mesh(bl_mesh, faces=faces)
                        json_mesh['material'] = material.name

                        json_mesh_name = bl_mesh.name + "-" + material.name
                        json_meshes[json_mesh_name] = json_mesh

                json_object['meshes'] = json_meshes
                # json_object['materials'] = ...
                # json_object['meshKeys'] = ...
                # json_object['materialKeys'] = ...

            json_objects.append(json_object)

        return json_objects

    def parse_mesh(bl_mesh, faces=None):
        """
            Parses a blender mesh into data3d arrays
            Example:

            Non-interleaved: (data3d.json)
                positions: [vx, vy, vz, ... ] size: multiple of 3
                normals: [nx, ny, nz, ...] size: multiple of 3
                uv: [u1, v1, ...] optional, multiple of 2
                uv2: [u2, v2, ...] optional, multiple of 2

            Interleaved: (data3d.buffer)
                (... TODO)
        """

        # UV Textures by name
        # FIXME Tessface uv Textures vs. Mesh.polygon for normals
        # FIXME triangulate
        texture_uvs = bl_mesh.tessface_uv_textures.get('UVMap')
        lightmap_uvs = bl_mesh.tessface_uv_textures.get('UVLightmap')

        if faces is None:
            faces = bl_mesh.polygons

        _vertices = []
        _normals = []
        _uvs = []
        _uvs2 = []

        # Used for split normals export
        face_index_pairs = [(face, index) for index, face in enumerate(faces)]
        # FIXME What does calc_normals split do for custom vertex normals?
        bl_mesh.calc_normals_split()
        loops = bl_mesh.loops

        for face, face_index in face_index_pairs:
            # gather the face vertices
            face_vertices = [bl_mesh.vertices[v] for v in face.vertices]
            face_vertices_length = len(face_vertices)

            vertices = [(v.co.x, v.co.y, v.co.z) for v in face_vertices]
            normals = [(loops[l_idx].normal.x, loops[l_idx].normal.y, loops[l_idx].normal.z) for l_idx in face.loop_indices]

            uvs = [None] * face_vertices_length
            uvs2 = [None] * face_vertices_length

            if texture_uvs:
                uv_layer = texture_uvs.data[face.index].uv
                uvs = [(uv[0], uv[1]) for uv in uv_layer]

            if lightmap_uvs:
                uv_layer = texture_uvs.data[face.index].uv
                uvs2 = [(uv[0], uv[1]) for uv in uv_layer]

            _vertices += vertices
            _normals += normals
            _uvs += uvs
            _uvs2 += uvs2


        mesh = OrderedDict()
        mesh['positions'] = unpack_list(_vertices)
        mesh['normals'] = unpack_list(_normals)

        if texture_uvs:
            mesh['uvs'] = unpack_list(_uvs)

        if lightmap_uvs:
            mesh['uvs2'] = unpack_list(_uvs2)

        return mesh


    obj_mesh_pairs = [get_obj_mesh_pair(obj) for obj in export_objects]
    #object_map = {}
    meshes = [mesh for (obj, mesh) in obj_mesh_pairs]

    # FIXME Create a dictionary for obj mesh pairs where mesh.name is obj
    #for (obj, mesh) in obj_mesh_pairs:
    #    objectMap[mesh.name] = obj
        #meshes.append(mesh)
    return serialize_objects(meshes)


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
        meshes = data3d['children'] = parse_geometry(context, export_objects)

        #materials = data3d['materials'] = parse_materials(export_objects)
        #materials['test1'] = {'diffuse':'mymap2', 'specular':'myspecmap'}
        #materials['test2'] = {'diffuse':'diffüs', 'specular':'specülar'}

        #data3d['meshKeys'] = [key for key in meshes.keys()]
        #data3d['materialKeys'] = [key for key in materials.keys()]


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
