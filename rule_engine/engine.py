import math
from typing import Any, Dict, List, Optional

from rule_engine.freecad_adapter import (
    collect_stages,
    compute_fingerprint,
    find_process,
    persist_result,
    read_saved_status,
    resolve_material,
    resolve_model,
    update_highlights,
)
from rule_engine.geometry import InvalidGeometryError, analyze_geometry
from rule_engine.models import (
    GeometryFacts,
    Severity,
    ValidationMessage,
    ValidationResult,
    ValidationStatus,
)
from rule_engine.rules import RuleBook, RuleConfigurationError, load_rules


STAGE_FALLBACK_ALIASES = {
    "heating": "heating",
    "cementation": "carburizing",
    "carburizing": "carburizing",
    "diffusion": "diffusion",
    "quenching": "quenching",
    "tempering": "tempering",
}


class ValidationEngine:
    def __init__(self, rules_path=None):
        self.rules_path = rules_path

    def validate(self, document, selection=None) -> ValidationResult:
        process = find_process(document)
        model = resolve_model(document, selection, process)
        messages: List[ValidationMessage] = []
        rules: Optional[RuleBook] = None
        facts: Optional[GeometryFacts] = None
        material = ""
        fingerprint = ""
        system_failure = False

        if document is None:
            return ValidationResult.from_messages(
                [
                    ValidationMessage(
                        code="HTO-SYS-001",
                        severity=Severity.ERROR,
                        problem="Не открыт документ FreeCAD.",
                        cause="Валидации требуется активный документ с моделью.",
                        recommendation="Откройте или создайте документ и повторите проверку.",
                    )
                ],
                system_failure=True,
            )

        try:
            rules = load_rules(self.rules_path)
        except RuleConfigurationError as exc:
            messages.append(
                ValidationMessage(
                    code="HTO-SYS-002",
                    severity=Severity.ERROR,
                    problem="Не удалось загрузить rules.yaml.",
                    cause=str(exc),
                    recommendation="Исправьте файл правил и повторите валидацию.",
                )
            )
            system_failure = True

        if model is None:
            messages.append(
                ValidationMessage(
                    code="HTO-MODEL-001",
                    severity=Severity.ERROR,
                    problem="Не выбрана модель изделия для проверки.",
                    cause=(
                        "В выделении, ссылке процесса и документе не найдено "
                        "единственное твердотельное тело."
                    ),
                    recommendation="Выберите Body или Part::Feature и повторите проверку.",
                )
            )
            system_failure = True
        elif process is not None:
            if "TargetObject" in process.PropertiesList:
                process.TargetObject = model
            if "TargetPart" in process.PropertiesList:
                process.TargetPart = model.Label

        if rules is not None and model is not None:
            try:
                facts, geometry_diagnostics = analyze_geometry(
                    model, rules.data["geometry_rules"]
                )
                for diagnostic in geometry_diagnostics:
                    diagnostic.severity = rules.severity(diagnostic.severity.value)
                    messages.append(diagnostic)
            except InvalidGeometryError as exc:
                messages.append(
                    ValidationMessage(
                        code="HTO-MODEL-002",
                        severity=Severity.ERROR,
                        problem="Геометрия модели некорректна.",
                        cause=str(exc),
                        recommendation=(
                            "Исправьте или импортируйте модель как замкнутое "
                            "твердотельное тело."
                        ),
                        object_name=getattr(model, "Name", ""),
                    )
                )
                system_failure = True
            except Exception as exc:
                messages.append(
                    ValidationMessage(
                        code="HTO-SYS-003",
                        severity=Severity.ERROR,
                        problem="Не удалось выполнить геометрический анализ.",
                        cause=str(exc),
                        recommendation=(
                            "Проверьте целостность модели и повторите валидацию."
                        ),
                        object_name=getattr(model, "Name", ""),
                    )
                )
                system_failure = True

        if rules is not None:
            material_resolution = resolve_material(
                process, model, rules.data["material_policy"]
            )
            material = self._normalize_material(
                material_resolution.value, rules.data
            )
            if not material:
                self._add(
                    messages,
                    rules,
                    "HTO-MAT-001",
                    rules.data["material_policy"].get(
                        "missing_material_severity", "error"
                    ),
                    "Материал изделия не задан.",
                    "Ни один разрешённый источник не содержит марку материала.",
                    "Укажите материал в процессе или в свойствах модели.",
                )
            elif material_resolution.used_default:
                self._add(
                    messages,
                    rules,
                    "HTO-MAT-002",
                    rules.data["material_policy"].get(
                        "default_material_severity", "warning"
                    ),
                    "Материал модели не задан; использован материал по умолчанию: {0}.".format(
                        material
                    ),
                    "Источники с более высоким приоритетом не содержат материал.",
                    "Явно укажите материал изделия.",
                    object_name=getattr(process, "Name", ""),
                )

            if process is None:
                self._add(
                    messages,
                    rules,
                    "HTO-PROC-000",
                    "error",
                    "Не создан технологический процесс ХТО.",
                    "В документе отсутствует объект HeatTreatmentProcess.",
                    "Создайте процесс и добавьте этапы перед валидацией.",
                )
            else:
                self._check_process(messages, rules, process, material)

            if facts is not None:
                self._check_geometry(messages, rules, model, facts)

            if model is not None:
                try:
                    fingerprint = compute_fingerprint(
                        model, process, rules.raw_text
                    )
                except Exception as exc:
                    messages.append(
                        ValidationMessage(
                            code="HTO-SYS-004",
                            severity=Severity.ERROR,
                            problem="Не удалось сформировать отпечаток валидации.",
                            cause=str(exc),
                            recommendation=(
                                "Повторите проверку после пересчёта документа."
                            ),
                            object_name=getattr(model, "Name", ""),
                        )
                    )
                    system_failure = True

        result = ValidationResult.from_messages(
            messages=messages,
            geometry=facts,
            model_name=getattr(model, "Name", ""),
            material=material,
            fingerprint=fingerprint,
            system_failure=system_failure,
        )

        try:
            persist_result(document, result, model)
            update_highlights(document, result, model)
            document.recompute()
        except Exception as exc:
            result.messages.append(
                ValidationMessage(
                    code="HTO-SYS-005",
                    severity=Severity.ERROR,
                    problem="Не удалось сохранить результат валидации.",
                    cause=str(exc),
                    recommendation="Сохраните документ и повторите проверку.",
                )
            )
            result.system_failure = True
            result.status = ValidationStatus.VALIDATION_FAILED

        return result

    def can_simulate(self, document, selection=None):
        saved = read_saved_status(document)
        if saved is None:
            return (
                False,
                "Моделирование невозможно: сначала выполните валидацию процесса.",
            )

        if saved["status"] not in (
            ValidationStatus.VALID,
            ValidationStatus.VALID_WITH_WARNINGS,
        ):
            return (
                False,
                "Моделирование невозможно: последняя валидация завершилась "
                "со статусом {0}. Устраните проблемы и повторите проверку.".format(
                    saved["status"].value
                ),
            )

        try:
            rules = load_rules(self.rules_path)
            process = find_process(document)
            model = resolve_model(document, selection, process)
            if model is None or process is None:
                return (
                    False,
                    "Моделирование невозможно: модель или процесс больше не доступны.",
                )
            current_fingerprint = compute_fingerprint(
                model, process, rules.raw_text
            )
        except Exception as exc:
            return (
                False,
                "Моделирование невозможно: не удалось проверить актуальность "
                "валидации ({0}).".format(exc),
            )

        if not saved["fingerprint"] or saved["fingerprint"] != current_fingerprint:
            return (
                False,
                "Модель, материал, правила или этапы процесса изменились после "
                "последней успешной валидации. Выполните валидацию повторно.",
            )
        return True, ""

    def _add(
        self,
        messages,
        rules,
        code,
        severity,
        problem,
        cause,
        recommendation,
        object_name="",
        subelements=None,
        critical=False,
    ):
        problem, cause, recommendation = rules.message(
            code,
            {
                "problem": problem,
                "cause": cause,
                "recommendation": recommendation,
                "object_name": object_name,
            },
            problem,
            cause,
            recommendation,
        )
        messages.append(
            ValidationMessage(
                code=code,
                severity=rules.severity(severity, critical=critical),
                problem=problem,
                cause=cause,
                recommendation=recommendation,
                object_name=object_name,
                subelements=list(subelements or []),
            )
        )

    def _normalize_material(self, material: str, data: Dict[str, Any]) -> str:
        material = str(material or "").strip()
        aliases = data.get("material_aliases", {})
        for alias, canonical in aliases.items():
            if material.casefold() == str(alias).casefold():
                return str(canonical)
        for canonical in data.get("materials", {}):
            if material.casefold() == str(canonical).casefold():
                return str(canonical)
        return material

    def _canonical_stage(self, stage_type: str, data: Dict[str, Any]) -> str:
        aliases = dict(STAGE_FALLBACK_ALIASES)
        aliases.update(
            {
                str(key).casefold(): str(value)
                for key, value in data.get("stage_aliases", {}).items()
            }
        )
        return aliases.get(str(stage_type).casefold(), str(stage_type).casefold())

    def _check_process(self, messages, rules, process, material):
        stages = collect_stages(process)
        enabled_stages = [
            stage for stage in stages if bool(getattr(stage, "Enabled", True))
        ]
        if not enabled_stages:
            self._add(
                messages,
                rules,
                "HTO-PROC-000",
                "error",
                "Технологический процесс не содержит активных этапов.",
                "Все этапы отсутствуют или отключены.",
                "Добавьте и включите этапы ХТО.",
                object_name=process.Name,
            )
            return

        process_key = str(getattr(process, "ProcessKey", "carburizing") or "carburizing")
        process_config = rules.data["process_rules"].get(process_key)
        if not isinstance(process_config, dict):
            self._add(
                messages,
                rules,
                "HTO-PROC-099",
                "error",
                "Неизвестный тип технологического процесса: {0}.".format(process_key),
                "Для типа процесса отсутствует раздел в rules.yaml.",
                "Исправьте ProcessKey или добавьте правила процесса.",
                object_name=process.Name,
            )
            return

        canonical = [
            self._canonical_stage(stage.StageType, rules.data)
            for stage in enabled_stages
        ]
        sequence_numbers = [
            int(getattr(stage, "SequenceNumber", 0)) for stage in enabled_stages
        ]
        if (
            any(number <= 0 for number in sequence_numbers)
            or len(sequence_numbers) != len(set(sequence_numbers))
        ):
            self._add(
                messages,
                rules,
                "HTO-PROC-002",
                "error",
                "Номера этапов должны быть положительными и уникальными.",
                "Обнаружены нулевые, отрицательные или повторяющиеся SequenceNumber.",
                "Исправьте номера этапов в секции Data.",
                object_name=process.Name,
            )

        required = list(process_config.get("required_stages", []))
        for required_stage in required:
            if required_stage not in canonical:
                self._add(
                    messages,
                    rules,
                    "HTO-PROC-001",
                    process_config.get("missing_stage_severity", "error"),
                    "Отсутствует обязательный этап «{0}».".format(
                        self._stage_label(required_stage, rules.data)
                    ),
                    "Этап обязателен для процесса {0}.".format(process_key),
                    "Добавьте этап в технологический процесс.",
                    object_name=process.Name,
                )

        allowed_order = list(process_config.get("allowed_order", required))
        last_order = -1
        last_stage = ""
        for stage, stage_key in zip(enabled_stages, canonical):
            if stage_key not in allowed_order:
                self._add(
                    messages,
                    rules,
                    "HTO-PROC-006",
                    "warning",
                    "Неизвестный этап «{0}».".format(stage.StageType),
                    "Этап не перечислен в допустимой последовательности.",
                    "Добавьте этап в rules.yaml или удалите его из процесса.",
                    object_name=stage.Name,
                )
                continue
            current_order = allowed_order.index(stage_key)
            if current_order < last_order:
                self._add(
                    messages,
                    rules,
                    "HTO-PROC-003",
                    process_config.get("sequence_severity", "error"),
                    "Нарушена последовательность этапов: «{0}» расположен после «{1}».".format(
                        self._stage_label(stage_key, rules.data),
                        self._stage_label(last_stage, rules.data),
                    ),
                    "SequenceNumber задаёт порядок, запрещённый rules.yaml.",
                    "Исправьте SequenceNumber этапов.",
                    object_name=stage.Name,
                )
            else:
                last_order = current_order
                last_stage = stage_key

        for stage, stage_key in zip(enabled_stages, canonical):
            self._check_stage(messages, rules, stage, stage_key)

        self._check_material_and_targets(
            messages, rules, process, enabled_stages, canonical, material, process_key
        )

    def _stage_label(self, stage_key, data):
        return data.get("stage_labels", {}).get(stage_key, stage_key)

    def _check_stage(self, messages, rules, stage, stage_key):
        config = rules.data["stage_rules"].get(stage_key)
        if not isinstance(config, dict):
            return
        if not config.get("enabled", True):
            return

        for property_name in config.get("required_properties", []):
            missing = property_name not in stage.PropertiesList
            if not missing:
                value = getattr(stage, property_name, None)
                missing = value is None or (
                    isinstance(value, str) and not value.strip()
                )
            if missing:
                self._add(
                    messages,
                    rules,
                    "HTO-PARAM-001",
                    config.get("missing_property_severity", "error"),
                    "Для этапа «{0}» не задан параметр {1}.".format(
                        stage.Label, property_name
                    ),
                    "Параметр обязателен согласно rules.yaml.",
                    "Укажите значение параметра в секции Data.",
                    object_name=stage.Name,
                )

        for property_name, limits in config.get("ranges", {}).items():
            if property_name not in stage.PropertiesList:
                continue
            try:
                value = float(getattr(stage, property_name))
            except (TypeError, ValueError):
                continue
            minimum = limits.get("min")
            maximum = limits.get("max")
            outside = (
                minimum is not None and value < float(minimum)
            ) or (
                maximum is not None and value > float(maximum)
            )
            if outside:
                self._add(
                    messages,
                    rules,
                    "HTO-PARAM-002",
                    limits.get("severity", config.get("range_severity", "error")),
                    "Параметр {0} этапа «{1}» равен {2} и выходит за допустимый диапазон.".format(
                        property_name, stage.Label, value
                    ),
                    "Допустимый диапазон: {0}–{1}.".format(minimum, maximum),
                    "Установите значение в допустимом диапазоне.",
                    object_name=stage.Name,
                )

        for property_name, allowed_config in config.get("allowed_values", {}).items():
            if property_name not in stage.PropertiesList:
                continue
            allowed = allowed_config.get("values", [])
            value = str(getattr(stage, property_name, "")).strip()
            if value.casefold() not in [str(item).casefold() for item in allowed]:
                self._add(
                    messages,
                    rules,
                    "HTO-PARAM-003",
                    allowed_config.get("severity", "error"),
                    "Значение {0} параметра {1} недопустимо.".format(
                        value or "«пусто»", property_name
                    ),
                    "Разрешены значения: {0}.".format(", ".join(map(str, allowed))),
                    "Выберите одно из разрешённых значений.",
                    object_name=stage.Name,
                )

    def _check_material_and_targets(
        self,
        messages,
        rules,
        process,
        stages,
        canonical,
        material,
        process_key,
    ):
        material_config = rules.data["materials"].get(material)
        if material and material_config is None:
            self._add(
                messages,
                rules,
                "HTO-MAT-003",
                rules.data["material_policy"].get(
                    "unknown_material_severity", "warning"
                ),
                "Для материала «{0}» отсутствуют правила.".format(material),
                "Марка не найдена в разделе materials.",
                "Добавьте свойства материала в rules.yaml.",
                object_name=process.Name,
            )
        elif material_config is not None:
            compatible = material_config.get("compatible_processes", [])
            if process_key not in compatible:
                self._add(
                    messages,
                    rules,
                    "HTO-MAT-004",
                    material_config.get("incompatible_severity", "error"),
                    "Материал «{0}» не рекомендуется для процесса {1}.".format(
                        material, process_key
                    ),
                    material_config.get(
                        "incompatibility_reason",
                        "Процесс отсутствует в списке совместимых.",
                    ),
                    material_config.get(
                        "recommendation",
                        "Выберите другой материал или технологический процесс.",
                    ),
                    object_name=process.Name,
                )

        target_config = rules.data["target_rules"]
        ranges = dict(target_config.get("defaults", {}))
        if material_config:
            ranges.update(material_config.get("targets", {}))

        target_properties = {
            "TargetCaseDepth": "case_depth_mm",
            "TargetSurfaceHardness": "surface_hardness_hrc",
            "CoreHardnessTarget": "core_hardness_hrc",
        }
        for property_name, range_name in target_properties.items():
            if property_name not in process.PropertiesList or range_name not in ranges:
                continue
            value = float(getattr(process, property_name))
            limits = ranges[range_name]
            minimum = float(limits["min"])
            maximum = float(limits["max"])
            if value < minimum or value > maximum:
                self._add(
                    messages,
                    rules,
                    "HTO-TARGET-001",
                    limits.get("severity", "error"),
                    "Целевой параметр {0} равен {1} и недопустим.".format(
                        property_name, value
                    ),
                    "Рекомендуемый диапазон для материала {0}: {1}–{2}.".format(
                        material or "не задан", minimum, maximum
                    ),
                    "Скорректируйте целевое значение.",
                    object_name=process.Name,
                )

        if material_config and "quenching" in canonical:
            quenching = stages[canonical.index("quenching")]
            medium = str(getattr(quenching, "QuenchMedium", "")).strip()
            allowed_media = material_config.get("quench_media", [])
            if allowed_media and medium.casefold() not in [
                str(value).casefold() for value in allowed_media
            ]:
                self._add(
                    messages,
                    rules,
                    "HTO-MAT-005",
                    material_config.get("quench_medium_severity", "error"),
                    "Среда закалки «{0}» не подходит для материала {1}.".format(
                        medium, material
                    ),
                    "Допустимые среды: {0}.".format(", ".join(allowed_media)),
                    "Выберите совместимую закалочную среду.",
                    object_name=quenching.Name,
                )

        consistency = target_config.get("case_depth_consistency", {})
        if (
            consistency.get("enabled", True)
            and "carburizing" in canonical
            and "TargetCaseDepth" in process.PropertiesList
        ):
            carburizing = stages[canonical.index("carburizing")]
            hours = float(getattr(carburizing, "DurationHours", 0.0))
            coefficient = float(consistency.get("coefficient", 0.30))
            tolerance = float(consistency.get("tolerance_mm", 0.15))
            estimated = coefficient * math.sqrt(max(hours, 0.0))
            target = float(process.TargetCaseDepth)
            if target > estimated + tolerance:
                self._add(
                    messages,
                    rules,
                    "HTO-TARGET-002",
                    consistency.get("severity", "warning"),
                    "Целевая глубина слоя {0:.2f} мм не согласуется со временем цементации.".format(
                        target
                    ),
                    "Оценочная глубина для {0:.2f} ч составляет {1:.2f} мм.".format(
                        hours, estimated
                    ),
                    "Увеличьте время цементации или уменьшите целевую глубину.",
                    object_name=carburizing.Name,
                )

    def _check_geometry(self, messages, rules, model, facts):
        geometry_rules = rules.data["geometry_rules"]

        thin_wall = geometry_rules.get("check_thin_walls", {})
        if thin_wall.get("enabled", True) and facts.minimum_thickness_mm is not None:
            threshold = float(thin_wall.get("min_thickness_mm", 2.0))
            if facts.minimum_thickness_mm < threshold:
                self._add(
                    messages,
                    rules,
                    "HTO-GEO-001",
                    thin_wall.get("severity", "warning"),
                    "Обнаружена тонкая стенка {0:.2f} мм.".format(
                        facts.minimum_thickness_mm
                    ),
                    "Значение меньше порога {0:.2f} мм.".format(threshold),
                    "Увеличьте толщину или снизьте интенсивность охлаждения.",
                    object_name=model.Name,
                    subelements=facts.minimum_thickness_faces,
                )

        sharp = geometry_rules.get("check_sharp_edges", {})
        if sharp.get("enabled", True) and facts.sharp_edges:
            threshold = float(sharp.get("min_radius_mm", 0.3))
            self._add(
                messages,
                rules,
                "HTO-GEO-002",
                sharp.get("severity", "warning"),
                "Обнаружены острые кромки или радиусы менее {0:.2f} мм.".format(
                    threshold
                ),
                "Такие кромки повышают концентрацию напряжений.",
                "Добавьте скругления в проблемных зонах.",
                object_name=model.Name,
                subelements=facts.sharp_edges,
            )

        holes = geometry_rules.get("check_holes", {})
        if holes.get("enabled", True) and facts.small_hole_faces:
            threshold = float(holes.get("small_diameter_mm", 6.0))
            self._add(
                messages,
                rules,
                "HTO-GEO-003",
                holes.get("severity", "warning"),
                "Обнаружены отверстия диаметром менее {0:.2f} мм.".format(threshold),
                "В малых отверстиях возможна неравномерная цементация.",
                "Проверьте доступ технологической среды к внутренним поверхностям.",
                object_name=model.Name,
                subelements=facts.small_hole_faces,
            )

        cavities = geometry_rules.get("check_cavities", {})
        if cavities.get("enabled", True) and facts.cavity_count:
            self._add(
                messages,
                rules,
                "HTO-GEO-004",
                cavities.get("severity", "warning"),
                "Обнаружены внутренние полости: {0}.".format(facts.cavity_count),
                "Внутренние оболочки могут прогреваться и насыщаться неравномерно.",
                "Проверьте вентиляцию и доступ технологической среды.",
                object_name=model.Name,
            )

        transitions = geometry_rules.get("check_section_transitions", {})
        if transitions.get("enabled", True) and facts.has_sudden_transitions:
            self._add(
                messages,
                rules,
                "HTO-GEO-005",
                transitions.get("severity", "warning"),
                "Обнаружен значительный перепад площадей граней.",
                "Отношение максимальной площади грани к минимальной равно {0:.2f}.".format(
                    facts.face_area_ratio
                ),
                "Проверьте резкие переходы сечений и добавьте плавные сопряжения.",
                object_name=model.Name,
            )

        ratio = geometry_rules.get("check_surface_to_volume", {})
        if ratio.get("enabled", True):
            maximum = float(ratio.get("max_ratio_per_mm", 1.0))
            minimum = float(ratio.get("min_ratio_per_mm", 0.1))
            if facts.surface_to_volume > maximum:
                self._add(
                    messages,
                    rules,
                    "HTO-GEO-006",
                    ratio.get("severity", "warning"),
                    "Высокое отношение площади поверхности к объёму: {0:.3f} 1/мм.".format(
                        facts.surface_to_volume
                    ),
                    "Деталь склонна к быстрому нагреву и охлаждению.",
                    "Используйте менее интенсивные режимы нагрева и закалки.",
                    object_name=model.Name,
                )
            elif facts.surface_to_volume < minimum:
                self._add(
                    messages,
                    rules,
                    "HTO-GEO-007",
                    ratio.get("severity", "warning"),
                    "Низкое отношение площади поверхности к объёму: {0:.3f} 1/мм.".format(
                        facts.surface_to_volume
                    ),
                    "Массивная деталь может недостаточно прогреваться в сердцевине.",
                    "Увеличьте выдержку или проверьте температурную равномерность.",
                    object_name=model.Name,
                )

        slender = geometry_rules.get("check_slender_elements", {})
        if (
            slender.get("enabled", True)
            and facts.slenderness_ratio > float(slender.get("max_ratio", 10.0))
        ):
            self._add(
                messages,
                rules,
                "HTO-GEO-008",
                slender.get("severity", "warning"),
                "Обнаружена вытянутая тонкая геометрия.",
                "Отношение максимального габарита к минимальному равно {0:.2f}.".format(
                    facts.slenderness_ratio
                ),
                "Предусмотрите оснастку или менее интенсивное охлаждение.",
                object_name=model.Name,
            )

        grooves = geometry_rules.get("check_grooves", {})
        if grooves.get("enabled", True) and facts.groove_faces:
            self._add(
                messages,
                rules,
                "HTO-GEO-009",
                grooves.get("severity", "warning"),
                "Обнаружены пазы или канавки.",
                "Выявлены вогнутые цилиндрические поверхности неполного охвата.",
                "Проверьте равномерность насыщения и охлаждения этих зон.",
                object_name=model.Name,
                subelements=facts.groove_faces,
            )
