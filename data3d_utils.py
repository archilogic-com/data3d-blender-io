import sys
import os.path
import struct
import binascii
import json
import re

import logging

__all__ = ['deserialize_data3d', 'serialize_data3d']

HEADER_BYTE_LENGTH = 16
MAGIC_NUMBER = 0x41443344 # AD3D encoded as ASCII characters in hex (Actual: b'44334441')
VERSION = 1

ESCAPE_ASCII = re.compile(r'([\\"]|[^\ -~])')
ESCAPE_DCT = {
    '\\': '\\\\',
    '"': '\\"',
    '\b': '\\b',
    '\f': '\\f',
    '\n': '\\n',
    '\r': '\\r',
    '\t': '\\t',
}

logging.basicConfig(level='DEBUG', format='%(asctime)s %(levelname)-10s %(message)s', stream=sys.stdout)
log = logging.getLogger('archilogic')


# Relevant Data3d keys
class D3D:
    # Root
    r_meta = 'meta'
    r_container = 'data3d'

    # Hierarchy
    node_id = 'nodeId'
    o_position = 'position'
    o_rotation = 'rotDeg'
    o_meshes = 'meshes'
    o_mesh_keys = 'meshKeys'
    o_materials = 'materials'
    o_material_keys = 'materialKeys'
    o_children = 'children'

    # Geometry
    m_position = 'position'
    m_rotation = 'rotDeg'
    m_material = 'material'
    v_coords = 'positions'
    v_normals = 'normals'
    uv_coords = 'uvs'
    uv2_coords = 'uvsLightmap'

    # Material
    col_diff = 'colorDiffuse'
    col_spec = 'colorSpecular'
    coef_spec = 'specularCoef'
    coef_emit = 'lightEmissionCoef'
    opacity = 'opacity'
    uv_scale = 'size' # UV1 map size in meters
    # tex_wrap = 'wrap'
    map_diff = 'mapDiffuse'
    map_spec = 'mapSpecular'
    map_norm = 'mapNormal'
    map_alpha = 'mapAlpha'
    map_light = 'mapLight'
    map_suffix_source = 'Source'
    map_suffix_preview = 'Preview'
    cast_shadows = 'castRealTimeShadows'
    receive_shadows = 'receiveRealTimeShadows'
    # Baking related material keys
    add_lightmap = 'addLightmap'
    use_in_calc = 'useInBaking'
    hide_after_calc = 'hideAfterBaking'

    # Buffer
    b_coords_offset = 'positionsOffset'
    b_coords_length = 'positionsLength'
    b_normals_offset = 'normalsOffset'
    b_normals_length = 'normalsLength'
    b_uvs_offset = 'uvsOffset'
    b_uvs_length = 'uvsLength'
    b_uvs2_offset = 'uvsLightmapOffset'
    b_uvs2_length = 'uvsLightmapOffset'
    ...


