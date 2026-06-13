import hashlib
import json
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

import FreeCAD
import Part

from rule_engine.models import Severity, ValidationResult, ValidationStatus


PROCESS_OBJECT_NAME = "HeatTreatmentProcess"
RESULT_OBJECT_NAME = "CHTValidationResult"
HIGHLIGHT_GROUP_NAME = "CHTValidationHighlights"
ERROR_HIGHLIGHT_NAME = "CHTValidationErrors"
WARNING_HIGHLIGHT_NAME = "CHTValidationWarnings"
INTERNAL_NAMES = {
    RESULT_OBJECT_NAME,
    HIGHLIGHT_GROUP_NAME,
    ERROR_HIGHLIGHT_NAME,
    WARNING_HIGHLIGHT_NAME,
}
MATERIAL_PLACEHOLDERS = {"", "steel", "сталь", "не задан", "none", "unknown"}


@dataclass
class MaterialResolution:
    value: str
    source: str
    used_default: bool = False


def find_process(document):
    if document is None:
        return None
    return document.getObject(PROCESS_OBJECT_NAME)


def _selection_object(item):
    return getattr(item, "Object", item)


def _is_internal(obj) -> bool:
    if obj is None:
        return True
    if getattr(obj, "Name", "") in INTERNAL_NAMES:
        return True
    return getattr(obj, "StageType", None) is not None


def _has_shape(obj) -> bool:
    if _is_internal(obj) or not hasattr(obj, "Shape"):
        return False
    try:
        return not obj.Shape.isNull()
    except Exception:
        return False


def resolve_model(document, selection=None, process=None):
    if document is None:
        return None

    for selected in selection or []:
        obj = _selection_object(selected)
        if _has_shape(obj):
            return obj

    process = process or find_process(document)
    if process is not None and "TargetObject" in process.PropertiesList:
        target = process.TargetObject
        if _has_shape(target):
            return target

    if process is not None and "TargetPart" in process.PropertiesList:
        target_name = str(process.TargetPart or "").strip()
        if target_name:
            target = document.getObject(target_name)
            if target is None:
                target = next(
                    (
                        obj
                        for obj in document.Objects
                        if getattr(obj, "Label", "") == target_name
                    ),
                    None,
                )
            if _has_shape(target):
                return target

    bodies = [
        obj
        for obj in document.Objects
        if getattr(obj, "TypeId", "") == "PartDesign::Body" and _has_shape(obj)
    ]
    if len(bodies) == 1:
        return bodies[0]

    candidates = [obj for obj in document.Objects if _has_shape(obj)]
    top_level_candidates = [
        obj
        for obj in candidates
        if not getattr(obj, "InList", None)
        or all(
            getattr(parent, "Name", "") in INTERNAL_NAMES
            for parent in getattr(obj, "InList", [])
        )
    ]
    if len(top_level_candidates) == 1:
        return top_level_candidates[0]
    if len(candidates) == 1:
        return candidates[0]
    return None


def _plain_value(value):
    if hasattr(value, "Value"):
        return value.Value
    if hasattr(value, "Name") and hasattr(value, "Document"):
        return value.Name
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (list, tuple)):
        return [_plain_value(item) for item in value]
    return str(value)


def _read_material(obj) -> str:
    if obj is None:
        return ""
    for property_name in ("Material", "MaterialName", "SteelGrade"):
        if property_name not in getattr(obj, "PropertiesList", []):
            continue
        value = str(_plain_value(getattr(obj, property_name, "")) or "").strip()
        if value.lower() not in MATERIAL_PLACEHOLDERS:
            return value
    return ""


def resolve_material(process, model, material_policy: Dict[str, Any]):
    sources = {
        "process_form": lambda: _read_material(process),
        "freecad_object": lambda: _read_material(model),
        "default": lambda: (
            str(material_policy.get("default_material", "")).strip()
            if material_policy.get("allow_default_material", False)
            else ""
        ),
    }

    for source in material_policy.get("source_priority", []):
        reader = sources.get(str(source))
        if reader is None:
            continue
        value = reader()
        if value:
            return MaterialResolution(
                value=value,
                source=str(source),
                used_default=str(source) == "default",
            )
    return MaterialResolution(value="", source="", used_default=False)


def collect_stages(process) -> List[Any]:
    if process is None:
        return []
    stages = [
        obj
        for obj in getattr(process, "Group", [])
        if "StageType" in getattr(obj, "PropertiesList", [])
    ]
    return sorted(
        stages,
        key=lambda obj: (
            int(getattr(obj, "SequenceNumber", 0)),
            getattr(obj, "Name", ""),
        ),
    )


def _object_snapshot(obj, excluded: Iterable[str]) -> Dict[str, Any]:
    excluded_names = set(excluded)
    result = {}
    for property_name in sorted(getattr(obj, "PropertiesList", [])):
        if property_name in excluded_names:
            continue
        try:
            result[property_name] = _plain_value(getattr(obj, property_name))
        except Exception:
            result[property_name] = "<unavailable>"
    return result


