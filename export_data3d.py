import os
import sys
import logging
from datetime import datetime
from collections import OrderedDict
import shutil

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

# FIXME Common data3d keys config
DiffuseMapKey = 'mapDiffuse'
SpecularMapKey = 'mapSpecular'
NormalMapKey = 'mapNormal'
AlphaMapKey = 'mapAlpha'
LightMapKey = 'mapLight'

TextureDirectory = 'textures'

### Helper ###

def validate_string(test_str, pattern=None):
    #Fixme implement return of string consisting of valid characters (for object name)
    import re
    pattern = r'[^\n.a-z0-9A-Z\s]'

    if re.search(pattern, test_str):
        print('invalid')
    else:
        print('valid')

def export_image_textures(bl_images, dest_dir):
    #Fixme Method

    log.debug("Export images %s", " **** ".join([img.name for img in bl_images]))

    for image in bl_images:
        filepath = image.filepath_from_user()

        tex_dir = os.path.join(dest_dir, TextureDirectory)
        if not os.path.exists(tex_dir):
            os.makedirs(tex_dir)
        shutil.copy(filepath, os.path.join(tex_dir))

    # filepath = os.path.join(TextureDirectory, tail)
    #
    #      filepath = path_reference(image.filepath, source_dir, dest_dir,
    #                            path_mode, "", copy_set, image.library)
    #     if export_textures:
    #         head, tail = ntpath.split(filepath)
    #         tex_dir = os.path.join(dest_dir, "tex")
    #         if not os.path.exists(tex_dir):
    #             os.makedirs(tex_dir)
    #         shutil.copyfile(filepath, os.path.join(tex_dir,tail))
    #
    #         filepath = os.path.join("tex", tail)

### Data3d Export Methods ###

def parse_materials(export_objects, export_metadata, export_images, export_dir=None):
    # From Metadata
    # Fallback: from Cycles or Blender internal
    # Don't forget Lightmapdata
    # Retun json material dictionary for writing

    # FIXME rename export_images
    materials = OrderedDict()
    bl_materials = []
    export_textures = []

    def get_material_json(bl_mat, tex_subdir):
        al_mat = {}
        textures = []
        # Get Material from Archilogic MetaData
        if export_metadata and 'Data3d Material Settings' in bl_mat:
            al_mat = bl_mat['Data3d Material Settings'].to_dict()
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
                    textures.append(tex_slot.texture.image)

                    if tex_slot.use_map_color_diffuse:
                        al_mat[DiffuseMapKey] = tex_subdir + file
                        log.info(al_mat[DiffuseMapKey])
                    elif tex_slot.use_map_specular:
                        al_mat[SpecularMapKey] = tex_subdir + file
                    elif tex_slot.use_map_normal:
                        al_mat[NormalMapKey] = tex_subdir + file
                    elif tex_slot.use_map_alpha:
                        al_mat[AlphaMapKey] = tex_subdir + file
                    elif tex_slot.use_map_emit:
                        al_mat[LightMapKey] = tex_subdir + file
                    else:
                        log.info('Texture type not supported for export: %s', file)

            # FIXME how/if to determine tesxture scale/size?

        return al_mat, textures

    for obj in export_objects:
        bl_materials.extend([slot.material for slot in obj.material_slots if slot.material != None])

    # Distinct the List
    bl_materials = list(set(bl_materials))
    tex_subdir = TextureDirectory + '/' if export_images else ''
    log.debug('tex subdir %s', tex_subdir)
    for mat in bl_materials:
        materials[mat.name], tex = get_material_json(mat, tex_subdir)
        export_textures.extend(tex)

    if export_images and export_dir:
        export_image_textures(list(set(export_textures)), export_dir)

    # TODO export textures

    return materials

def parse_geometry(context, export_objects, al_materials):
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

    def serialize_objects(bl_meshes, al_materials):
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
                #json_object['materials'] = {}
                #json_object['materialKeys'] = []
                #json_object['meshKeys'] = []

            else:
                # Multimaterial Mesh
                json_materials = {}
                for i, bl_mat in enumerate(mesh_materials):
                    faces = [face for face in bl_mesh.polygons if face.material_index == i]
                    if len(faces) > 0:
                        mat_name = bl_mat.name
                        json_mesh = parse_mesh(bl_mesh, faces=faces)
                        json_mesh['material'] = mat_name

                        json_mesh_name = bl_mesh.name + "-" + mat_name
                        json_meshes[json_mesh_name] = json_mesh

                        if mat_name in al_materials:
                            json_materials[mat_name] = al_materials[mat_name]

                json_object['meshes'] = json_meshes
                json_object['materials'] = json_materials
                json_object['meshKeys'] = [key for key in json_meshes.keys()]
                json_object['materialKeys'] = [key for key in json_materials.keys()]

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
    return serialize_objects(meshes, al_materials)


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


def _write(context, output_path, EXPORT_GLOBAL_MATRIX, EXPORT_SEL_ONLY, EXPORT_IMAGES, EXPORT_AL_METADATA):
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
        materials = parse_materials(export_objects, EXPORT_AL_METADATA, EXPORT_IMAGES, export_dir=os.path.dirname(output_path))
        meshes = data3d['children'] = parse_geometry(context, export_objects, materials)

        #TODO make texture export optional
        #if EXPORT_IMAGES:
        #export_images(materials)


        with open(output_path, 'w', encoding='utf-8') as file:
            file.write(to_json(export_data))
        ...

    except:
        raise Exception('Export Scene failed. ', sys.exc_info())


def save(operator,
         context,
         filepath='',
         check_existing=True,
         use_selection=False,
         export_images=False,
         export_al_metadata=False,
         global_matrix=None):
    """ Called by the user interface or another script.
        (...)
    """
    # Fixme Remove unused variables operator, context, check_existing
    if global_matrix is None:
        global_matrix = mathutils.Matrix()

    _write(context, filepath,
           EXPORT_GLOBAL_MATRIX=global_matrix,
           EXPORT_SEL_ONLY=use_selection,
           EXPORT_IMAGES=export_images,
           EXPORT_AL_METADATA=export_al_metadata)

    return {'FINISHED'}
