###
# Data 3d Documentation : https://task.archilogic.com/projects/dev/wiki/3D_Data_Pipeline
###

import os
import sys
import json

import bpy
import bmesh

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

#FIXME implement (and make optional): import metadata archilogic
# FIXME modularize import/export materials
def import_materials_cycles(data3d):
    """ Import the material references and create blender or cycles materials (?)
    """
    try:
        print('Importing Materials')
        al_materials = data3d['materials']

        # Import node groups from library-file
        import_node_groups()

        for key in al_materials.keys():

            bl_material = D.materials.new(key) # Assuming that the materials have a unique naming convention

            # Create Archilogic Material Datablock
            # (...)

            # Create Cycles Material
            # FIXME: To maintain compatibility with bake script/json exporter > import blender material
            create_blender_material(al_materials[key], bl_material)
            # FIXME: There are three basic material setups for now. (basic, emission, transparency)
            create_cycles_material(al_materials[key], bl_material)



    except:
        raise Exception('Import materials failed. ', sys.exc_info)

def create_cycles_material(al_mat, bl_mat):
    bl_mat.use_nodes = True
    node_tree = bl_mat.node_tree

    # Clear the node tree
    for node in node_tree.nodes:
        node_tree.nodes.remove(node)

    # Material Output Node
    output_node = node_tree.nodes.new('ShaderNodeOutputMaterial')
    output_node.location = (300, 100)


    if 'alphaMap' in al_material:
        print('advanced: transparency material')

    elif 'emit' in al_material:
        print('emission material')

    else:
        print('basic material')

def create_blender_material(al_mat, bl_mat):
    # Set default material settings
    bl_mat.diffuse_intensity = 1
    bl_mat.specular_intensity = 1

    # FIXME global values
    if 'colorDiffuse' in al_mat:
        bl_mat.diffuse_color = al_mat['colorDiffuse']
    if 'specularDiffuse' in al_mat:
        bl_mat.specular_color = al_mat['colorSpecular']
    if 'specularCoef' in al_mat:
        bl_mat.specular_hardness = int(al_mat['specularCoef'])
    if 'lightEmissionCoef' in al_mat:
        bl_mat.emit = float(al_mat['lightEmissionCoef'])
    if 'opacity' in al_mat:
        opacity = al_mat['opacity']
        if opacity < 1:
            bl_mat.use_transparency = True
            bl_mat.transparency_method = 'Z-Transparency'
            bl_mat.alpha = opacity

    if 'mapDiffuse' in al_mat:
        set_image_texture(bl_mat, al_mat['mapDiffuse'], 'DIFFUSE')
    if 'mapSpecular' in al_mat:
        set_image_texture(bl_mat, al_mat['mapSpecular'], 'SPECULAR')
    if 'mapNormal' in al_mat:
        set_image_texture(bl_mat, al_mat['mapNormal'], 'NORMAL')
    if 'mapAlpha' in al_mat:
        set_image_texture(bl_mat, al_mat['mapAlpha'], 'ALPHA')

def set_image_texture(bl_mat, imagepath, map):
    #FIXME map enum in ['NORMAL', 'DIFFUSE', ('ALPHA',) 'SPECULAR']
    #FIXME
    def load_image(imagepath):
        # FIXME: if image is already in data.images, return that
        # (also maybe check if texture already exists?) (attention: data block names are not a reliable source
        print('Find image file in Path')

        # Raise Exception if image is not found

    # Create the blender image texture
    name = map + '-' + os.path.splitext(os.path.basename(imagepath))
    texture = bpy.data.textures.new(name=name, type='IMAGE')
    image = load_image(imagepath)

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
        bl_mat.transparency_method = 'Z-TRANSPARENCY'



def import_node_groups():

    filepath = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'node-library.blend')

    with bpy.data.libraries.load(filepath) as (data_from, data_to):
        data_to.node_groups = data_from.node_groups
        # FIXME loads all node groups (-> load selective)

    for node_group in data_to.node_groups:
        print(node_group.name)
        node_group.use_fake_user = True