class Data3dObject(object):
    """
        Global Attributes:
            # Fixme file-buffer
        Attributes:
            node_id ('str') - The nodeId of the object.
            node_id ('str') - The nodeId of the parent object, 'root' if it is root-level object.
            meshes ('list(dict)') - The object meshes as raw json data.
            materials ('list(dict)') - The object materials as raw json data.
            position ('list(int)') - The relative position of the object.
            rotation ('list(int)') - The relative rotation of the object.
            mat_hash_map ('dict') - The HashMap of the object material keys -> blender materials.
            bl_object ('bpy.types.Object') - The blender object for this data3d object
    """

    def __init__(self, node, root=None, parent=None):

        self.node_id = node[D3D.node_id] if D3D.node_id in node else ''
        self.parent_id = root[D3D.node_id] if root and D3D.node_id in root else 'root'
        self.parent = parent

        self.meshes = []
        self.materials = node[D3D.o_materials] if D3D.o_materials in node else ''
        self.position = node[D3D.o_position] if D3D.o_position in node else ''
        self.rotation = node[D3D.o_rotation] if D3D.o_rotation in node else ''

        self.bl_object = None
        self.mat_hash_map = {}

        mesh_references = node[D3D.o_meshes] if D3D.o_meshes in node else ''
        for mesh_key in mesh_references:
            self._get_data3d_mesh_nodes(mesh_references[mesh_key], mesh_key)


    def _get_data3d_mesh_nodes(self, mesh, name):
        """ Return all the relevant nodes of this mesh. Create face data for the mesh import.
        """
        mesh_data = {
            'name': name,
            'material': mesh[D3D.m_material],
            # Vertex location, normal and uv coordinates, referenced by indices
            'verts_loc': [tuple(mesh[D3D.v_coords][x:x+3]) for x in range(0, len(mesh[D3D.v_coords]), 3)],
            'verts_nor': [tuple(mesh[D3D.v_normals][x:x+3]) for x in range(0, len(mesh[D3D.v_normals]), 3)],
            'position': mesh[D3D.m_position] if D3D.m_position in mesh else [0, 0, 0],
            'rotation': mesh[D3D.m_rotation] if D3D.m_rotation in mesh else [0, 0, 0]
        }

        has_uvs = D3D.uv_coords in mesh
        has_uvs2 = D3D.uv2_coords in mesh

        if has_uvs:
            mesh_data['verts_uvs'] = [tuple(mesh[D3D.uv_coords][x:x+2]) for x in range(0, len(mesh[D3D.uv_coords]), 2)]
        if has_uvs2:
            mesh_data['verts_uvs2'] = [tuple(mesh[D3D.uv2_coords][x:x+2]) for x in range(0, len(mesh[D3D.uv2_coords]), 2)]

        # Fixme: Handle double sided faces
        faces = []                                      # face = [(loc_idx), (norm_idx), (uv_idx), (uv2_idx)]
        v_total = len(mesh_data['verts_loc'])           # Consistent with len(verts_nor) and len(verts_uvs)
        v_indices = [x for x in range(0, v_total)]
        face_indices = [tuple(v_indices[x:x+3]) for x in range(0, v_total, 3)] # [ (0, 1, 2), (3, 4, 5), ... ]

        for idx, data in enumerate(face_indices):
            face = [data] * 2                           # Add (loc_idx), (norm_idx) to the face list

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

        self.meshes.append(mesh_data)

    def set_bl_object(self, bl_object):
        self.bl_object = bl_object

# Temp debugging
def _dump_json_to_file(j, output_path):
    with open(output_path, 'w', encoding='utf-8') as file:
        file.write(json.dumps(j))


# Helper
def _get_data3d_objects_recursive(root, parent=None):
    """ Go trough the json hierarchy recursively and get all the children.
    """
    recursive_data = []
    children = root[D3D.o_children] if D3D.o_children in root else []
    if children is not []:
        for child in children:
            data3d_object = Data3dObject(child, root, parent)
            recursive_data.append(data3d_object)
            recursive_data.extend(_get_data3d_objects_recursive(child, data3d_object))
    return recursive_data



def _py_encode_basestring_ascii(s):
    """ Return an ASCII-only JSON representation of a Python string
        Args:
            s ('str') - The string to encode.
        Returns:
            _ ('str') - The encoded string.
    """
    def replace(match):
        s = match.group(0)
        try:
            return ESCAPE_DCT[s]
        except KeyError:
            n = ord(s)
            if n < 0x10000:
                return '\\u{0:04x}'.format(n)
                #return '\\u%04x' % (n,)
            else:
                # surrogate pair
                n -= 0x10000
                s1 = 0xd800 | ((n >> 10) & 0x3ff)
                s2 = 0xdc00 | (n & 0x3ff)
                return '\\u{0:04x}\\u{1:04x}'.format(s1, s2)

    return '"' + ESCAPE_ASCII.sub(replace, s) + '"'


