import itertools
import math
from typing import Any, Dict, List, Tuple

import Part

from rule_engine.models import GeometryFacts, Severity, ValidationMessage


class InvalidGeometryError(RuntimeError):
    pass


def _surface_name(face) -> str:
    return type(face.Surface).__name__


def _curve_name(edge) -> str:
    return type(edge.Curve).__name__


def _is_reversed(element) -> bool:
    return str(getattr(element, "Orientation", "")).lower() == "reversed"


def _edge_is_sharp(shape, edge) -> bool:
    if _curve_name(edge) != "Line":
        return False
    try:
        adjacent = shape.ancestorsOfType(edge, Part.Face)
    except Exception:
        return False
    return len(adjacent) >= 2 and all(_surface_name(face) == "Plane" for face in adjacent)


def _minimum_face_distance(
    faces,
    max_pairs: int,
    tolerance: float = 1e-7,
) -> Tuple[Any, List[str], bool]:
    best_distance = None
    best_faces: List[str] = []
    total_pairs = len(faces) * (len(faces) - 1) // 2

    for pair_number, (first_index, second_index) in enumerate(
        itertools.combinations(range(len(faces)), 2), start=1
    ):
        if pair_number > max_pairs:
            break
        try:
            distance = float(
                faces[first_index].distToShape(faces[second_index])[0]
            )
        except Exception:
            continue
        if distance <= tolerance:
            continue
        if best_distance is None or distance < best_distance:
            best_distance = distance
            best_faces = [
                "Face{0}".format(first_index + 1),
                "Face{0}".format(second_index + 1),
            ]

    return best_distance, best_faces, total_pairs > max_pairs


def _validate_shape(shape) -> None:
    if shape is None or shape.isNull():
        raise InvalidGeometryError("геометрия отсутствует или пуста")
    if not shape.isValid():
        raise InvalidGeometryError("форма не прошла проверку OpenCascade")
    if not shape.isClosed():
        raise InvalidGeometryError("тело не является замкнутым solid-объектом")
    if len(shape.Solids) != 1:
        raise InvalidGeometryError(
            "ожидалось одно твердотельное тело, обнаружено: {0}".format(
                len(shape.Solids)
            )
        )
    if not shape.Faces or not shape.Edges:
        raise InvalidGeometryError("у тела отсутствуют грани или рёбра")
    if float(shape.Volume) <= 0.0 or float(shape.Area) <= 0.0:
        raise InvalidGeometryError("объём или площадь поверхности равны нулю")