def compute_fingerprint(model, process, rules_text: str) -> str:
    if model is None or not hasattr(model, "Shape"):
        geometry_text = ""
    else:
        geometry_text = model.Shape.exportBrepToString()

    process_snapshot = (
        _object_snapshot(
            process,
            {
                "ExpressionEngine",
                "Group",
                "Label",
                "Label2",
                "Proxy",
                "TargetObject",
            },
        )
        if process is not None
        else None
    )
    stages = [
        {
            "name": stage.Name,
            "properties": _object_snapshot(
                stage,
                {"ExpressionEngine", "Label", "Label2", "Proxy"},
            ),
        }
        for stage in collect_stages(process)
    ]
    payload = json.dumps(
        {
            "model_name": getattr(model, "Name", ""),
            "geometry": geometry_text,
            "process": process_snapshot,
            "stages": stages,
            "rules": rules_text,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _ensure_property(obj, property_type, name, description):
    if name not in obj.PropertiesList:
        obj.addProperty(property_type, name, "CHT Validation", description)


def persist_result(document, result: ValidationResult, model=None):
    if document is None:
        return None
    obj = document.getObject(RESULT_OBJECT_NAME)
    if obj is None:
        obj = document.addObject("App::FeaturePython", RESULT_OBJECT_NAME)
        obj.Label = "Результат валидации ХТО"

    properties = (
        ("App::PropertyString", "ValidationStatus", "Итоговый статус"),
        ("App::PropertyInteger", "ErrorCount", "Количество ошибок"),
        ("App::PropertyInteger", "WarningCount", "Количество предупреждений"),
        ("App::PropertyInteger", "InfoCount", "Количество сообщений"),
        ("App::PropertyString", "MessagesJson", "Сообщения в формате JSON"),
        ("App::PropertyString", "Material", "Материал"),
        ("App::PropertyString", "InputFingerprint", "Отпечаток входных данных"),
        ("App::PropertyLink", "Model", "Проверенная модель"),
    )
    for property_type, name, description in properties:
        _ensure_property(obj, property_type, name, description)

    obj.ValidationStatus = result.status.value
    obj.ErrorCount = result.error_count
    obj.WarningCount = result.warning_count
    obj.InfoCount = result.info_count
    obj.MessagesJson = json.dumps(
        [message.to_dict() for message in result.messages],
        ensure_ascii=False,
        sort_keys=True,
    )
    obj.Material = result.material
    obj.InputFingerprint = result.fingerprint
    obj.Model = model
    return obj


def _subshape(shape, name):
    if name.startswith("Face"):
        index = int(name[4:]) - 1
        return shape.Faces[index] if 0 <= index < len(shape.Faces) else None
    if name.startswith("Edge"):
        index = int(name[4:]) - 1
        return shape.Edges[index] if 0 <= index < len(shape.Edges) else None
    return None


def _highlight_object(document, group, name, label, color):
    obj = document.getObject(name)
    if obj is None:
        obj = document.addObject("Part::Feature", name)
        obj.Label = label
        group.addObject(obj)
    view = getattr(obj, "ViewObject", None)
    if view is not None:
        view.ShapeColor = color
        view.LineColor = color
        view.Transparency = 25
        view.Selectable = False
    return obj


def update_highlights(document, result: ValidationResult, model=None):
    if document is None:
        return
    group = document.getObject(HIGHLIGHT_GROUP_NAME)
    if group is None:
        group = document.addObject("App::DocumentObjectGroup", HIGHLIGHT_GROUP_NAME)
        group.Label = "Проблемные зоны валидации"

    error_obj = _highlight_object(
        document,
        group,
        ERROR_HIGHLIGHT_NAME,
        "Критические зоны",
        (1.0, 0.15, 0.15),
    )
    warning_obj = _highlight_object(
        document,
        group,
        WARNING_HIGHLIGHT_NAME,
        "Зоны риска",
        (1.0, 0.75, 0.1),
    )

    severity_shapes = {Severity.ERROR: [], Severity.WARNING: []}
    if model is not None and hasattr(model, "Shape"):
        used = {Severity.ERROR: set(), Severity.WARNING: set()}
        for message in result.messages:
            if (
                message.severity not in severity_shapes
                or message.object_name != model.Name
            ):
                continue
            for subelement in message.subelements:
                key = (model.Name, subelement)
                if key in used[message.severity]:
                    continue
                subshape = _subshape(model.Shape, subelement)
                if subshape is not None:
                    severity_shapes[message.severity].append(subshape.copy())
                    used[message.severity].add(key)

    error_obj.Shape = (
        Part.makeCompound(severity_shapes[Severity.ERROR])
        if severity_shapes[Severity.ERROR]
        else Part.Shape()
    )
    warning_obj.Shape = (
        Part.makeCompound(severity_shapes[Severity.WARNING])
        if severity_shapes[Severity.WARNING]
        else Part.Shape()
    )

    for obj, severity in (
        (error_obj, Severity.ERROR),
        (warning_obj, Severity.WARNING),
    ):
        view = getattr(obj, "ViewObject", None)
        if view is not None:
            view.Visibility = bool(severity_shapes[severity])


def read_saved_status(document):
    if document is None:
        return None
    obj = document.getObject(RESULT_OBJECT_NAME)
    if obj is None or "ValidationStatus" not in obj.PropertiesList:
        return None
    try:
        status = ValidationStatus(str(obj.ValidationStatus))
    except ValueError:
        return None
    return {
        "status": status,
        "fingerprint": str(getattr(obj, "InputFingerprint", "") or ""),
        "object": obj,
    }
