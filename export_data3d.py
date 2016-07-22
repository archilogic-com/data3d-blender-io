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

from . import ModuleInfo
from io_scene_data3d.data3d_utils import D3D, serialize_data3d


# Global Variables
C = bpy.context
D = bpy.data
O = bpy.ops

logging.basicConfig(level='DEBUG', format='%(asctime)s %(levelname)-10s %(message)s', stream=sys.stdout)
log = logging.getLogger('archilogic')

TextureDirectory = 'textures'

### Data3d Export Methods ###


def parse_materials(export_objects, export_metadata, export_images, export_dir=None):
    """ Parse Blender Materials and translate them to data3d materials.
        Args:
            export_objects ('bpy_prop_collection') - The exported objects.
            export_metadata ('bool') - Export Archilogic Metadata, if it exists.
            export_images ('bool') -  Export associated texture files.
            export_dir ('str') - The exported directory.
        Returns:
            al_materials ('dict') - The data3d materials dictionary.
    """
    # From Metadata
    # Fallback: from Cycles or Blender internal
    # Don't forget Lightmapdata
    # Retun json material dictionary for writing

    # FIXME rename export_images
    al_materials = OrderedDict()
    bl_materials = []
    raw_images = []

    def get_material_json(bl_mat, tex_subdir):
        """ Get the json material data from Archilogic metadata or Blender Internal material.
            Args:
                bl_mat ('bpy.types.Material') - The Blender materials.
                tex_subdir ('str') - The texture export directory.
            Returns:
                al_mat ('dict') - The parsed data3d material.
                textures ('list(bpy.types.Image)') - The list of associated textures to export.
        """
        al_mat = {}
        textures = []
        # Get Material from Archilogic MetaData
        if export_metadata and 'Data3d Material' in bl_mat:
            al_mat = bl_mat['Data3d Material'].to_dict()
        else:
            al_mat[D3D.col_diff] = list(bl_mat.diffuse_color)
            al_mat[D3D.col_spec] = list(bl_mat.specular_color)
            al_mat[D3D.coef_spec] = int(bl_mat.specular_hardness)

            if bl_mat.emit > 0.0:
                al_mat[D3D.coef_emit] = bl_mat.emit
            if bl_mat.use_transparency:
                al_mat[D3D.opacity] = bl_mat.alpha

            for tex_slot in bl_mat.texture_slots:
                if tex_slot is not None and tex_slot.texture.type == 'IMAGE':
                    # FIXME if type image but no filepath, abort
                    file = os.path.basename(tex_slot.texture.image.filepath)
                    textures.append(tex_slot.texture.image)

                    if tex_slot.use_map_color_diffuse:
                        al_mat[D3D.map_diff] = tex_subdir + file
                        log.info(al_mat[D3D.map_diff])
                    elif tex_slot.use_map_specular:
                        al_mat[D3D.map_spec] = tex_subdir + file
                    elif tex_slot.use_map_normal:
                        al_mat[D3D.map_norm] = tex_subdir + file
                    elif tex_slot.use_map_alpha:
                        al_mat[D3D.map_alpha] = tex_subdir + file
                    elif tex_slot.use_map_emit:
                        al_mat[D3D.map_light] = tex_subdir + file
                    else:
                        log.info('Texture type not supported for export: %s', file)

            # FIXME export texture scale/size?

        return al_mat, textures

    def export_image_textures(bl_images, dest_dir):
        """ Copy the image texture to destination directory.
            Args:
                bl_images ('list(bpy.types.Image)') - The associated image data blocks.
                dest_dir ('str') - The texture export directory.
        """
        log.debug("Export images %s", " **** ".join([img.name for img in bl_images]))

        for image in bl_images:
            filepath = image.filepath_from_user()

            tex_dir = os.path.join(dest_dir, TextureDirectory)
            if not os.path.exists(tex_dir):
                os.makedirs(tex_dir)
            shutil.copy(filepath, os.path.join(tex_dir))

    for obj in export_objects:
        bl_materials.extend([slot.material for slot in obj.material_slots if slot.material is not None])

    bl_materials = list(set(bl_materials))
    texture_subdirectory = TextureDirectory + '/' if export_images else ''
    for mat in bl_materials:
        al_materials[mat.name], tex = get_material_json(mat, texture_subdirectory)
        raw_images.extend(tex)

    if export_images and export_dir:
        # Distinct the List
        export_image_textures(list(set(raw_images)), export_dir)

    return al_materials