def create_template_node_tree(requested_types=['DIFFUSE']):
    #
    def structure_nodes(nodes, type):
        color_presets = {'map':(0.7, 0.9, 0.5), 'shader':(0.1, 0.2, 0.7)}

        for key, node in nodes.items():
            node.name = key + '-' + type
            node.label = type
            node.use_custom_color = True
            node.color = color_presets[type]

        # FIXME node positions for visibility / clarity / inspection

    node_group = D.node_groups.new('template-node-tree', 'ShaderNodeTree')
    node_group.use_fake_user = True

    texture_nodes = {}
    shader_nodes = {}

    # Add the nodes to the group
    for map in ['diffuse', 'normal', 'specular', 'alpha']:
        texture_nodes[map] = node_group.nodes.new('ShaderNodeTexImage')

    shader_nodes['mix'] = node_group.nodes.new('ShaderNodeMixShader')
    shader_nodes['bsdf-diffuse'] = node_group.nodes.new('ShaderNodeBsdfDiffuse')
    shader_nodes['bsdf-glossy'] = node_group.nodes.new('ShaderNodeBsdfGlossy')

    structure_nodes(texture_nodes, 'map')
    structure_nodes(shader_nodes, 'shader')

    # Link the nodes


    # The idea is to use the group as a template (with the correct links already setup
    # Then instantiate the group for each material import and adjust the references
    # OR create node inputs for all relevant inputs (leave the template intact) although would mute be possible?
    # Create a fake user
    #Link the node tree input (if necessary)
    #Link the node tree output to the material output, if necessary
    #http://blender.stackexchange.com/questions/5387/how-to-handle-creating-a-node-group-in-a-script
    #Mute the unused nodes


def import_scene(data3d):
    """ Import the scene, parse data3d, create meshes (...)
    """
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

    # Parse Data3d information (Future-> hierarchy, children (...))
    try:
        meshes = data3d['meshes']
        for key in meshes.keys():
            mesh = meshes[key]
            # FIXME temporary (because normals is a dictionary)
            normals_raw = list(mesh['normals'].values())
            mesh_data = {
                'name': key,
                'material': mesh['material'],
                #'vertices': [mesh['positions'][x:x+3] for x in range(0, len(mesh['positions']), 3)],
                'faces': [mesh['positions'][x:x+9] for x in range(0, len(mesh['positions']), 9)],
                'normals': [normals_raw[x:x+3] for x in range(0, len(normals_raw), 3)],
                #object-id
            }
            if 'uvs' in mesh:
                uvs = [mesh['uvs'][x:x+2] for x in range(0, len(mesh['uvs']), 2)]
                mesh_data['per_face_uvs'] = [uvs[x:x+3] for x in range(0, len(uvs), 3)]
                #FIXME flexible / NGONs? find good option to tie face data to uv/normal data
            mesh = create_mesh(mesh_data)
            # Create new object and link it to the scene
            # FIXME Fallback if mesh creation fails? (for now we want all the errors
            ob = D.objects.new(mesh_data['name'], mesh)
            ob.show_name = True #DEBUG
            C.scene.objects.link(ob)

    except:
        raise Exception('Import Scene failed. ' + sys.exc_info())



########
# Main #
########

def load(operator, context, filepath='',
    import_materials=True
    ):
    """ Called by the user interface or another script.
        (...)
    """

    #try:
    # Import the file - Json dictionary
    data3d = read_file(filepath=filepath)
    meshes = data3d['meshes']
    for key in meshes.keys():
        print('Mesh: ' + key + ", Material: " + meshes[key]['material'])

    # material_references = ...
    if import_materials:
        import_materials_cycles()

    import_scene(data3d)

    return {'FINISHED'}

    # except:
    #     print('Data3d import failed: ', sys.exc_info())
    #     return {'CANCELLED'}
