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
from bpy_extras.io_utils import unpack_list

from . import material_utils
from . import D3D


# Global Variables
C = bpy.context
D = bpy.data
O = bpy.ops

#FIXME Logging & Timestamps
logging.basicConfig(level='DEBUG', format='%(asctime)s %(levelname)-10s %(message)s')
log = logging.getLogger('archilogic')

def read_file(filepath=''):
    if os.path.exists(filepath):
        data3d_file = open(filepath, mode='r')
        json_str = data3d_file.read()
        return json.loads(json_str)
    else:
        raise Exception('File does not exist, ' + filepath)


def import_data3d_materials(data3d_objects, filepath, import_metadata):
    """ Import the material references and create blender and cycles materials.

    """

    def get_al_material_hash(al_material):
        compare_keys = [D3D.col_diff,
                        D3D.col_spec,
                        D3D.coef_spec,
                        D3D.opacity,
                        # Fixme
                        D3D.map_diff, D3D.map_diff + D3D.map_suffix_source, D3D.map_diff + D3D.map_suffix_preview,
                        D3D.map_spec, D3D.map_spec + D3D.map_suffix_source, D3D.map_spec + D3D.map_suffix_preview,
                        D3D.map_norm, D3D.map_norm + D3D.map_suffix_source, D3D.map_norm + D3D.map_suffix_preview,
                        D3D.map_alpha, D3D.map_alpha + D3D.map_suffix_source, D3D.map_alpha + D3D.map_suffix_preview,
                        D3D.map_light, D3D.map_light + D3D.map_suffix_source, D3D.map_light + D3D.map_suffix_preview,
                        D3D.cast_shadows,
                        D3D.receive_shadows] #'colorAmbient'
        # FIXME solution for Baking related material info (we only need this for internal purposes
        hash_nodes = {}
        for key in compare_keys:
            if key in al_material:
                value = al_material[key]
                hash_nodes[key] = tuple(value) if isinstance(value, list) else value
        al_mat_hash = hash(frozenset(hash_nodes.items()))
        return al_mat_hash, hash_nodes

    material_utils.setup()

    # TODO Flatten Material duplicates for faster import

    # HOW TO IMPLEMENT: Modify data3d dictionary -> somehow map bl_materials to al_material_keys
    al_hashed_materials = {}
    for data3d_object in data3d_objects:
        al_raw_materials = data3d_object['materials']
        for key in al_raw_materials:
            # create unique key name
            al_mat_hash, al_mat = get_al_material_hash(al_raw_materials[key])
            # Check if the material already exists
            if al_mat_hash in al_hashed_materials:
                log.info('Material duplicate found. %s ', al_mat_hash)
            else:
                al_hashed_materials[al_mat_hash] = al_mat
                log.info('Material added to hashed materials %s', al_mat_hash)

    log.debug(al_hashed_materials)

    working_dir = os.path.dirname(filepath)
    bl_materials = []
    for key in al_hashed_materials:
        bl_materials.append(material_utils.import_material(str(key), al_hashed_materials[key], import_metadata, working_dir))

    return bl_materials