def parse_flattened_geometry(context, export_objects):
    """ Triangulate the specified mesh, calculate normals & tessfaces, apply export matrix
        Args:
            context ('bpy.types.context') - Current window manager and data context.
            export_objects ('bpy_prop_collection') - The exported objects.
        Returns:
            json_meshes ('dict') - The data3d meshes dictionary.
    """
    obj_mesh_pairs = [get_obj_mesh_pair(obj, context) for obj in export_objects]
    json_meshes = {}
    # FIXME rename & fix unclarity

    for obj, bl_mesh in obj_mesh_pairs:
        log.debug('Parsing blender mesh to json: %s', bl_mesh.name)
        mesh_materials = [m for m in bl_mesh.materials if m]

        if len(mesh_materials) == 0:
            # No Material Mesh
            json_meshes[bl_mesh.name] = parse_mesh(bl_mesh)
            # Fixme no material key

        else:
            for i, bl_mat in enumerate(mesh_materials):
                faces = [face for face in bl_mesh.polygons if face.material_index == i]
                if len(faces) > 0:
                    mat_name = bl_mat.name
                    json_mesh = parse_mesh(bl_mesh, faces=faces)
                    json_mesh[D3D.m_material] = mat_name

                    json_mesh_name = bl_mesh.name + "-" + mat_name
                    json_meshes[json_mesh_name] = json_mesh

    return json_meshes


def parse_geometry(context, export_objects, al_materials):
    """ Triangulate the specified mesh, calculate normals & tessfaces, apply export matrix
        Args:
            context ('bpy.types.context') - Current window manager and data context.
            export_objects ('bpy_prop_collection') - The exported objects.
            al_materials ('dict') - The data3d materials dictionary.
        Returns:
            data3d_objects ('dict') - The data3d objects dictionary.
    """
    # Fixme PARENT - child objects
    obj_mesh_pairs = [get_obj_mesh_pair(obj, context) for obj in export_objects]

    json_objects = []
    #bl_meshes = [mesh for (obj, mesh) in obj_mesh_pairs]

    for obj, bl_mesh in obj_mesh_pairs:
        json_object = OrderedDict()
        json_object[D3D.o_position] = list(obj.location[0:3])
        json_object[D3D.o_rotation] = list(obj.rotation_euler[0:3])

        json_meshes = OrderedDict()
        mesh_materials = [m for m in bl_mesh.materials if m]

        if len(mesh_materials) == 0:
            # No Material Mesh
            json_meshes[bl_mesh.name] = parse_mesh(bl_mesh)
            json_object[D3D.o_meshes] = json_meshes
            # FIXME what about these, mandatory?
            json_object[D3D.o_materials] = {}
            json_object[D3D.o_material_keys] = []
            json_object[D3D.o_meshKeys] = {}

        else:
            # Multimaterial Mesh
            json_materials = {}
            for i, bl_mat in enumerate(mesh_materials):
                faces = [face for face in bl_mesh.polygons if face.material_index == i]
                if len(faces) > 0:
                    mat_name = bl_mat.name
                    json_mesh = parse_mesh(bl_mesh, faces=faces)
                    json_mesh[D3D.m_material] = mat_name

                    json_mesh_name = bl_mesh.name + "-" + mat_name
                    json_meshes[json_mesh_name] = json_mesh

                    if mat_name in al_materials:
                        json_materials[mat_name] = al_materials[mat_name]

            json_object[D3D.o_meshes] = json_meshes
            json_object[D3D.o_materials] = json_materials
            json_object[D3D.o_mesh_keys] = [key for key in json_meshes.keys()]
            json_object[D3D.o_material_keys] = [key for key in json_materials.keys()]

        json_objects.append(json_object)

    return json_objects


