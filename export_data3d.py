import os
import sys
import json
import logging
from datetime import datetime
from collections import OrderedDict

import bpy

# Global Variables
C = bpy.context
D = bpy.data
O = bpy.ops

logging.basicConfig(level='DEBUG', format='%(asctime)s %(levelname)-10s %(message)s')
log = logging.getLogger('archilogic')

data3d_format_version = 1
addon_version = '?'

def export_images():
    ...

def write_materials():
    # From Metadata
    # Fallback: from Cycles or Blender internal
    # Don't forget Lightmapdata
    # Retun json material dictionary for writing
    ...

def parse_geometry(export_objects):
    # Prepare Mesh, tesselation, apply modifiers (...)
    # obj.to_mesh(context.scene, apply_modifiers=True, settings='RENDER' (, calc_tessface=True, calc_undeformed=False))
    ...

def test_json_export(output_path):
    export_data = OrderedDict()
    meta = export_data['meta'] = OrderedDict()
    meta['version'] = str(data3d_format_version)
    meta['exporter'] = 'Archilogic Data3d Exporter Version: ' + addon_version
    meta['timestamp'] = str(datetime.utcnow())

    with open(output_path, 'w', encoding='utf-8') as file:
        file.write(to_json(export_data))

def to_json(o, level=0):
    """
        Python's native JSON module adds a newline to every array element, since we
        deal with large arrays, we want the items in a row
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
        ret += json_quote + o + json_quote
    elif isinstance(o, bool):
        ret += 'true' if o else 'false'
    elif isinstance(o, int):
        ret += str(o)
    elif isinstance(o, float):
        ret += '%.7g' % o
    #elif isinstance(o, numpy.ndarray) ...:
    else:
        raise TypeError("Unknown type '%s' for json serialization" % str(type(o)))

    return ret


def _write(context, output_path, EXPORT_GLOBAL_MATRIX, EXPORT_SEL_ONLY):
    try:
        if not os.path.exists(os.path.dirname(output_path)):
            os.makedirs(os.path.dirname(output_path))
        log.info('Exporting Scene: %s', output_path)

        if EXPORT_SEL_ONLY:
            export_objects = context.selected_objects
        else:
            export_objects = context.selectable_objects

        parse_geometry(export_objects)
        test_json_export(output_path)
        ...

    except:
        raise Exception('Export Scene failed. ', sys.exc_info())


def save(operator, context, filepath='', check_existing=True, use_selection=False, global_matrix=None):
    """ Called by the user interface or another script.
        (...)
    """
    # Fixme Remove unused variables operator, context, check_existing
    if global_matrix is None:
        global_matrix = mathutils.Matrix()

    _write(context, filepath, EXPORT_GLOBAL_MATRIX=global_matrix, EXPORT_SEL_ONLY=use_selection)

    return {'FINISHED'}
