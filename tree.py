import FreeCAD


PROCESS_OBJECT_NAME = "HeatTreatmentProcess"
PROPERTY_GROUP = "Heat Treatment"

STAGE_LIBRARY = {
    "HeatingStage": {
        "label": "HeatingStage",
        "stage_type": "Heating",
        "properties": [
            ("App::PropertyFloat", "Temperature", "Target heating temperature, C", 930.0),
            ("App::PropertyFloat", "DurationMinutes", "Heating time, min", 45.0),
            ("App::PropertyString", "Atmosphere", "Heating atmosphere", "Protective"),
        ],
    },
    "CementationStage": {
        "label": "CementationStage",
        "stage_type": "Cementation",
        "properties": [
            ("App::PropertyFloat", "Temperature", "Cementation temperature, C", 930.0),
            ("App::PropertyFloat", "DurationHours", "Cementation duration, h", 6.0),
            ("App::PropertyFloat", "CarbonPotential", "Carbon potential, %C", 1.1),
            ("App::PropertyString", "Atmosphere", "Process atmosphere", "Endogas"),
            ("App::PropertyFloat", "CaseDepthTarget", "Target case depth, mm", 0.8),
        ],
    },
    "DiffusionStage": {
        "label": "DiffusionStage",
        "stage_type": "Diffusion",
        "properties": [
            ("App::PropertyFloat", "Temperature", "Diffusion temperature, C", 900.0),
            ("App::PropertyFloat", "DurationMinutes", "Diffusion time, min", 60.0),
            ("App::PropertyString", "Atmosphere", "Diffusion atmosphere", "Endogas"),
        ],
    },
    "QuenchingStage": {
        "label": "QuenchingStage",
        "stage_type": "Quenching",
        "properties": [
            ("App::PropertyFloat", "AustenitizingTemperature", "Austenitizing temperature, C", 820.0),
            ("App::PropertyFloat", "HoldMinutes", "Hold time before quenching, min", 30.0),
            ("App::PropertyString", "QuenchMedium", "Quench medium", "Oil"),
            ("App::PropertyFloat", "MediumTemperature", "Quench medium temperature, C", 60.0),
            ("App::PropertyFloat", "AgitationRate", "Agitation rate, rel. units", 1.0),
        ],
    },
    "TemperingStage": {
        "label": "TemperingStage",
        "stage_type": "Tempering",
        "properties": [
            ("App::PropertyFloat", "Temperature", "Tempering temperature, C", 180.0),
            ("App::PropertyFloat", "DurationMinutes", "Tempering duration, min", 90.0),
            ("App::PropertyInteger", "Cycles", "Number of tempering cycles", 1),
            ("App::PropertyString", "CoolingMethod", "Cooling method after tempering", "Air"),
        ],
    },
}

DEFAULT_STAGE_ORDER = [
    "HeatingStage",
    "CementationStage",
    "QuenchingStage",
    "TemperingStage",
]


def _ensure_property(obj, prop_type, prop_name, description, default_value=None):
    if prop_name not in obj.PropertiesList:
        obj.addProperty(prop_type, prop_name, PROPERTY_GROUP, description)
        if default_value is not None:
            setattr(obj, prop_name, default_value)


def _ensure_process_properties(process):
    _ensure_property(process, "App::PropertyString", "ProcessType", "Type of process", "Chemical Heat Treatment")
    _ensure_property(process, "App::PropertyString", "ProcessKey", "Rule set key", "carburizing")
    _ensure_property(process, "App::PropertyLink", "TargetObject", "Related solid model")
    _ensure_property(process, "App::PropertyString", "TargetPart", "Name of the related part or body", "")
    _ensure_property(process, "App::PropertyString", "Material", "Part material", "20\u0425")
    _ensure_property(process, "App::PropertyFloat", "TargetCaseDepth", "Required case depth, mm", 0.8)
    _ensure_property(process, "App::PropertyFloat", "TargetSurfaceHardness", "Required surface hardness, HRC", 62.0)
    _ensure_property(process, "App::PropertyFloat", "CoreHardnessTarget", "Required core hardness, HRC", 36.0)
    _ensure_property(process, "App::PropertyString", "ProcessNotes", "Notes for the whole process", "")


