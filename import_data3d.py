###
# Data 3d Documentation : https://task.archilogic.com/projects/dev/wiki/3D_Data_Pipeline
###

import os
import sys
import json
import mathutils

import bpy
import bmesh

from bpy_extras.image_utils import load_image


# Global Variables
C = bpy.context
D = bpy.data
O = bpy.ops

#FIXME Logging & Timestamps


def read_file(filepath=''):
    if os.path.exists(filepath):
        # FIXME ensure ending
        data3d_file = open(filepath, mode='r')
        json_str = data3d_file.read()
        return json.loads(json_str)
    else:
        raise Exception('File does not exist, ' + filepath)

# FIXME implement (and make optional): import metadata archilogic
# FIXME modularize import/export materials


def import_materials_cycles(data3d, filepath):
    """ Import the material references and create blender or cycles materials (?)
    """
    working_dir = os.path.dirname(filepath) #filepath to data3d file (in case of relative paths)
    print('Importing Materials')

    al_materials = data3d['materials']
    bl_materials = {}

    # Import node groups from library-file
    import_node_groups()

    for key in al_materials.keys():

        bl_material = D.materials.new(key) # Assuming that the materials have a unique naming convention
        bl_material.use_fake_user = True
        # Create Archilogic Material Datablock #FIXME check: PropertyGroup
        bl_material['Data3d Material Settings'] = al_materials[key]
        # (...)

        # Create Cycles Material
        # FIXME: To maintain compatibility with bake script/json exporter > import blender material
        create_blender_material(al_materials[key], bl_material, working_dir)
        # FIXME: There are three basic material setups for now. (basic, emission, transparency)
        #create_cycles_material(al_materials[key], bl_material)

        bl_materials[key] = bl_material
    return bl_materials


def create_cycles_material(al_mat, bl_mat):
    bl_mat.use_nodes = True
    node_tree = bl_mat.node_tree

    # Clear the node tree
    for node in node_tree.nodes:
        node_tree.nodes.remove(node)

    # Material Output Node
    output_node = node_tree.nodes.new('ShaderNodeOutputMaterial')
    output_node.location = (300, 100)

    if 'alphaMap' in al_mat:
        print('advanced: transparency material')

    elif 'emit' in al_mat:
        print('emission material')

    else:
        print('basic material')


def create_blender_material(al_mat, bl_mat, working_dir):
    # Set default material settings
    bl_mat.diffuse_intensity = 1
    bl_mat.specular_intensity = 1

    # FIXME global values
    if 'colorDiffuse' in al_mat:
        bl_mat.diffuse_color = al_mat['colorDiffuse']
    if 'colorSpecular' in al_mat:
        bl_mat.specular_color = al_mat['colorSpecular']
    if 'specularCoef' in al_mat:
        bl_mat.specular_hardness = int(al_mat['specularCoef'])
    if 'lightEmissionCoef' in al_mat:
        bl_mat.emit = float(al_mat['lightEmissionCoef'])
    if 'opacity' in al_mat:
        opacity = al_mat['opacity']
        if opacity < 1:
            bl_mat.use_transparency = True
            bl_mat.transparency_method = 'Z_TRANSPARENCY'
            bl_mat.alpha = opacity

    #FIXME unify: filter key contains 'map' -> set image texture(entry, key, ...)
    if 'mapDiffuse' in al_mat:
        set_image_texture(bl_mat, al_mat['mapDiffuse'], 'DIFFUSE', working_dir)
    if 'mapSpecular' in al_mat:
        set_image_texture(bl_mat, al_mat['mapSpecular'], 'SPECULAR', working_dir)
    if 'mapNormal' in al_mat:
        set_image_texture(bl_mat, al_mat['mapNormal'], 'NORMAL', working_dir)
    if 'mapAlpha' in al_mat:
        set_image_texture(bl_mat, al_mat['mapAlpha'], 'ALPHA', working_dir)


def set_image_texture(bl_mat, imagepath, map, working_dir):
    # FIXME map enum in ['NORMAL', 'DIFFUSE', ('ALPHA',) 'SPECULAR']
    # Create the blender image texture
    name = map + '-' + os.path.splitext(os.path.basename(imagepath))[0]
    texture = bpy.data.textures.new(name=name, type='IMAGE')
    texture.use_fake_user = True
    image = get_image_datablock(imagepath, working_dir, recursive=True)

    texture.image = image
    tex_slot = bl_mat.texture_slots.add()
    tex_slot.texture_coords = 'UV'
    tex_slot.texture = texture

    if map == 'DIFFUSE':
        tex_slot.use_map_color_diffuse = True
    if map == 'NORMAL':
        tex_slot.use_map_color_diffuse = False
        texture.use_normal_map = True
        tex_slot.use_map_normal = True
    if map == 'SPECULAR':
        tex_slot.use_map_color_diffuse = False
        texture.use_normal_map = True
        tex_slot.use_map_specular = True
    if map == 'ALPHA':
        tex_slot.use_map_color_diffuse = False
        texture.use_normal_map = True
        tex_slot.use_map_alpha = True
        bl_mat.use_transparency = True
        bl_mat.transparency_method = 'Z_TRANSPARENCY'


def get_image_datablock(image_path, dir, recursive=False):
    """ Load the image
    """
    #FIXME if addon is made available externally: make use image search optional
    dir = os.path.normpath(dir)
    img = load_image(image_path, dirname=dir, recursive=recursive, check_existing=True)
    if img is None:
        #Fixme for now, raise an exception if image is not found (-> # change to warning)
        #raise Exception('Image could not be loaded:' + image_path + 'in directory: ' + dir)
        print('Warning: Image could not be loaded:' + image_path + 'in directory: ' + dir)
        return None
    img.use_fake_user = True
    return img


