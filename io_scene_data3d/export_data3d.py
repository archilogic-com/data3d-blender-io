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
from io_scene_data3d.material_utils import get_al_material, get_default_al_material
from io_scene_data3d.data3d_utils import D3D, serialize_data3d


# Global Variables
C = bpy.context
D = bpy.data
O = bpy.ops

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


    al_materials = OrderedDict()
    bl_materials = []
    raw_images = []

    def export_image_textures(bl_images, dest_dir):
        """ Copy the image texture to destination directory.
            Args:
                bl_images ('list(bpy.types.Image)') - The associated image data blocks.
                dest_dir ('str') - The texture export directory.
        """
        log.debug("Export images %s", " * ".join([img.name for img in bl_images]))

        for image in bl_images:
            filepath = image.filepath_from_user()
            if os.path.exists(filepath):
                tex_dir = os.path.join(dest_dir, TextureDirectory)
                if not os.path.exists(tex_dir):
                    os.makedirs(tex_dir)
                shutil.copy(filepath, os.path.join(tex_dir))
            else:
                log.warn("File does not exist: %s", filepath)

    for obj in export_objects:
        obj_materials = [slot.material for slot in obj.material_slots if slot.material is not None]
        bl_materials.extend(obj_materials)

    bl_materials = list(set(bl_materials))
    texture_subdirectory = TextureDirectory + '/' if export_images else ''
    for mat in bl_materials:
        al_materials[mat.name], tex = get_al_material(mat, texture_subdirectory, from_metadata=export_metadata)
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
    default_material = None
    # FIXME rename (json) & fix unclarity

    for obj, bl_mesh in obj_mesh_pairs:
        log.info('Parsing blender mesh to json: %s', bl_mesh.name)
        mesh_materials = [m for m in bl_mesh.materials if m]

        if len(mesh_materials) == 0:
            # No Material Mesh
            json_mesh = parse_mesh(bl_mesh)
            json_mesh[D3D.m_material] = D3D.mat_default
            if default_material is None:
                default_material = get_default_al_material()
            json_meshes[bl_mesh.name] = json_mesh
        else:
            for i, bl_mat in enumerate(mesh_materials):
                faces = [face for face in bl_mesh.polygons if face.material_index == i]
                if len(faces) > 0:
                    mat_name = bl_mat.name
                    json_mesh = parse_mesh(bl_mesh, material_index=i)
                    json_mesh[D3D.m_material] = mat_name

                    json_mesh_name = bl_mesh.name + "-" + mat_name
                    json_meshes[json_mesh_name] = json_mesh

    return json_meshes, default_material


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
    # bl_meshes = [mesh for (obj, mesh) in obj_mesh_pairs]

    for obj, bl_mesh in obj_mesh_pairs:
        json_object = OrderedDict()
        # Fixme: export object position & rotation (right now, pos & rot are applied to the mesh when parsed
        # json_object[D3D.o_position] = list(obj.location[0:3])
        # json_object[D3D.o_rotation] = list(obj.rotation_euler[0:3])

        json_meshes = OrderedDict()
        mesh_materials = [m for m in bl_mesh.materials if m]

        if len(mesh_materials) == 0:
            # Parse mesh with no material.
            json_meshes[bl_mesh.name] = parse_mesh(bl_mesh)
            json_object[D3D.o_meshes] = json_meshes

        else:
            # Parse mesh with one or more materials.
            json_materials = {}
            for i, bl_mat in enumerate(mesh_materials):
                faces = [face for face in bl_mesh.polygons if face.material_index == i]
                if len(faces) > 0:
                    mat_name = bl_mat.name
                    json_mesh = parse_mesh(bl_mesh, material_index=i)
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
    depsgraph = context.evaluated_depsgraph_get()
    mesh = obj.to_mesh(preserve_all_data_layers=True, depsgraph=depsgraph)
    mesh.transform(Matrix.Rotation(-math.pi / 2, 4, 'X') @ obj.matrix_world)

    mesh.calc_loop_triangles()
    mesh.calc_normals()

    return (obj, mesh)


