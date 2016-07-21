import sys
import os.path
import logging

import struct
import binascii
import json
import re

import string
import random
import copy

__all__ = ['deserialize_data3d', 'serialize_data3d']

HEADER_BYTE_LENGTH = 16
MAGIC_NUMBER = '41443344' #AD3D encoded as ASCII characters in hex (Actual: b'44334441')
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

# Temp
dump_file = 'C:/Users/madlaina-kalunder/Desktop/dump'

# Relevant Data3d keys
class D3D:
    # Root
    r_meta = 'meta'
    r_container = 'data3d'

    # Hierarchy
    node_id = 'nodeId'
    o_position = 'position'
    o_rotation = 'rotRad'
    o_meshes = 'meshes'
    o_mesh_keys = 'meshKeys'
    o_materials = 'materials'
    o_material_keys = 'materialKeys'
    o_children = 'children'

    # Geometry
    m_position = 'position'
    m_rotation = 'rotRad'
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
            node_id ('str') - The nodeId of the object or a generated Id.
            parent ('Data3dObject')
            meshes ('list(dict)') - The object meshes as raw json data.
            materials ('list(dict)') - The object materials as raw json data.
            position ('list(int)') - The relative position of the object.
            rotation ('list(int)') - The relative rotation of the object.
            mat_hash_map ('dict') - The HashMap of the object material keys -> blender materials.
            bl_object ('bpy.types.Object') - The blender object for this data3d object
    """
    file_buffer = None
    payload_byte_offset = 0

    def __init__(self, node, parent=None):

        self.node_id = node[D3D.node_id] if D3D.node_id in node else _id_generator(12)
        self.parent = None
        self.children = []

        self.meshes = []
        self.materials = node[D3D.o_materials] if D3D.o_materials in node else []
        self.position = node[D3D.o_position] if D3D.o_position in node else [0, 0, 0]
        self.rotation = node[D3D.o_rotation] if D3D.o_rotation in node else [0, 0, 0]

        self.bl_object = None
        self.mat_hash_map = {}

        mesh_references = node[D3D.o_meshes] if D3D.o_meshes in node else ''
        for mesh_key in mesh_references:
            self._get_data3d_mesh_nodes(mesh_references[mesh_key], mesh_key)
        if parent:
            self.parent = parent
            parent.add_child(self)

    def _get_data3d_mesh_nodes(self, mesh, name):
        """ Return all the relevant nodes of this mesh. Create face data for the mesh import.
        """
        mesh_data = {
            'name': name,
            'material': mesh[D3D.m_material],
            'position': mesh[D3D.m_position] if D3D.m_position in mesh else [0, 0, 0],
            'rotation': mesh[D3D.m_rotation] if D3D.m_rotation in mesh else [0, 0, 0]
        }

        has_uvs = D3D.uv_coords in mesh or D3D.b_uvs_offset in mesh
        has_uvs2 = D3D.uv2_coords in mesh or D3D.b_uvs2_offset in mesh

        if Data3dObject.file_buffer:
            unpacked_coords = self._get_data_from_buffer(mesh[D3D.b_coords_offset], mesh[D3D.b_coords_length])
            mesh_data['verts_loc'] = [tuple(unpacked_coords[x:x+3]) for x in range(0, len(unpacked_coords), 3)]

            unpacked_normals = self._get_data_from_buffer(mesh[D3D.b_normals_offset], mesh[D3D.b_normals_offset])
            mesh_data['verts_nor'] = [tuple(unpacked_normals[x:x+3]) for x in range(0, len(unpacked_normals), 3)]

            if has_uvs:
                unpacked_uvs = self._get_data_from_buffer(mesh[D3D.b_uvs_offset], mesh[D3D.b_uvs_length])
                mesh_data['verts_uvs'] = [tuple(unpacked_uvs[x:x+2]) for x in range(0, len(unpacked_uvs), 2)]

            if has_uvs2:
                unpacked_uvs2 = self._get_data_from_buffer(mesh[D3D.b_uvs2_offset], mesh[D3D.b_uvs2_length])
                mesh_data['verts_uvs2'] = [tuple(unpacked_uvs2[x:x+2]) for x in range(0, len(unpacked_uvs2), 2)]

        else:
            # Vertex location, normal and uv coordinates, referenced by indices
            mesh_data['verts_loc'] = [tuple(mesh[D3D.v_coords][x:x+3]) for x in range(0, len(mesh[D3D.v_coords]), 3)]
            mesh_data['verts_nor'] = [tuple(mesh[D3D.v_normals][x:x+3]) for x in range(0, len(mesh[D3D.v_normals]), 3)]

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

    def _get_data_from_buffer(self, offset, length):
        start = Data3dObject.payload_byte_offset + (offset * 4)
        end = start + (length * 4)
        data = []
        binary_data = Data3dObject.file_buffer[start:end]
        for x in range(0, len(binary_data), 4):
            data.append(binary_unpack('f', binary_data[x:x+4]))
        return data

    def set_bl_object(self, bl_object):
        self.bl_object = bl_object

    def add_child(self, child):
        self.children.append(child)


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
            data3d_object = Data3dObject(child, parent)
            recursive_data.append(data3d_object)
            recursive_data.extend(_get_data3d_objects_recursive(child, data3d_object))
    return recursive_data


def _id_generator(size=6, chars=string.ascii_uppercase + string.digits):
    return ''.join(random.choice(chars) for _ in range(size))


def binary_unpack(t, b):
    return struct.unpack(t, b)[0]


def binary_pack(t, a):
    return struct.pack(t*len(a), *a)


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
            ret += _to_json(v, level+1)
        ret += json_newline + json_space * json_indent * level + '}'
    elif isinstance(o, list):
        ret += '[' + ','.join([_to_json(e, level + 1) for e in o]) + ']'
    elif isinstance(o, str):
        ret += _py_encode_basestring_ascii(o)
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

    # Import JSON Data3d Objects and add root level object
    root_object = Data3dObject(data3d_json['data3d'])
    data3d_objects = _get_data3d_objects_recursive(data3d_json['data3d'], root_object)
    data3d_objects.append(root_object)
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

    file_buffer = read_into_buffer(data3d_buffer)

    # Fixme Magic number in the downloaded data3d files does not correspond -> b'44334441' -> 'D3DA' instead of 'A3D3'

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
    _dump_json_to_file(structure_json, dump_file)

    #payload_array = file_buffer[payload_byte_offset:len(file_buffer)]
    Data3dObject.file_buffer = file_buffer #payload_array
    Data3dObject.payload_byte_offset = payload_byte_offset

    #  Import JSON Data3d Objects and add root level object
    root_object = Data3dObject(structure_json['data3d'])
    data3d_objects = _get_data3d_objects_recursive(structure_json['data3d'], root_object)
    data3d_objects.append(root_object)
    #del file_buffer
    return data3d_objects, structure_json['meta']


def _to_data3d_json(data3d, output_path):
    with open(output_path, 'w', encoding='utf-8') as file:
            file.write(_to_json(data3d))


def _to_data3d_buffer(data3d, output_path):

    def create_header(structure_byte_length, payload_byte_length):
        return binascii.unhexlify(MAGIC_NUMBER) + binary_pack('i', [VERSION, structure_byte_length, payload_byte_length])

    def extract_buffer_data(d):
        s = copy.deepcopy(d)
        p = []

        root = s[D3D.r_container]
        # Flattened Data3d dictionary with no hierarchy
        if D3D.o_meshes in root:
            meshes = root[D3D.o_meshes]
            for mesh_key in meshes:
                mesh = meshes[mesh_key]
                log.info(mesh)
                v_loc = mesh.pop(D3D.v_coords, None)
                v_norm = mesh.pop(D3D.v_normals, None)
                v_uvs = mesh.pop(D3D.uv_coords, None)
                v_uvs2 = mesh.pop(D3D.uv2_coords, None)

                mesh[D3D.b_coords_length] = len(v_loc)
                mesh[D3D.b_coords_offset] = len(p)
                p.extend(v_loc)

                mesh[D3D.b_normals_length] = len(v_norm)
                mesh[D3D.b_normals_offset] = len(p)
                p.extend(v_norm)

                if v_uvs:
                    mesh[D3D.b_uvs_length] = len(v_uvs)
                    mesh[D3D.b_uvs_offset] = len(p)
                    p.extend(v_uvs)

                if v_uvs2:
                    mesh[D3D.b_uvs2_length] = len(v_uvs2)
                    mesh[D3D.b_uvs2_offset] = len(p)
                    p.extend(v_uvs2)

            # alter mesh dict
            # append the data
            # FIXME go trough all children

        return s, p

    structure, payload = extract_buffer_data(data3d)
    structure_json = json.dumps(structure, indent=None, skipkeys=False)
    structure['version'] = VERSION

    if not len(structure_json) % 2:
        structure_json += ' '

    log.info(_to_json(structure))
    #_dump_json_to_file(structure, dump_file)

    structure_byte_array = bytearray(structure_json, 'utf-16')
    structure_byte_length = len(structure_byte_array)
    payload_byte_array = binary_pack('f', payload)
    payload_byte_length = len(payload_byte_array)

    header = create_header(structure_byte_length, payload_byte_length)
    log.info('Header Number: %s, version %s, structure %s, payload %s, \n bytes: %s',
             MAGIC_NUMBER, VERSION, structure_byte_length, payload_byte_length, header)
    # Warnings

    # Errors
    if len(header) != HEADER_BYTE_LENGTH:
        raise Exception('Can not serialize data3d buffer. Wrong header size: ' + str(len(header)) + ' Expected: ' + str(len(HEADER_BYTE_LENGTH)))
    # FIXME if buffer_file length != expected length

    with open(output_path, 'wb') as buffer_file:
        buffer_file.write(header)
        buffer_file.write(structure_byte_array)
        buffer_file.write(payload_byte_array)


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