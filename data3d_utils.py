import sys
import os.path
import struct
import binascii
import json

import logging

HEADER_BYTE_LENGTH = 16
MAGIC_NUMBER = 0x41443344 # AD3D encoded as ASCII characters in hex (Actual: b'44334441')
VERSION = 1

data3d_buffer_file = ''

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


# Temp
def dump_json_to_file(j, output_path):
    with open(output_path, 'w', encoding='utf-8') as file:
        file.write(json.dumps(j))


def from_data3d_buffer(data3d_buffer):
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
    dump_json_to_file(structure_json, 'C:/Users/madlaina-kalunder/Desktop/dump')

    payload_array = file_buffer[payload_byte_offset:len(file_buffer)]
    log.info(len(payload_array))

    del file_buffer


def deserialize_data3d(input_path, from_buffer=True):
    from_data3d_buffer(data3d_buffer_file)

def serialize_data3d(data3d, output_path, to_buffer=True):
    ...

deserialize_data3d(data3d_buffer_file, from_buffer=True)