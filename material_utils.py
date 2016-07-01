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
    create_cycles_material(al_material, bl_material)
    return bl_material


def create_blender_material(al_mat, bl_mat, working_dir):
    # Set default material settings
    bl_mat.diffuse_intensity = 1
    bl_mat.specular_intensity = 1

    if D3D.col_diff in al_mat:
        bl_mat.diffuse_color = al_mat[D3D.col_diff]
    else:
        bl_mat.diffuse_color = (0.85,)*3
    if D3D.col_spec in al_mat:
        bl_mat.specular_color = al_mat[D3D.col_spec]
    else:
        bl_mat.diffuse_color = (0.25,)*3
    if D3D.coef_spec in al_mat:
        bl_mat.specular_hardness = int(al_mat[D3D.coef_spec])
    else:
        bl_mat.specular_hardness = 1
    if D3D.coef_emit in al_mat:
        bl_mat.emit = float(al_mat[D3D.coef_emit])
    if D3D.opacity in al_mat:
        opacity = al_mat[D3D.opacity]
        if opacity < 1:
            bl_mat.use_transparency = True
            bl_mat.transparency_method = 'Z_TRANSPARENCY'
            bl_mat.alpha = opacity

    ref_maps = get_reference_maps(al_mat)
    for map_key in ref_maps:
        set_image_texture(bl_mat, ref_maps[map_key], map_key, working_dir)

    if D3D.uv_scale in al_mat:
        size = al_mat[D3D.uv_scale]
        for tex_slot in bl_mat.texture_slots:
            if tex_slot is not None:
                tex_slot.scale[0] = 1/size[0]
                tex_slot.scale[1] = 1/size[1]


def create_cycles_material(al_mat, bl_mat):
    C.scene.render.engine = 'CYCLES'
    bl_mat.use_nodes = True
    node_tree = bl_mat.node_tree

    # Clear the node tree
    for node in node_tree.nodes:
        node_tree.nodes.remove(node)

    # Material group node (no datablock assigned)
    node_group = node_tree.nodes.new('ShaderNodeGroup')
    # Material Output Node
    output_node = node_tree.nodes.new('ShaderNodeOutputMaterial')
    output_node.location = (300, 100)

    if D3D.map_alpha in al_mat:
        log.debug('advanced: transparency material')
        node_group.node_tree = D.node_groups['archilogic-transparency']

    elif D3D.coef_emit in al_mat:
        log.debug('emission material')
        node_group.node_tree = D.node_groups['archilogic-emission']

    else:
        log.debug('basic material')
        # Add the corresponding Material node group ('archilogic-basic')
        node_group.node_tree = D.node_groups['archilogic-basic']

        # Create the nodes for the texture maps
        ref_maps = get_reference_maps(al_mat)

        # Create the nodes for other inputs

        # Connect the nodes

def get_reference_maps(al_mat):
    map_types = [D3D.map_diff, D3D.map_spec, D3D.map_norm, D3D.map_alpha, D3D.map_light]
    ref_maps = {}
    for map_key in map_types:
        map_key_source = map_key + D3D.map_suffix_source
        map_key_preview = map_key + D3D.map_suffix_preview

        maps = [
            al_mat[map_key_source] if map_key_source in al_mat else '',
            al_mat[map_key] if map_key in al_mat else '',
            al_mat[map_key_preview] if map_key_preview in al_mat else ''
        ]
        ref_map = next((m for m in maps if (m and not m.endswith('.dds'))), '')
        if ref_map:
            ref_maps[map_key] = ref_map
    return ref_maps


def set_image_texture(bl_mat, imagepath, map_key, working_dir):
    # Create the blender image texture
    name = map_key + '-' + os.path.splitext(os.path.basename(imagepath))[0]
    texture = bpy.data.textures.new(name=name, type='IMAGE')
    texture.use_fake_user = True
    image = get_image_datablock(imagepath, working_dir, recursive=True)

    texture.image = image
    tex_slot = bl_mat.texture_slots.add()
    tex_slot.texture_coords = 'UV'
    tex_slot.texture = texture

    if map_key == D3D.map_diff:
        tex_slot.use_map_color_diffuse = True
    elif map_key == D3D.map_norm:
        tex_slot.use_map_color_diffuse = False
        texture.use_normal_map = True
        tex_slot.use_map_normal = True
    elif map_key == D3D.map_spec:
        tex_slot.use_map_color_diffuse = False
        texture.use_normal_map = True
        tex_slot.use_map_specular = True
    elif map_key == D3D.map_alpha:
        tex_slot.use_map_color_diffuse = False
        texture.use_normal_map = True
        tex_slot.use_map_alpha = True
        bl_mat.use_transparency = True
        bl_mat.transparency_method = 'Z_TRANSPARENCY'
    # FIXME Lightmaps?
    else:
        log.error('Image Texture type not found, %s', map_key)


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
