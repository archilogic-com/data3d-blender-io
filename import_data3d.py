###
# Data 3d Documentation : https://task.archilogic.com/projects/dev/wiki/3D_Data_Pipeline
###

import os
import sys
import json
import mathutils
import logging
import array
import time

import bpy
import bmesh

from bpy_extras.image_utils import load_image
from bpy_extras.io_utils import unpack_list


# Global Variables
C = bpy.context
D = bpy.data
O = bpy.ops

#FIXME Logging & Timestamps
logging.basicConfig(level='DEBUG', format='%(asctime)s %(levelname)-10s %(message)s')
log = logging.getLogger('archilogic')


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


def import_data3d_materials(object_data, filepath):
    """ Import the material references and create blender or cycles materials (?)
    """
    working_dir = os.path.dirname(filepath) #filepath to data3d file (in case of relative paths)
    log.info('Importing Materials')

    al_materials = object_data['materials']
    bl_materials = {}

    # Import node groups from library-file
    import_material_node_groups()

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
        log.debug('advanced: transparency material')

    elif 'emit' in al_mat:
        log.debug('emission material')

    else:
        log.debug('basic material')


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
    if 'size' in al_mat:
        size = al_mat['size']
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


def get_image_datablock(image_path, dir, recursive=False):
    """ Load the image
    """
    #FIXME if addon is made available externally: make use image search optional
    dir = os.path.normpath(dir)
    img = load_image(image_path, dirname=dir, recursive=recursive, check_existing=True)
    if img is None:
        #raise Exception('Image could not be loaded:' + image_path + 'in directory: ' + dir)
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


