# coding=utf-8
bl_info = {
    "name": "Archilogic I/O data3d format",
    "author": "Madlaina Kalunder",
    "version": (1, 1),
    "blender": (2, 80, 0),
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
        orientation_helper
        )


class ModuleInfo:
    add_on_version = '.'.join([str(item) for item in bl_info['version']])
    data3d_format_version = '1'


@orientation_helper(axis_forward='-Z', axis_up='Y')
class ImportData3d(bpy.types.Operator, ImportHelper):
    """ Load a Archilogic Data3d File """

    bl_idname = 'import_scene.data3d'
    bl_label = 'Import Data3d'
    bl_options = {'PRESET', 'UNDO'}

    filter_glob: StringProperty(default='*.data3d.buffer;*.data3d.json', options={'HIDDEN'})

    import_materials: BoolProperty(
        name='Import Materials',
        description='Import Materials and Textures.',
        default=True
        )

    import_hierarchy: BoolProperty(
        name='Import Hierarchy',
        description='Import objects with parent-child relations.',
        default=True
        )

    # Hidden context
    import_al_metadata: EnumProperty(
        name='DATA3D Metadata',
        description='Import Archilogic Metadata',
        default='NONE',
        items=[
            ('NONE', 'none', '', 0),
            ('BASIC', 'basic material metadata', '', 1),
            ('ADVANCED', 'advanced material metadata', '', 2)
            ]
    )

    # Fixme: Change to enum property (custom-split-normals: {none, raw, Autosmooth}
    smooth_split_normals: BoolProperty(
        name='Autodetect smooth vertices from custom split normals.',
        description='Autosmooth vertex normals.',
        default=True
    )

    import_place_holder_images: BoolProperty(
        name='Placeholder Images',
        description='Import a placeholder image if the source image is unavailable',
        default=True
    )

    config_logger: BoolProperty(
        name='Configure logger',
        description='Configure and format log output',
        default=True
    )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, 'import_materials')
        if self.import_materials is True:
            box = layout.box()
            row = box.row()
            row.label(text='Material Import Options')
            # Fixme: Add Material import options
            #row = box.row()
            #row.prop(self, "create cycles material")
            row = box.row()
            row.prop(self, "import_place_holder_images")

        layout.prop(self, 'import_hierarchy')

        layout.prop(self, "axis_forward")
        layout.prop(self, "axis_up")

    def execute(self, context):
        from . import import_data3d
        keywords = self.as_keywords(ignore=('axis_forward',
                                            'axis_up',
                                            'filter_glob'))
        keywords['global_matrix'] = axis_conversion(from_forward=self.axis_forward, from_up=self.axis_up).to_4x4()
        return import_data3d.load(**keywords)

@orientation_helper(axis_forward='-Z', axis_up='Y')
class ExportData3d(bpy.types.Operator, ExportHelper):
    """ Export the scene as an Archilogic Data3d File """

    # export_materials
    # export_textures
    # apply modifiers

    bl_idname = 'export_scene.data3d'
    bl_label = 'Export Data3d'
    bl_options = {'PRESET'}

    filename_ext = '.data3d.json'
    filter_glob: StringProperty(default='*.data3d.buffer;*.data3d.json', options={'HIDDEN'})

    # Context
    export_format: EnumProperty(
        name='Format',
        description='Export geometry interleaved(buffer) or non-interleaved (json).',
        default='NON_INTERLEAVED',
        items=[
            ('INTERLEAVED', 'data3d.buffer', '', 0),
            ('NON_INTERLEAVED', 'data3d.json', '', 1)
            ]
    )

    use_selection: BoolProperty(
        name='Selection Only',
        description='Export selected objects only.',
        default=False
    )

    export_images: BoolProperty(
        name='Export Images',
        description='Export associated texture files.',
        default=False
    )

    # Hidden context
    export_al_metadata: BoolProperty(
        name='Export Archilogic Metadata',
        description='Export Archilogic Metadata, if it exists.',
        default=False
    )

    config_logger: BoolProperty(
        name='Configure logger',
        description='Configure and format log output',
        default=True
    )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, 'export_format')
        layout.prop(self, 'use_selection')
        layout.prop(self, 'export_images')

    def execute(self, context):
        from . import export_data3d

        keywords = self.as_keywords(ignore=('axis_forward',
                                            'axis_up',
                                            'filter_glob',
                                            'filename_ext',
                                            'check_existing'))
        global_matrix = axis_conversion(to_forward=self.axis_forward,
                                        to_up=self.axis_up,
                                        ).to_4x4()
        keywords["global_matrix"] = global_matrix
        return export_data3d.save(context, **keywords)


def menu_func_import(self, context):
    self.layout.operator(ImportData3d.bl_idname, text='Archilogic Data3d (data3d.buffer/data3d.json)')


def menu_func_export(self, context):
    self.layout.operator(ExportData3d.bl_idname, text='Archilogic Data3d (data3d.buffer/data3d.json)')

classes = (
    ImportData3d,
    ExportData3d,
)

def register():
    from bpy.utils import register_class
    for cls in classes:
        register_class(cls)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)


def unregister():
    from bpy.utils import unregister_class
    for cls in reversed(classes):
        unregister_class(cls)
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)


if __name__ == '__main__':
    register()