def analyze_geometry(model, geometry_rules: Dict[str, Any]):
    shape = getattr(model, "Shape", None)
    _validate_shape(shape)

    bounds = shape.BoundBox
    dimensions = (
        float(bounds.XLength),
        float(bounds.YLength),
        float(bounds.ZLength),
    )
    nonzero_dimensions = [value for value in dimensions if value > 1e-9]
    slenderness = (
        max(nonzero_dimensions) / min(nonzero_dimensions)
        if nonzero_dimensions
        else 0.0
    )

    cylindrical_faces = []
    hole_faces = []
    hole_diameters = []
    groove_faces = []
    full_circle = 2.0 * math.pi

    for index, face in enumerate(shape.Faces, start=1):
        if _surface_name(face) != "Cylinder":
            continue
        cylindrical_faces.append("Face{0}".format(index))
        radius = float(getattr(face.Surface, "Radius", 0.0))
        try:
            u_span = abs(float(face.ParameterRange[1]) - float(face.ParameterRange[0]))
        except Exception:
            u_span = full_circle

        if _is_reversed(face) and u_span >= full_circle - 1e-4:
            hole_faces.append("Face{0}".format(index))
            hole_diameters.append(2.0 * radius)
        elif _is_reversed(face):
            groove_faces.append("Face{0}".format(index))

    sharp_edges = []
    circular_radii = []
    min_radius_threshold = float(
        geometry_rules.get("check_sharp_edges", {}).get("min_radius_mm", 0.3)
    )
    for index, edge in enumerate(shape.Edges, start=1):
        curve_name = _curve_name(edge)
        radius = getattr(edge.Curve, "Radius", None)
        if radius is not None:
            radius = float(radius)
            circular_radii.append(radius)
            if radius < min_radius_threshold:
                sharp_edges.append("Edge{0}".format(index))
        elif _edge_is_sharp(shape, edge):
            sharp_edges.append("Edge{0}".format(index))

    if sharp_edges and any(
        _curve_name(shape.Edges[int(name[4:]) - 1]) == "Line"
        for name in sharp_edges
    ):
        minimum_radius = 0.0
    else:
        minimum_radius = min(circular_radii) if circular_radii else None

    thickness_config = geometry_rules.get("check_thin_walls", {})
    max_pairs = int(thickness_config.get("max_face_pairs", 5000))
    minimum_thickness, thickness_faces, partial = _minimum_face_distance(
        shape.Faces, max_pairs
    )

    face_areas = [float(face.Area) for face in shape.Faces if float(face.Area) > 1e-9]
    face_area_ratio = (
        max(face_areas) / min(face_areas) if len(face_areas) > 1 else 1.0
    )
    surface_to_volume = float(shape.Area) / float(shape.Volume)
    solid = shape.Solids[0]
    cavity_count = max(len(solid.Shells) - 1, 0)

    small_hole_limit = float(
        geometry_rules.get("check_holes", {}).get("small_diameter_mm", 6.0)
    )
    small_hole_faces = [
        face_name
        for face_name, diameter in zip(hole_faces, hole_diameters)
        if diameter < small_hole_limit
    ]

    transition_threshold = float(
        geometry_rules.get("check_section_transitions", {}).get(
            "max_face_area_ratio", 10.0
        )
    )
    massive_threshold = float(
        geometry_rules.get("check_surface_to_volume", {}).get(
            "min_ratio_per_mm", 0.1
        )
    )

    facts = GeometryFacts(
        model_name=model.Name,
        dimensions_mm=dimensions,
        volume_mm3=float(shape.Volume),
        surface_area_mm2=float(shape.Area),
        surface_to_volume=surface_to_volume,
        face_count=len(shape.Faces),
        edge_count=len(shape.Edges),
        solid_count=len(shape.Solids),
        cylindrical_face_count=len(cylindrical_faces),
        hole_faces=hole_faces,
        small_hole_faces=small_hole_faces,
        hole_diameters_mm=hole_diameters,
        groove_faces=groove_faces,
        cavity_count=cavity_count,
        sharp_edges=sharp_edges,
        minimum_radius_mm=minimum_radius,
        minimum_thickness_mm=minimum_thickness,
        minimum_thickness_faces=thickness_faces,
        thickness_analysis_partial=partial,
        slenderness_ratio=slenderness,
        face_area_ratio=face_area_ratio,
        has_massive_zones=surface_to_volume < massive_threshold,
        has_sudden_transitions=face_area_ratio > transition_threshold,
    )

    diagnostics: List[ValidationMessage] = []
    if minimum_thickness is None:
        diagnostics.append(
            ValidationMessage(
                code="HTO-GEO-090",
                severity=Severity.WARNING,
                problem="Не удалось определить минимальную толщину стенки.",
                cause="Для граней модели не найдено устойчивое ненулевое расстояние.",
                recommendation="Проверьте тонкостенные участки вручную.",
                object_name=model.Name,
            )
        )
    elif partial:
        diagnostics.append(
            ValidationMessage(
                code="HTO-GEO-091",
                severity=Severity.WARNING,
                problem="Анализ толщины выполнен частично.",
                cause="Количество пар граней превысило лимит {0}.".format(max_pairs),
                recommendation=(
                    "Увеличьте max_face_pairs в rules.yaml или проверьте сложную "
                    "геометрию вручную."
                ),
                object_name=model.Name,
                subelements=thickness_faces,
            )
        )

    return facts, diagnostics