def _to_json(o, level=0):
    """ Parse python elements into json strings recursively.
        Args:
            o ('any') - The python (sub)element to parse.
            level (int) - The current indent level.
        Returns:
            ret ('str') - The parsed json string.
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
        ret += py_encode_basestring_ascii(o)
    elif isinstance(o, bool):
        ret += 'true' if o else 'false'
    elif isinstance(o, int):
        ret += str(o)
    elif isinstance(o, float):
        if str(o).find('e') != -1:
            ret += '{:.5f}'.format(o)
        else:
            ret += '%.5g' % o
    #elif isinstance(o, numpy.ndarray) ...:
    else:
        raise TypeError("Unknown type '%s' for json serialization" % str(type(o)))

    return ret


def _from_data3d_json(input_path):

    def read_file_to_json(filepath=''):
        if os.path.exists(filepath):
            data3d_file = open(filepath, mode='r')
            json_str = data3d_file.read()
            return json.loads(json_str)
        else:
            raise Exception('File does not exist, ' + filepath)

    data3d_json = read_file_to_json(filepath=input_path)
    data3d = data3d_json['data3d']
    # Import JSON Data3d Objects and add root level object
    data3d_objects = _get_data3d_objects_recursive(data3d)
    data3d_objects.append(Data3dObject(data3d))

    meta = data3d_json['meta']

    del data3d_json

    return data3d_objects, meta


def _from_data3d_buffer(data3d_buffer):

    def read_into_buffer(file):
        buf = bytearray(os.path.getsize(file))
        with open(file, 'rb') as f:
            f.readinto(buf)
        return buf

    def get_header(buffer_file):
        header_array = [buffer_file[x:x+4] for x in range(0, HEADER_BYTE_LENGTH, 4)]
        header = [binascii.hexlify(header_array[0]),
                  binary_unpack('i', header_array[1]),
                  binary_unpack('i', header_array[2]),
                  binary_unpack('i', header_array[3])
                  ]
        return header

    def binary_unpack(t, b):
        return struct.unpack(t, b)[0]

    file_buffer = read_into_buffer(data3d_buffer)

    # Fixme Magic number in the downloaded data3d files does not correspond -> b'44334441' -> 'D3DA' instead of 'A3D3'
    log.info(file_buffer[0:4])

    magic_number, version, structure_byte_length, payload_byte_length = get_header(file_buffer)
    expected_file_byte_length = HEADER_BYTE_LENGTH + structure_byte_length + payload_byte_length

    # Fixme why only != gives accurate result instead of is/is not

    # Validation warnings
    if magic_number != MAGIC_NUMBER:
        log.error('File header error: Wrong magic number. File is probably not data3d buffer format. %s', magic_number)
    if version != VERSION:
        log.error('File header error: Wrong version number: %s. Parser supports version: %s', version, VERSION)

    # Validation errors
    if len(file_buffer) != expected_file_byte_length:
        raise Exception('Can not parse data3d buffer. Wrong buffer size: ' + str(len(file_buffer)) + ' Expected: ' + str(expected_file_byte_length))

    # Parse structure info
    payload_byte_offset = HEADER_BYTE_LENGTH + structure_byte_length
    structure_array = file_buffer[HEADER_BYTE_LENGTH:payload_byte_offset]
    structure_string = structure_array.decode("utf-16")
    structure_json = json.loads(structure_string)

    # Temp
    _dump_json_to_file(structure_json, 'C:/Users/madlaina-kalunder/Desktop/dump')

    payload_array = file_buffer[payload_byte_offset:len(file_buffer)]

    del file_buffer
    # Fixme buffer format has no nodeIds
    return structure_json['data3d'], structure_json['meta']

def _to_data3d_json(data3d, output_path):
    with open(output_path, 'w', encoding='utf-8') as file:
            file.write(_to_json(data3d))


def _to_data3d_buffer(data3d):
    # Header
    # structure_byte_array
    # payoad_byte_array
    # put everything together as byte array
    ...


# Public functions
def deserialize_data3d(input_path, from_buffer):
    if from_buffer:
        return _from_data3d_buffer(input_path)
    else:
        return _from_data3d_json(input_path)


def serialize_data3d(data3d, output_path, to_buffer):
    if to_buffer:
        _to_data3d_buffer(data3d, output_path)
    else:
        _to_data3d_json(data3d, output_path)