def _ensure_stage_common_properties(stage, stage_type):
    _ensure_property(stage, "App::PropertyString", "StageType", "Type of heat treatment stage", stage_type)
    _ensure_property(stage, "App::PropertyInteger", "SequenceNumber", "Stage position in process", 0)
    _ensure_property(stage, "App::PropertyBool", "Enabled", "Whether stage is active", True)
    _ensure_property(stage, "App::PropertyString", "Notes", "User notes for this stage", "")


def _apply_stage_schema(stage, stage_name):
    schema = STAGE_LIBRARY[stage_name]
    _ensure_stage_common_properties(stage, schema["stage_type"])

    for prop_type, prop_name, description, default_value in schema["properties"]:
        _ensure_property(stage, prop_type, prop_name, description, default_value)


def get_active_document():
    document = FreeCAD.ActiveDocument
    if document is None:
        document = FreeCAD.newDocument("Unnamed")
    return document


def find_process_group(document=None):
    document = document or FreeCAD.ActiveDocument
    if document is None:
        return None
    return document.getObject(PROCESS_OBJECT_NAME)


def ensure_process_group(document=None):
    document = get_active_document() if document is None else document
    process = find_process_group(document)
    if process is None:
        process = document.addObject("App::DocumentObjectGroup", PROCESS_OBJECT_NAME)
        process.Label = PROCESS_OBJECT_NAME

    _ensure_process_properties(process)
    _assign_target_part(document, process)
    return process


def _assign_target_part(document, process):
    if "TargetObject" in process.PropertiesList and process.TargetObject is not None:
        if not process.TargetPart:
            process.TargetPart = process.TargetObject.Label
        return

    if process.TargetPart:
        target = document.getObject(process.TargetPart)
        if target is None:
            target = next(
                (
                    obj
                    for obj in document.Objects
                    if getattr(obj, "Label", "") == process.TargetPart
                ),
                None,
            )
        if target is not None and hasattr(target, "Shape"):
            process.TargetObject = target
            return

    for obj in document.Objects:
        if getattr(obj, "TypeId", "") == "PartDesign::Body":
            process.TargetObject = obj
            process.TargetPart = obj.Label
            return

    candidates = []
    for obj in document.Objects:
        if not hasattr(obj, "Shape"):
            continue
        try:
            if not obj.Shape.isNull():
                candidates.append(obj)
        except Exception:
            continue

    if len(candidates) == 1:
        process.TargetObject = candidates[0]
        process.TargetPart = candidates[0].Label


def _next_stage_object_name(process, base_name):
    existing_names = {obj.Name for obj in process.Group}
    if base_name not in existing_names:
        return base_name

    index = 2
    while True:
        candidate = "{0}_{1}".format(base_name, index)
        if candidate not in existing_names:
            return candidate
        index += 1


def _next_sequence_number(process):
    highest = 0
    for obj in process.Group:
        if "SequenceNumber" in obj.PropertiesList:
            highest = max(highest, int(obj.SequenceNumber))
    return highest + 1


def _refresh_stage_labels(process):
    ordered = sorted(
        [obj for obj in process.Group if "SequenceNumber" in obj.PropertiesList],
        key=lambda item: int(item.SequenceNumber),
    )

    for obj in ordered:
        if "StageType" in obj.PropertiesList and obj.StageType:
            obj.Label = "{0:02d} - {1}".format(int(obj.SequenceNumber), obj.Name)


def create_stage(document, process, stage_name):
    if stage_name not in STAGE_LIBRARY:
        raise ValueError("Unknown stage type: {0}".format(stage_name))

    object_name = _next_stage_object_name(process, stage_name)
    stage = document.addObject("App::FeaturePython", object_name)
    stage.Label = object_name
    _apply_stage_schema(stage, stage_name)
    stage.SequenceNumber = _next_sequence_number(process)
    process.addObject(stage)
    _refresh_stage_labels(process)
    return stage


def ensure_default_process_tree(document=None):
    document = get_active_document() if document is None else document
    process = ensure_process_group(document)

    existing_names = {obj.Name for obj in process.Group}
    for stage_name in DEFAULT_STAGE_ORDER:
        if stage_name not in existing_names:
            create_stage(document, process, stage_name)

    _refresh_stage_labels(process)
    document.recompute()
    return process


def add_stage_to_process(stage_name, document=None):
    document = get_active_document() if document is None else document
    process = ensure_process_group(document)
    stage = create_stage(document, process, stage_name)
    document.recompute()
    return stage


def get_stage_names():
    return list(STAGE_LIBRARY.keys())