def parse_mesh(bl_mesh, material_index=None):
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
                material_index - The subset of triangles to parse wich have the corresponding material index.
            Returns:
                al_mesh ('dict') - The data3d mesh dictionary.
        """

        # UV Textures by name
        # FIXME if channel names do not apply, get 1 channel as uv and 2nd channel as lightmap Uv
        texture_uvs = bl_mesh.uv_layers.get('UVMap')
        lightmap_uvs = bl_mesh.uv_layers.get('UVLightmap')

        vertices = []
        normals = []
        uvs = []
        uvs2 = []

        # FIXME What does calc_normals split do for custom vertex normals?
        # bl_mesh.calc_normals_split()

        invalid_uv = False

        for tri in bl_mesh.loop_triangles:
            if material_index is None or material_index == tri.material_index:
                for vert_index in tri.vertices:
                    co = bl_mesh.vertices[vert_index].co
                    no = bl_mesh.vertices[vert_index].normal
                    vertices += [co.x, co.y, co.z]
                    normals  += [no.x, no.y, no.z]
                
                if texture_uvs is not None or lightmap_uvs is not None:
                    for loop_index in tri.loops:
                        if texture_uvs is not None:
                            uv = texture_uvs.data[loop_index].uv
                            uvs += [uv.x, uv.y]
                        if lightmap_uvs is not None:
                            uv = lightmap_uvs.data[loop_index].uv
                            uvs2 += [uv.x, uv.y]
                            if uv.x > 1.0 or uv.y > 1.0 or uv.x < 0.0 or uv.y < 0.0:
                                invalid_uv = True
                    
        if invalid_uv:
            log.info('Invalid values in UVLightmap, index: %d', material_index)

        al_mesh = OrderedDict()
        al_mesh[D3D.v_coords] = vertices
        al_mesh[D3D.v_normals] = normals

        # temp
        al_mesh[D3D.m_position] = [0.0, ]*3  #list(obj.location[0:3])
        al_mesh[D3D.m_rotation] = [0.0, ]*3  #list(obj.rotation_euler[0:3])
        al_mesh['rotDeg'] = [0.0, ]*3
        al_mesh['scale'] = [1.0, ]*3

        if texture_uvs:
            al_mesh[D3D.uv_coords] = uvs

        if lightmap_uvs:
            al_mesh[D3D.uv2_coords] = uvs2

        return al_mesh


def _write(context, export_path, global_matrix, export_selection_only, export_images, export_format, export_al_metadata):
    """ Export the scene as an Archilogic Data3d File
        Args:
            context ('bpy.types.context') - Current window manager and data context.
            export_path ('str') - The filepath to the data3d file.
            global_matrix ('Matrix') - The target world matrix.
            export_selection_only ('bool') - Export selected objects only.
            export_images ('bool') - Export associated texture files.
            export_format ('int') - Export interleaved (buffer, 0) or non-interleaved (json, 1).
            export_al_metadata ('bool') - Export Archilogic Metadata, if it exists.
    """
    # Fixme: use global matrix from param export_global_matrix
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

        data3d = export_data[D3D.r_container] = OrderedDict()
        data3d[D3D.o_position] = [0, ] * 3
        data3d[D3D.o_rotation] = [0, ] * 3
        data3d['rotDeg'] = [0, ] * 3

        materials = parse_materials(export_objects, export_al_metadata, export_images, export_dir=os.path.dirname(output_path))

        if to_buffer:
            data3d[D3D.o_meshes], default_material = parse_flattened_geometry(context, export_objects)
            if default_material:
                materials[D3D.mat_default] = default_material
            data3d[D3D.o_materials] = materials
        else:
            #Fixme: add functionality to parse parent-child hierarchy for data3d.json
            #data3d[D3D.o_meshes] = {}
            #data3d[D3D.o_materials]
            data3d[D3D.o_children] = parse_geometry(context, export_objects, materials)

        serialize_data3d(export_data, output_path, to_buffer=to_buffer)

    except:
        raise Exception('Export Scene failed. ', sys.exc_info())


def save(context,
         **args):
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
    if args['config_logger']:
        logging.basicConfig(level='DEBUG', format='%(asctime)s %(levelname)-10s %(message)s', stream=sys.stdout)

    _write(context, args['filepath'],
           global_matrix=args['global_matrix'],
           export_selection_only=args['use_selection'],
           export_images=args['export_images'],
           export_format=args['export_format'],
           export_al_metadata=args['export_al_metadata'])

    return {'FINISHED'}
