
def _write(filepath, global_matrix):
    print(filepath)
    print(global_matrix)

def save(filepath='', global_matrix=None):
    """ Called by the user interface or another script.
        (...)
    """
    if global_matrix is None:
        global_matrix = mathutils.Matrix()

    _write(filepath='', global_matrix=None)

    return {'FINISHED'}