def get_obj_mesh_pair(obj, context):
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

            Args:
                bl_mesh ('bpy.types.Mesh') - The mesh data block to parse.
            Kwargs:
                faces ('list(bpy.types.MeshPolygon)') - The subset of polygons to parse.
            Returns:
                al_mesh ('dict') - The data3d mesh dictionary.
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


        al_mesh = OrderedDict()
        al_mesh[D3D.v_coords] = unpack_list(_vertices)
        al_mesh[D3D.v_normals] = unpack_list(_normals)

        # temp
        al_mesh[D3D.m_position] = [0.0, ]*3 #list(obj.location[0:3])
        al_mesh[D3D.m_rotation] = [0.0, ]*3 #list(obj.rotation_euler[0:3])
        al_mesh['rotDeg'] = [0.0, ]*3
        al_mesh['scale'] = [1.0, ]*3

        if texture_uvs:
            al_mesh[D3D.uv_coords] = unpack_list(_uvs)

        if lightmap_uvs:
            al_mesh[D3D.uv2_coords] = unpack_list(_uvs2)

        return al_mesh


def _write(context, export_path, export_global_matrix, export_selection_only, export_images, export_format, export_al_metadata):
    """ Export the scene as an Archilogic Data3d File
        Args:
            context ('bpy.types.context') - Current window manager and data context.
            export_path ('str') - The filepath to the data3d file.
            export_global_matrix ('Matrix') - The target world matrix.
            export_selection_only ('bool') - Export selected objects only.
            export_images ('bool') - Export associated texture files.
            export_format ('int') - Export interleaved (buffer, 0) or non-interleaved (json, 1).
            export_al_metadata ('bool') - Export Archilogic Metadata, if it exists.
    """
    try:
        output_path = export_path
        to_buffer = True if export_format == 'INTERLEAVED' else False

        if not os.path.exists(os.path.dirname(output_path)):
            os.makedirs(os.path.dirname(output_path))
        log.info('Exporting Scene: %s', output_path)

        if export_selection_only:
            export_objects = [obj for obj in context.selected_objects if obj.type == 'MESH']
        else:
            export_objects = [obj for obj in context.selectable_objects if obj.type == 'MESH']

        export_data = OrderedDict()
        meta = export_data['meta'] = OrderedDict()
        meta['version'] = ModuleInfo.data3d_format_version
        meta['exporter'] = 'Archilogic Data3d Exporter Version: ' + ModuleInfo.add_on_version
        meta['timestamp'] = str(datetime.utcnow())

        data3d = export_data[D3D.r_container] = OrderedDict()
        data3d[D3D.o_position] = [0, ] * 3
        data3d[D3D.o_rotation] = [0, ] * 3
        data3d['rotDeg'] = [0, ] * 3

        materials = parse_materials(export_objects, export_al_metadata, export_images, export_dir=os.path.dirname(output_path))

        if to_buffer:
            data3d[D3D.o_materials] = materials
            meshes = data3d[D3D.o_meshes] = parse_flattened_geometry(context, export_objects)
        else:
            #data3d[D3D.o_meshes] = {}
            #data3d[D3D.o_materials]
            #Fixme parse parent-child hierarchy
            meshes = data3d[D3D.o_children] = parse_geometry(context, export_objects, materials)


        #TODO make texture export optional
        #if EXPORT_IMAGES:
        #export_images(materials)

        serialize_data3d(export_data, output_path, to_buffer=to_buffer)

    except:
        raise Exception('Export Scene failed. ', sys.exc_info())


def save(context,
         filepath='',
         use_selection=False,
         export_images=False,
         export_format='INTERLEAVED',
         export_al_metadata=False,
         global_matrix=None):
    """ Export the scene as an Archilogic Data3d File
        Args:
            context ('bpy.types.context') - Current window manager and data context.
        Kwargs:
            filepath ('str') - The filepath to the data3d file.
            use_selection ('bool') - Export selected objects only.
            export_images ('bool') - Export associated texture files.
            export_mode ('int') - Export interleaved (buffer, 0) or non-interleaved (json, 1).
            export_al_metadata ('bool') - Export Archilogic Metadata, if it exists.
            global_matrix ('Matrix') - The target world matrix.
    """
    if global_matrix is None:
        global_matrix = mathutils.Matrix()

    _write(context, filepath,
           export_global_matrix=global_matrix,
           export_selection_only=use_selection,
           export_images=export_images,
           export_format=export_format,
           export_al_metadata=export_al_metadata)

    return {'FINISHED'}