def import_node_groups():

    filepath = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'node-library.blend')

    with bpy.data.libraries.load(filepath) as (data_from, data_to):
        data_to.node_groups = data_from.node_groups
        # FIXME loads all node groups (-> load selective)

    for node_group in data_to.node_groups:
        print(node_group.name)
        node_group.use_fake_user = True


def import_scene(data3d, global_matrix, filepath, import_materials):
    """ Import the scene, parse data3d, create meshes (...)
    """
    def get_sorted_list_from_dict(dict):
        sorted_list = []
        sorted_keys = sorted([int(key) for key in dict.keys()])
        for key in sorted_keys:
            sorted_list.append(dict[str(key)])
        return sorted_list

    def get_child_nodes(node):
        if 'children' in node:
            if node['children'] is not []:
                return node['children']
        return None

    def get_nodes_recursive(root):
        children = get_child_nodes(root)

        # FIXME the parent object is ignored
        if children:
            for child in children:
                data = {
                    'nodeId': child['nodeId'],
                    'parentId': root['nodeId'],
                    'meshes': child['meshes'],
                    'materials': child['materials']
                }
                data3d_object_data.append(data)
                get_nodes_recursive(child)
                # Add to mesh dict: nodeId, parent, meshes, , -> object

    def create_mesh(data):
        bm = bmesh.new()

        uv_layer = None
        if 'per_face_uvs' in data:
            uv_layer = bm.loops.layers.uv.new('UVTexture')

        print('creating mesh ' + data['name'])
        for f_idx, face in enumerate(data['faces']):
            #debug:
            if len(face) % 3 > 0:
                print('Warning: inconsistent vertexes, length of the list is not a multiple of 3')
            bm_verts = []
            for v in [face[x:x+3] for x in range(0, len(face), 3)]:
                bm_verts.append(bm.verts.new(v))

            bm.verts.index_update()
            f = bm.faces.new(bm_verts)

            if uv_layer:
                #uv_layer = bm.loops.layers.uv.active #FIXME
                for l_idx, loop in enumerate(f.loops):
                    loop[uv_layer].uv = data['per_face_uvs'][f_idx][l_idx] #FIXME "perFaceUvs, find better solution

        #TODO TEXTURE coordinates, if they exist

            #TODO Vertex Normals, if they exist
        #TODO if fails?: delete "me" from bpy.data.meshes (garbage collector when saving/reopening the scene would delete it
        # Assign Material
        #(multimaterial?)

        # Create new mesh
        me = D.meshes.new(data['name'] + '-mesh')
        bm.to_mesh(me)
        # finally:
        bm.free()
        return me

    # def beautify():
        # Clean mesh / remove faces that don't span an area (...)
        # split
        # Handle double sided Faces

    #def get_material(name):
    #    if bpy.data.materials.get(name) is not None:
    #        return bpy.data.materials[name]
    #    else:
    #        print('Material could not be found: ' + name)
    #        return None
    try:
        data3d_object_data = []
        bl_materials = {}
        get_nodes_recursive(data3d)

        # Parse Data3d information (Future-> hierarchy, children (...))
        for object_data in data3d_object_data:

            print(object_data['nodeId'])
            # Import mesh-materials

            if import_materials:
                bl_materials = import_materials_cycles(object_data, filepath)

            print(''.join([mat.name for mat in bl_materials.values()]))

            #  Import meshes
            meshes = object_data['meshes']
            for key in meshes.keys():
                mesh = meshes[key]
                # FIXME temporary (because normals is a dictionary)
                positions_raw = get_sorted_list_from_dict(mesh['positions'])
                normals_raw = get_sorted_list_from_dict(mesh['normals'])
                mesh_data = {
                    'name': key,
                    'material': mesh['material'],
                    #'vertices': [mesh['positions'][x:x+3] for x in range(0, len(mesh['positions']), 3)],
                    'faces': [positions_raw[x:x+9] for x in range(0, len(positions_raw), 9)],
                    'normals': [normals_raw[x:x+3] for x in range(0, len(normals_raw), 3)],
                    #object-id
                }

                if 'uvs' in mesh:
                    if not mesh['uvs']:
                        print('No uvs in mesh.')
                    else:
                        uvs_raw = get_sorted_list_from_dict(mesh['uvs'])
                        uvs = [uvs_raw[x:x+2] for x in range(0, len(uvs_raw), 2)]
                        mesh_data['per_face_uvs'] = [uvs[x:x+3] for x in range(0, len(uvs), 3)]
                    #FIXME flexible / NGONs? find good option to tie face data to uv/normal data
                mesh = create_mesh(mesh_data)
                # Create new object and link it to the scene
                # FIXME Fallback if mesh creation fails? (for now we want all the errors
                ob = D.objects.new(mesh_data['name'], mesh)
                if import_materials:
                    ob.data.materials.append(bl_materials[mesh_data['material']])
                ob.matrix_world = global_matrix
                ob.show_name = True #DEBUG
                C.scene.objects.link(ob)

    except:
        #FIXME clean scene from created data-blocks
        raise Exception('Import Scene failed. ', sys.exc_info())



########
# Main #
########


def load(operator, context, filepath='', import_materials=True, global_matrix=None):
    """ Called by the user interface or another script.
        (...)
    """
    if global_matrix is None:
        global_matrix = mathutils.Matrix()
    #try:
    # Import the file - Json dictionary
    data3d = read_file(filepath=filepath)


    # material_references = ...
    #if import_materials:
    #    import_materials_cycles(data3d, filepath)

    import_scene(data3d, global_matrix, filepath, import_materials)

    C.scene.update()

    return {'FINISHED'}

    # except:
    #     print('Data3d import failed: ', sys.exc_info())
    #     return {'CANCELLED'}