def import_scene(data3d, **kwargs):
    """ Import the data3d file as a blender scene
        Args:
            data3d ('dict') - The parsed data3d json file
        Kwargs:
            filepath ('str') - The file path to the data3d source file.
            import_materials ('bool') - Import materials.
            import_materials ('bool') - Import and apply materials.
            import_hierarchy ('bool') - Import and keep the parent-child hierarchy.
            import_al_metadata ('bool') - Import the Archilogic data as metadata.
            global_matrix ('Matrix') - The global orientation matrix to apply.
    """

    filepath = kwargs['filepath']
    import_materials = kwargs['import_materials']
    import_hierarchy = kwargs['import_hierarchy']
    global_matrix = kwargs['global_matrix']

    def get_objects_recursive(root):
        recursive_data = []
        # Support non-flattened arrays (remove eventually)
        children = root['children'] if 'children' in root else []
        if children is not []:
            for child in children:
                data = get_object_nodes(child, root)
                recursive_data.append(data)
                recursive_data.extend(get_objects_recursive(child))
        return recursive_data

    def get_object_nodes(node, root=None):
        # TODO Rename (OBJECT node data)
        data = {
                    'nodeId': node['nodeId'],
                    'parentId': root['nodeId'] if root else 'root',
                    'meshes': node['meshes'] if 'meshes' in node else [], # FIXME falback to dic not list
                    'materials': node['materials'] if 'materials' in node else [],
                    'position': node['position'] if 'position' in node else [0, 0, 0],
                    'rotation': node['rotRad'] if 'rotRad' in node else [0, 0, 0],
                }
        return data

    def get_mesh_nodes(mesh, name):
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

        # TODO lightmap import to uv2
        has_uvs2 = ('uvsLightmap' in mesh)
        if has_uvs2:
            mesh_data['verts_uvs2'] = [tuple(mesh['uvsLightmap'][x:x+2]) for x in range(0, len(mesh['uvsLightmap']), 2)]

        # Add Faces to the dictionary
        faces = []
        # face = [(loc_idx), (norm_idx), (uv_idx), (uv2_idx)]
        v_total = len(mesh_data['verts_loc']) #consistent with verts_nor and verts_uvs
        v_indices = [a for a in range(0, v_total)]
        faces_indices = [tuple(v_indices[x:x+3]) for x in range(0, v_total, 3)]

        # Face: [loc_indices, normal_indices, uvs_indices, uv2_indices]
        for idx, data in enumerate(faces_indices):
            face = [data] * 2
            if has_uvs:
                face.append(data)
            else:
                face.append(())
            if has_uvs2:
                face.append(data)
            else:
                face.append(())
            faces.append(face)

        mesh_data['faces'] = faces
        return mesh_data

    def clean_mesh(object):
        # Clean mesh /
        # TODO remove faces that don't span an area (...)
        # FIXME Handle double sided Faces
        # TODO Make tris to quads hidden option for operator (internal use)

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
            data ('dict') - The json mesh data: vertices, normals, coordinates and materials.
        """
        # FIXME Renaming for readability and clarity
        # FIXME take rotDeg and position of MESH into account (?)
        verts_loc = data['verts_loc']
        verts_nor = data['verts_nor']
        verts_uvs = data['verts_uvs'] if 'verts_uvs' in data else []
        verts_uvs2 = data['verts_uvs2'] if 'verts_uvs2' in data else []

        faces = data['faces']

        total_loops = len(faces)*3

        loops_vert_idx = []
        faces_loop_start = []
        faces_loop_total = [] # we can assume that, since all faces are trigons
        l_idx = 0 #loop index = ?? count for assigning loop start index to face

        # FIXME Document properly in the wiki and maybe also for external publishing
        # FIXME simplify fixed values
        for f in faces:
            v_idx = f[0] # The vertex indices of this face [a, b , c]
            nbr_vidx = 3 # len(v_idx) Vertices count per face (Always 3 (all faces are trigons))

            loops_vert_idx.extend(v_idx) # Append all vert idx to loops vert idx
            faces_loop_start.append(l_idx)

            faces_loop_total.append(nbr_vidx) # (list of [3, 3, 3 ... ] vertex idc count per face)
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

        # Empty split vertex normals
        # Research: uvs not correct if split normals are set below blen_layer
        # Note: we store 'temp' normals in loops, since validate() may alter final mesh,
        #       we can only set custom loop_nors *after* calling it.
        me.create_normals_split()

        if verts_uvs:
            # FIXME: Research: difference between uv_layers and uv_textures (get layer directly?)
            me.uv_textures.new(name='UVMap')
            blen_uvs = me.uv_layers['UVMap']

        if verts_uvs2:
            me.uv_textures.new(name='UVLightmap')
            blen_uvs2 = me.uv_layers['UVLightmap']

        # FIXME validate before applying vertex normals

        # Loop trough tuples of corresponding face / polygon
        for i, (face, blen_poly) in enumerate(zip(faces, me.polygons)):
            (face_vert_loc_indices,
             face_vert_nor_indices,
             face_vert_uvs_indices,
             face_vert_uvs2_indices) = face

            for face_nor_idx, loop_idx in zip(face_vert_nor_indices, blen_poly.loop_indices):
                # FIXME Understand ... ellipsis (verts_nor[0 if (face_noidx is ...) else face_noidx])
                me.loops[loop_idx].normal[:] = verts_nor[face_nor_idx]

            if verts_uvs:
                for face_uvs_idx, loop_idx in zip(face_vert_uvs_indices, blen_poly.loop_indices):
                    blen_uvs.data[loop_idx].uv = verts_uvs[face_uvs_idx]
            if verts_uvs2:
                for face_uvs2_idx, loop_idx in zip(face_vert_uvs2_indices, blen_poly.loop_indices):
                    blen_uvs2.data[loop_idx].uv = verts_uvs2[face_uvs2_idx]

        me.validate(clean_customdata=False)
        me.update()

        # if normals
        cl_nors = array.array('f', [0.0] * (len(me.loops) * 3)) # Custom loop normals
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

        # If there are objects in the object group, join them
        if len(group) > 0:
            select(group, discard_selection=True)

            # Join them into the first object return the resulting object
            C.scene.objects.active = group[0]
            O.object.mode_set(mode='OBJECT')
            joined = group[0]

            if O.object:
                O.object.join()
            return joined

        else:
            log.debug('No objects to join.')
            return None

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
            O.object.select_all(action='DESELECT')

        for obj in group:
            obj.select = True
            C.scene.objects.active = obj

    def normalise_objects(objects, apply_location=False):
        """ Prepare object for baking/export, apply transform
            Args:
                obj ('bpy_types.Object', 'bpy_prop_collection') - Object(s) to be normalised.
            Kwargs:
                apply_location ('boolean') - Apply location of the object.
        """
        group = []

        if hasattr(objects, '__iter__'):
            for obj in objects:
                if obj is None and obj.type != 'MESH':
                    group.append(obj)
        else:
            group.append(objects)


        select(group, discard_selection=True)
        #O.object.mode_set(mode='OBJECT')
        O.object.transform_apply(location=apply_location, rotation=True, scale=True)

    t0 = time.perf_counter()
    bl_materials = {}

    try:
        # FIXME Documentation: data3d object
        # Import JSON Data3d Objects and add root level object
        data3d_objects = get_objects_recursive(data3d)
        data3d_objects.append(get_object_nodes(data3d))

        # Import mesh-materials
        if import_materials:
            bl_materials = import_data3d_materials(data3d_objects, filepath, kwargs['import_al_metadata'])
            log.debug('Imported materials.')

        t1 = time.perf_counter()
        log.info('Time: Material Import %s', t1 - t0)

        for data3d_object in data3d_objects:
            # TOP-level Objects
            # Import meshes as bl_objects
            # FIXME rename mesh, mesh_data ... to clarify origin (json or blender)
            al_meshes = data3d_object['meshes']
            bl_meshes = []
            for key in al_meshes.keys():
                al_mesh = get_mesh_nodes(al_meshes[key], key)
                # FIXME al_mesh material key
                bl_mesh = create_mesh(al_mesh)
                # Create new object
                ob = D.objects.new(al_mesh['name'], bl_mesh)

                # TODO fix material import
                # if import_materials:
                #    if al_mesh['material'] in bl_materials:
                #        ob.data.materials.append(bl_materials[al_mesh['material']])
                #    else:
                #        log.error('Material not found: %s', al_mesh['material'])

                # Link the object to the scene
                C.scene.objects.link(ob)
                # clean_mesh(ob) # FIXME for now
                bl_meshes.append(ob)

            # WORKAROUND: we are joining all objects instead of joining generated mesh (bmesh module would support this)
            if len(bl_meshes) > 0:
                joined_object = join_objects(bl_meshes)
                joined_object.name = data3d_object['nodeId']
                data3d_object['bl_object'] = joined_object
            else:
                ob = D.objects.new(data3d_object['nodeId'], None)
                C.scene.objects.link(ob)
                data3d_object['bl_object'] = ob

            # Relative rotation and position to the parent
            data3d_object['bl_object'].location = data3d_object['position']
            data3d_object['bl_object'].rotation_euler = data3d_object['rotation']

        # Make parent - children relationships
        # FIXME dictionary for now (nodeID -> object_data)
        id_object_pair = {o['nodeId']: o for o in data3d_objects}

        bl_root_obj = None
        for key in id_object_pair:
            data3d_object = id_object_pair[key]
            parent_id = data3d_object['parentId']
            if parent_id is not 'root':
                bl_object = data3d_object['bl_object']
                parent_object = id_object_pair[parent_id]['bl_object']
                bl_object.parent = parent_object
            else:
                bl_root_obj = data3d_object['bl_object']

        t2 = time.perf_counter()
        log.info('Time: Mesh Import %s', t2 - t1)

        bl_objects = [id_object_pair[key]['bl_object'] for key in id_object_pair]

        normalise_objects(bl_root_obj, apply_location=True)
        bl_root_obj.matrix_world = global_matrix

        if not import_hierarchy:
            # Clear the parent-child relationships, keep transform
            # FIXME operation is really slow. find option to do this via datablock (parent_clear /transform_apply)
            for bl_object in bl_objects:
                select(bl_object, discard_selection=False)
                O.object.parent_clear(type='CLEAR_KEEP_TRANSFORM')

            normalise_objects(bl_objects, apply_location=True)

            for bl_object in bl_objects:
                if bl_object.type == 'EMPTY':
                    C.scene.objects.unlink(bl_object)
                    D.objects.remove(bl_object)

         # FIXME Hierarchy cleanup is extremely costly. maybe we can keep the hierarchy for the bakes?
        t3 = time.perf_counter()
        log.info('Time: Hierarchy cleanup %s', t3 - t2)
    except:
        #FIXME clean scene from created data-blocks
        raise Exception('Import Scene failed. ', sys.exc_info())


########
# Main #
########


def load(operator,
         context,
         **args):
    """ Called by the user interface or another script.
        Args:
            operator (...)
            context (...)
        Kwargs:
            filepath ('str') - The filepath to the data3d source file.
            import_materials ('bool') - Import and apply materials.
            import_hierarchy ('bool') - Import and keep the parent-child hierarchy.
            import_al_metadata ('bool') - Import the Archilogic data as metadata.
            global_matrix ('Matrix') - The global orientation matrix to apply.
    """

    # FIXME Cleanup unused params
    log.info('Data3d import started, %s', args)
    t0 = time.perf_counter()

    if args['global_matrix']is None:
        args['global_matrix'] = mathutils.Matrix()

    # FIXME try-except
    # try:
    # Import the file - Json dictionary
    data3d_json = read_file(filepath=args['filepath'])
    data3d = data3d_json['data3d']
    # meta = data3d_json['meta']

    t1 = time.perf_counter()
    log.info('Time: JSON parser %s', t1 - t0)

    import_scene(data3d, **args)

    C.scene.update()

    t2 = time.perf_counter()

    log.info('Data3d import succesful, %s seconds', t2 - t0)

    return {'FINISHED'}

    # except:
    #     print('Data3d import failed: ', sys.exc_info())
    #     return {'CANCELLED'}