def import_scene(data3d, global_matrix, filepath, import_materials):
    """ Import the scene, parse data3d, create meshes (...)
    """

    def get_node_data(node, root=None):
        data = {
                    'nodeId': node['nodeId'],
                    'parentId': root['nodeId'] if root else 'root',
                    'meshes': node['meshes'] if 'meshes' in node else [],
                    'materials': node['materials'] if 'materials' in node else [],
                    'position': node['position'] if 'position' in node else [0, 0, 0],
                    'rotation': node['rotRad'] if 'rotRad' in node else [0, 0, 0],
                }
        return data

    def get_nodes_recursive(root):
        recursive_data = []
        # Support non-flattened arrays (remove eventually)
        children = root['children'] if 'children' in root else []
        if children is not []:
            for child in children:
                data = get_node_data(child, root)
                recursive_data.append(data)
                recursive_data.extend(get_nodes_recursive(child))
        return recursive_data

    def get_mesh_data(mesh, name):
        mesh_data = {
            'name': name,
            'material': mesh['material'],
            # Vertex location, normal and uv coordinates, referenced by indices
            'verts_loc': [tuple(mesh['positions'][x:x+3]) for x in range(0, len(mesh['positions']), 3)],
            'verts_nor': [tuple(mesh['normals'][x:x+3]) for x in range(0, len(mesh['normals']), 3)],
            'position': mesh['position'] if 'position' in mesh else [0, 0, 0],
            'rotation': mesh['rotDeg'] if 'rotDeg' in mesh else [0, 0, 0]
        }

        has_uvs = ('uvs' in mesh)
        if has_uvs:
            mesh_data['verts_uvs'] = [tuple(mesh['uvs'][x:x+2]) for x in range(0, len(mesh['uvs']), 2)]

        # TODO hasUVS2

        # Add Faces to the dictionary
        faces = []
        # face = [(loc_idx), (norm_idx), (uv_idx)]
        v_total = len(mesh_data['verts_loc']) #consistent with verts_nor and verts_uvs
        v_indices = [a for a in range(0, v_total)]
        faces_indices = [tuple(v_indices[x:x+3]) for x in range(0, v_total, 3)]

        for idx, data in enumerate(faces_indices):
            face = [data] * 2
            if has_uvs:
                face.append(data)
            else:
                face.append(())
            faces.append(face)
        mesh_data['faces'] = faces
        return mesh_data

    def clean_mesh(object):
        # Clean mesh / remove faces that don't span an area (...)
        # split
        # FIXME Handle double sided Faces

        select(object)
        O.object.mode_set(mode='EDIT')
        O.mesh.select_all(action='SELECT')
        O.mesh.remove_doubles(threshold=0.0001)
        O.mesh.tris_convert_to_quads(face_threshold=3.14159, shape_threshold=3.14159)
        O.object.mode_set(mode='OBJECT')

    def create_mesh(data):
        """
        Takes all the data gathered and generates a mesh, deals with custom normals and applies materials.
        Args:
            data ('dict') - The mesh data, vertices, normals, coordinates and materials.
        """
        # FIXME take rotDeg and position of MESH into account (?)
        verts_loc = data['verts_loc']
        verts_nor = data['verts_nor']
        verts_uvs = []

        if 'verts_uvs' in data:
            verts_uvs = data['verts_uvs']

        faces = data['faces']

        total_loops = len(faces)*3

        loops_vert_idx = []
        faces_loop_start = []
        faces_loop_total = [] # we can assume that, since all faces are trigons
        l_idx = 0 #loop index = ?? count for assigning loop start index to face

        # FIXME Document properly in the wiki and maybe also for external publishing
        for f in faces:
            v_idx = f[0] # The vertex indices of this face [a, b , c]
            nbr_vidx = len(v_idx) # Vertices count per face (Always 3 (all faces are trigons))

            loops_vert_idx.extend(v_idx) # Append all vert idx to loops vert idx
            faces_loop_start.append(l_idx)

            faces_loop_total.append(nbr_vidx) #(list of [3, 3, 3] vertex idc count per face)
            l_idx += nbr_vidx # Add the count to the total count to get the loop_start for the next face


        # Create a new mesh
        me = bpy.data.meshes.new(data['name'])
        # Add new empty vertices and polygons to the mesh
        me.vertices.add(len(verts_loc))
        me.loops.add(total_loops)
        me.polygons.add(len(faces))

        # Note unpack_list creates a flat array
        me.vertices.foreach_set('co', unpack_list(verts_loc))
        me.loops.foreach_set('vertex_index', loops_vert_idx)
        me.polygons.foreach_set('loop_start', faces_loop_start)
        me.polygons.foreach_set('loop_total', faces_loop_total)

        #Empty split vertex normals
        #Research: uvs not correct if split normals are set below blen_layer
        # Note: we store 'temp' normals in loops, since validate() may alter final mesh,
        #       we can only set custom loop_nors *after* calling it.
        me.create_normals_split()
        # FIXME multiple uv channel support?:
        if verts_uvs:
            # Research: difference between uv_layers and uv_textures
            me.uv_textures.new(name='UVMap')
            blen_uvs = me.uv_layers['UVMap']

        # Loop trough tuples of corresponding face / polygon
        for i, (face, blen_poly) in enumerate(zip(faces, me.polygons)):
            (face_vert_loc_indices,
             face_vert_nor_indices,
             face_vert_uvs_indices) = face

            for face_nor_idx, loop_idx in zip(face_vert_nor_indices, blen_poly.loop_indices):
                # FIXME Understand ... ellipsis (verts_nor[0 if (face_noidx is ...) else face_noidx])
                me.loops[loop_idx].normal[:] = verts_nor[face_nor_idx]

            if verts_uvs:
                for face_uvs_idx, loop_idx in zip(face_vert_uvs_indices, blen_poly.loop_indices):
                    blen_uvs.data[loop_idx].uv = verts_uvs[face_uvs_idx]

        me.validate(clean_customdata=False)
        me.update()

        # if normals
        cl_nors = array.array('f', [0.0] * (len(me.loops) * 3)) #Custom loop normals
        me.loops.foreach_get('normal', cl_nors)

        nor_split_set = tuple(zip(*(iter(cl_nors),) * 3))
        me.normals_split_custom_set(nor_split_set) # float array of 3 items in [-1, 1]
        # FIXME check if these steps are necessary and what they actually do
        # Set use_smooth -> actually this automatically calculates the median between two custom normals (if connected)
        # This feature could be nice if they share the
        # me.polygons.foreach_set('use_smooth', [True] * len(me.polygons))
        me.use_auto_smooth = True
        return me

    def join_objects(group):
        """ Joins all objects of the group
            Args:
                group ('bpy_prop_collection') - Objects to be joined.
            Returns:
                joined_object ('bpy_types.Object'): The joined object.
        """
        joined_object = None

        # If there are objects in the object group, join them
        if len(group) > 0:
            select(group, discard_selection=True)

            # Join them into the first object return the resulting object
            C.scene.objects.active = group[0]
            O.object.mode_set(mode='OBJECT')
            joined_object = group[0]

            if O.object:
                O.object.join()
        else:
            log.info('No objects to join.')

        return joined_object

    def select(objects, discard_selection=True):
        """ Select all objects in this group.
            Args:
                objects ('bpy_types.Object', 'bpy_prop_collection') - Object(s) to be selected
            Kwargs:
                discard_selection ('bool') - Discard original selection (Default=True)
        """
        group = []
        if hasattr(objects, '__iter__'):
            group = objects
        else:
            group.append(objects)

        if discard_selection:
            deselect(D.objects)

        for obj in group:
            obj.select = True
            C.scene.objects.active = obj

    def deselect(objects):
        """ Deselect all objects in this group.
            Args:
                objects ('bpy_types.Object', 'bpy_prop_collection') - Object(s) to be selected.
        """
        group = []
        if hasattr(objects, '__iter__'):
            group = objects
        else:
            group.append(objects)

        for obj in group:
            obj.select = False

    t0 = time.perf_counter()
    bl_materials = {}

    try:
        # FIXME rename
        data3d_object_data = get_nodes_recursive(data3d)
        # Add root level data to data3d object data
        data3d_object_data.append(get_node_data(data3d))

        # Parse Data3d information (Future-> hierarchy, children (...))
        for object_data in data3d_object_data:

            # Import mesh-materials
            if import_materials:
                bl_materials = import_data3d_materials(object_data, filepath)
                log.debug('Imported materials: %s', len(bl_materials))

        t1 = time.perf_counter()
        log.info('Time: Material Import %s', t1 - t0)

        for object_data in data3d_object_data:
            # TOP-level Objects
            # Import meshes as bl_objects
            # FIXME rename mesh, mesh_data ... to clarify origin (json or blender)
            meshes = object_data['meshes']
            bl_meshes = []
            for key in meshes.keys():
                mesh_data = get_mesh_data(meshes[key], key)
                bl_mesh = create_mesh(mesh_data)
                # Create new object and link it to the scene
                # FIXME Fallback if mesh creation fails? (for now we want all the errors
                ob = D.objects.new(mesh_data['name'], bl_mesh)
                if import_materials:
                    if mesh_data['material'] in bl_materials:
                        ob.data.materials.append(bl_materials[mesh_data['material']])
                    else:
                        log.error('Material not found: %s', mesh_data['material'])
                # TODO Add meshes position & rotation
                C.scene.objects.link(ob)
                clean_mesh(ob)
                bl_meshes.append(ob)

            # FIXME workaround joining all objects instead of joining generated mesh
            joined_object = join_objects(bl_meshes)
            if joined_object:
                joined_object.name = object_data['nodeId']
                object_data['bl_object'] = joined_object
            else:
                ob = D.objects.new(object_data['nodeId'], None)
                C.scene.objects.link(ob)
                object_data['bl_object'] = ob

            object_data['bl_object'].location = object_data['position']
            object_data['bl_object'].rotation_euler = object_data['rotation']

        # Make Parents
        # FIXME make dictionary for now
        id_data_pair = {data['nodeId']: data for data in data3d_object_data}

        for key in id_data_pair:
            data = id_data_pair[key]
            parent_id = data['parentId']
            if parent_id is not 'root':
                bl_object = data['bl_object']
                parent_object = id_data_pair[parent_id]['bl_object']
                bl_object.parent = parent_object

        # FIXME Global Matrix
        # parent - object.matrix_world = global_matrix

        #


        t2 = time.perf_counter()
        log.info('Time: Mesh Import %s', t2 - t1)


    except:
        #FIXME clean scene from created data-blocks
        raise Exception('Import Scene failed. ', sys.exc_info())


########
# Main #
########


def load(operator, context,filepath='', import_materials=True, global_matrix=None):
    """ Called by the user interface or another script.
        (...)
    """
    t0 = time.perf_counter()

    if global_matrix is None:
        global_matrix = mathutils.Matrix()
    #try:
    # Import the file - Json dictionary
    data3d_json = read_file(filepath=filepath)
    data3d = data3d_json['data3d']
    meta = data3d_json['meta']

    t1 = time.perf_counter()
    log.info('Time: JSON parser %s', t1 - t0)

    import_scene(data3d, global_matrix, filepath, import_materials)

    C.scene.update()

    t2 = time.perf_counter()

    log.info('Data3d import succesful, %s seconds', t2 -t0)

    return {'FINISHED'}

    # except:
    #     print('Data3d import failed: ', sys.exc_info())
    #     return {'CANCELLED'}
