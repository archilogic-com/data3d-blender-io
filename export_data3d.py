import json

def export_images():
    ...

def write_materials():
    # From Metadata
    # Fallback: from Cycles or Blender internal
    # Don't forget Lightmapdata
    # Retun json material dictionary for writing
    ...

def ensure_extension():
    ...

def write_file():
    with open('testjson.hson', 'w') as outfile:
        json.dumps(['foo', {'bar': ('baz', None, 1.0, 2)}], outfile)
    ...



def _write(filepath, global_matrix):
    print(filepath)
    print(global_matrix)
    write_file()

def save(filepath='', global_matrix=None):
    """ Called by the user interface or another script.
        (...)
    """
    if global_matrix is None:
        global_matrix = mathutils.Matrix()

    _write(filepath, global_matrix)

    return {'FINISHED'}
