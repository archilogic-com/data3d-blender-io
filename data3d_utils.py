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


# Temp debugging
def _dump_json_to_file(j, output_path):
    with open(output_path, 'w', encoding='utf-8') as file:
        file.write(json.dumps(j))


# Helper
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
    meta = data3d_json['meta']

    del data3d_json

    return data3d, meta


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