import os
import logging

import bpy
from bpy_extras.image_utils import load_image

from . import D3D

# Global Variables
C = bpy.context
D = bpy.data
O = bpy.ops

logging.basicConfig(level='DEBUG', format='%(asctime)s %(levelname)-10s %(message)s')
log = logging.getLogger('archilogic')


def import_material(key, al_material, import_metadata, working_dir):

    bl_material = D.materials.new(key)
    bl_material.use_fake_user = True

    # Import Archilogic Material Datablock (FIXME check PropertyGroup)
    if import_metadata:
        bl_material['Data3d Material'] = al_material

    # Create Blender Material
    create_blender_material(al_material, bl_material, working_dir)

    # Create Cycles Material
    # FIXME: There are three basic material setups for now. (basic, emission, transparency)
    # create_cycles_material(al_materials[key], bl_material)
    return bl_material

def create_cycles_material(al_mat, bl_mat):
    bl_mat.use_nodes = True
    node_tree = bl_mat.node_tree

    # Clear the node tree
    for node in node_tree.nodes:
        node_tree.nodes.remove(node)

    # Material Output Node
    output_node = node_tree.nodes.new('ShaderNodeOutputMaterial')
    output_node.location = (300, 100)

    if D3D.map_alpha in al_mat:
        log.debug('advanced: transparency material')

    elif D3D.coef_emit in al_mat:
        log.debug('emission material')

    else:
        log.debug('basic material')


def create_blender_material(al_mat, bl_mat, working_dir):
    # Set default material settings
    bl_mat.diffuse_intensity = 1
    bl_mat.specular_intensity = 1

    if D3D.col_diff in al_mat:
        bl_mat.diffuse_color = al_mat[D3D.col_diff]
    if D3D.col_spec in al_mat:
        bl_mat.specular_color = al_mat[D3D.col_spec]
    if D3D.coef_spec in al_mat:
        bl_mat.specular_hardness = int(al_mat[D3D.coef_spec])
    if D3D.coef_emit in al_mat:
        bl_mat.emit = float(al_mat[D3D.coef_emit])
    if D3D.opacity in al_mat:
        opacity = al_mat[D3D.opacity]
        if opacity < 1:
            bl_mat.use_transparency = True
            bl_mat.transparency_method = 'Z_TRANSPARENCY'
            bl_mat.alpha = opacity

    #FIXME unify: filter key contains 'map' -> set image texture(entry, key, ...)
    if D3D.map_diff in al_mat:
        set_image_texture(bl_mat, al_mat[D3D.map_diff], 'DIFFUSE', working_dir)
    if D3D.map_spec in al_mat:
        set_image_texture(bl_mat, al_mat[D3D.map_spec], 'SPECULAR', working_dir)
    if D3D.map_norm in al_mat:
        set_image_texture(bl_mat, al_mat[D3D.map_norm], 'NORMAL', working_dir)
    if D3D.map_alpha in al_mat:
        set_image_texture(bl_mat, al_mat[D3D.map_alpha], 'ALPHA', working_dir)
    if D3D.uv_scale in al_mat:
        size = al_mat[D3D.uv_scale]
        for tex_slot in bl_mat.texture_slots:
            if tex_slot is not None:
                tex_slot.scale[0] = 1/size[0]
                tex_slot.scale[1] = 1/size[1]


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


def get_image_datablock(image_path, image_directory, recursive=False):
    """ Load the image
    """
    # FIXME if addon is made available externally: make use image search optional
    image_directory = os.path.normpath(image_directory)
    img = load_image(image_path, dirname=image_directory, recursive=recursive, check_existing=True)
    if img is None:
        # FIXME Failed to load images report for automated baking
        log.warning('Warning: Image could not be loaded: %s in directory %s ', image_path, dir)
        return None
    img.use_fake_user = True
    return img


def import_material_node_groups():

    filepath = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'node-library.blend')

    with bpy.data.libraries.load(filepath) as (data_from, data_to):
        data_to.node_groups = data_from.node_groups
        # FIXME loads all node groups (-> load selective)

    for node_group in data_to.node_groups:
        log.debug('Importing material node group: %s', node_group.name)
        node_group.use_fake_user = True


#################
# Setup         #
#################

def setup():
    # Import the Cycles material node groups from reference file
    log.info('Setting up material_utils.')
    import_material_node_groups()
