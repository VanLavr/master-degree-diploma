from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class Severity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class ValidationStatus(str, Enum):
    VALID = "VALID"
    VALID_WITH_WARNINGS = "VALID_WITH_WARNINGS"
    INVALID = "INVALID"
    VALIDATION_FAILED = "VALIDATION_FAILED"


@dataclass
class ValidationMessage:
    code: str
    severity: Severity
    problem: str
    cause: str
    recommendation: str
    object_name: str = ""
    subelements: List[str] = field(default_factory=list)

    @property
    def object_reference(self) -> str:
        if not self.object_name:
            return ""
        if not self.subelements:
            return self.object_name
        return "{0}.{1}".format(self.object_name, ", ".join(self.subelements))

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["severity"] = self.severity.value
        payload["object_reference"] = self.object_reference
        return payload


@dataclass
class GeometryFacts:
    model_name: str
    dimensions_mm: Tuple[float, float, float]
    volume_mm3: float
    surface_area_mm2: float
    surface_to_volume: float
    face_count: int
    edge_count: int
    solid_count: int
    cylindrical_face_count: int = 0
    hole_faces: List[str] = field(default_factory=list)
    small_hole_faces: List[str] = field(default_factory=list)
    hole_diameters_mm: List[float] = field(default_factory=list)
    groove_faces: List[str] = field(default_factory=list)
    cavity_count: int = 0
    sharp_edges: List[str] = field(default_factory=list)
    minimum_radius_mm: Optional[float] = None
    minimum_thickness_mm: Optional[float] = None
    minimum_thickness_faces: List[str] = field(default_factory=list)
    thickness_analysis_partial: bool = False
    slenderness_ratio: float = 0.0
    face_area_ratio: float = 0.0
    has_massive_zones: bool = False
    has_sudden_transitions: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ValidationResult:
    status: ValidationStatus
    messages: List[ValidationMessage] = field(default_factory=list)
    geometry: Optional[GeometryFacts] = None
    model_name: str = ""
    material: str = ""
    fingerprint: str = ""
    system_failure: bool = False

    @property
    def error_count(self) -> int:
        return sum(message.severity == Severity.ERROR for message in self.messages)

    @property
    def warning_count(self) -> int:
        return sum(message.severity == Severity.WARNING for message in self.messages)

    @property
    def info_count(self) -> int:
        return sum(message.severity == Severity.INFO for message in self.messages)

    @classmethod
    def from_messages(
        cls,
        messages: List[ValidationMessage],
        geometry: Optional[GeometryFacts] = None,
        model_name: str = "",
        material: str = "",
        fingerprint: str = "",
        system_failure: bool = False,
    ) -> "ValidationResult":
        if system_failure:
            status = ValidationStatus.VALIDATION_FAILED
        elif any(message.severity == Severity.ERROR for message in messages):
            status = ValidationStatus.INVALID
        elif any(message.severity == Severity.WARNING for message in messages):
            status = ValidationStatus.VALID_WITH_WARNINGS
        else:
            status = ValidationStatus.VALID

        return cls(
            status=status,
            messages=messages,
            geometry=geometry,
            model_name=model_name,
            material=material,
            fingerprint=fingerprint,
            system_failure=system_failure,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "messages": [message.to_dict() for message in self.messages],
            "geometry": self.geometry.to_dict() if self.geometry else None,
            "model_name": self.model_name,
            "material": self.material,
            "fingerprint": self.fingerprint,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "info_count": self.info_count,
            "system_failure": self.system_failure,
        }
