import os.path
import struct
import binascii

HEADER_BYTE_LENGTH = 16
MAGIC_NUMBER = b'44334441' #0x41443344 # AD3D encoded as ASCII characters in hex
VERSION = 1

data3d_buffer_file = ''


def read_into_buffer(file):
    buf = bytearray(os.path.getsize(file))
    with open(file, 'rb') as f:
        f.readinto(buf)
    return buf


def get_header(buffer_file):
    header_array = [buffer_file[x:x+4] for x in range(0, HEADER_BYTE_LENGTH, 4)]
    header = [  binascii.hexlify(header_array[0]),
                binary_unpack('i', header_array[1]),
                binary_unpack('i', header_array[2]),
                binary_unpack('i', header_array[3]),
              ]
    print(header)
    return header
    # with open(buffer_file, 'rb') as fin:
    #     m = 4
    #     n = HEADER_BYTE_LENGTH
    #     header_array = [fin.read(4) for num in range(0, (m+1)*n, n)[1:]]
    #
    #     header = [  binascii.hexlify(header_array[0]),
    #                 binary_unpack('i', header_array[1]),
    #                 binary_unpack('i', header_array[2]),
    #                 binary_unpack('i', header_array[3]),
    #                 ]
    #     return header

def binary_unpack(t, b):
    return struct.unpack(t, b)[0]


def from_data3d_buffer(data3d_buffer):
    file_buffer = read_into_buffer(data3d_buffer_file)
    magic_number, version, structure_byte_length, payload_byte_length = get_header(file_buffer)
    expected_file_byte_length = HEADER_BYTE_LENGTH + structure_byte_length + payload_byte_length

    # Validation warnings
    if magic_number != MAGIC_NUMBER:
        print('File header error: Wrong magic number. File is probably not data3d buffer format.' + str(magic_number))
    if version != VERSION:
        print('File header error: Wrong version number: ' + str(version) + '. Parser supports version: ' + str(VERSION))

    # Validation errors
    print(len(file_buffer))
    print(expected_file_byte_length)


from_data3d_buffer(data3d_buffer_file)