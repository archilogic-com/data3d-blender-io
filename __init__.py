# coding=utf-8
bl_info = {
    "name": "Archilogic I/O data3d format",
    "author": "Madlaina Kalunder",
    "version": (0, 1),
    "blender": (2, 75, 0),
    "location": "File > import-export",
    "description": "Import-Export Archilogic Data3d format, "
                   "materials and textures",
    "warning": "Add-on is in development.",
    "wiki_url": "",
    "category": "Import-Export"
}

if "bpy" in locals():
    import importlib
    if "import_data3d" in locals():
        importlib.reload(import_data3d)
    if "export_data3d" in locals():
        importlib.reload(export_data3d)

import bpy
from bpy.props import (
        BoolProperty,
        FloatProperty,
        StringProperty,
        EnumProperty
        )

from bpy_extras.io_utils import (
        ImportHelper,
        ExportHelper,
        axis_conversion,
        orientation_helper_factory
        )


class ModuleInfo:
    add_on_version = '.'.join([str(item) for item in bl_info['version']])
    data3d_format_version = '1'


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
    ...

    # Materials:
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
    # Baking related material info
    add_lightmap = 'addLightmap'
    use_in_calc = 'useInBaking'
    hide_after_calc = 'hideAfterBaking'
    ...

IOData3dOrientationHelper = orientation_helper_factory('IOData3dOrientationHelper', axis_forward='-Z', axis_up='Y')


class ImportData3d(bpy.types.Operator, ImportHelper, IOData3dOrientationHelper):
    """ Load a Archilogic Data3d File """
    bl_idname = 'import_scene.data3d'
    bl_label = 'Import Data3d'
    bl_options = {'PRESET', 'UNDO'}

    filename_ext = '.data3d.json'
    filter_glob = StringProperty(default='*.data3d.json', options={'HIDDEN'})

    import_materials = BoolProperty(
        name='Import Materials',
        description='Import Materials and Textures.',
        default=True
        )

    import_hierarchy = BoolProperty(
        name='Import Hierarchy',
        description='Import objects with parent-child relations.',
        default=True
        )

    # Hidden context
    import_al_metadata = BoolProperty(
        name='Import Archilogic Metadata',
        description='Import Archilogic Metadata',
        default=False
    )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, 'import_materials')
        layout.prop(self, 'import_hierarchy')

        #Fixme Import materials (bool) if yes -> import cycles, import blender, use image search?

        layout.prop(self, "axis_forward")
        layout.prop(self, "axis_up")

    def execute(self, context):
        from . import import_data3d
        keywords = self.as_keywords(ignore=('axis_forward',
                                            'axis_up',
                                            'filter_glob',
                                            'filename_ext'))
        keywords['global_matrix'] = axis_conversion(from_forward=self.axis_forward, from_up=self.axis_up).to_4x4()
        return import_data3d.load(self, context, **keywords)

class ExportData3d(bpy.types.Operator, ExportHelper, IOData3dOrientationHelper):
    """ Export the scene as an Archilogic Data3d File """

    # export_materials
    # export_textures
    # apply modifiers

    bl_idname = 'export_scene.data3d'
    bl_label = 'Export Data3d'
    bl_options = {'PRESET'}

    filename_ext = '.data3d.json'
    filter_glob = StringProperty(default='*.data3d.json', options={'HIDDEN'})

    # Context
    use_selection = BoolProperty(
        name='Selection Only',
        description='Export selected objects only.',
        default=False
    )

    export_images = BoolProperty(
        name='Export Images',
        description='Export associated texture files.',
        default=False
    )

    # Hidden context
    export_al_metadata = BoolProperty(
        name='Export Archilogic Metadata',
        description='Export Archilogic Metadata, if it exists.',
        default=False
    )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, 'use_selection')
        layout.prop(self, 'export_images')

    def execute(self, context):
        from . import export_data3d

        keywords = self.as_keywords(ignore=('axis_forward',
                                            'axis_up',
                                            'filter_glob',
                                            'filename_ext'))
        global_matrix = axis_conversion(to_forward=self.axis_forward,
                                        to_up=self.axis_up,
                                        ).to_4x4()
        keywords["global_matrix"] = global_matrix
        return export_data3d.save(self, context, **keywords)


def menu_func_import(self, context):
    self.layout.operator(ImportData3d.bl_idname, text='Archilogic Data3d (data3d.json)')

def menu_func_export(self, context):
    self.layout.operator(ExportData3d.bl_idname, text='Archilogic Data3d (data3d.json)')

def register():
    bpy.utils.register_module(__name__)
    bpy.types.INFO_MT_file_import.append(menu_func_import)
    bpy.types.INFO_MT_file_export.append(menu_func_export)

def unregister():
    bpy.utils.unregister_module(__name__)
    bpy.types.INFO_MT_file_import.remove(menu_func_import)
    bpy.types.INFO_MT_file_export.remove(menu_func_export)

if __name__ == '__main__':
    register()