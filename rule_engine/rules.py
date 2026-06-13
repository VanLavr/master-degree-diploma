from pathlib import Path
from typing import Any, Dict

import yaml

from rule_engine.models import Severity


class RuleConfigurationError(RuntimeError):
    pass


REQUIRED_SECTIONS = (
    "validation",
    "material_policy",
    "process_rules",
    "stage_rules",
    "geometry_rules",
    "target_rules",
    "materials",
)


class RuleBook:
    def __init__(self, data: Dict[str, Any], raw_text: str, path: Path):
        self.data = data
        self.raw_text = raw_text
        self.path = path
        self._validate()

    @property
    def strictness(self) -> str:
        return str(self.data["validation"].get("strictness", "normal")).lower()

    def _validate(self) -> None:
        if not isinstance(self.data, dict):
            raise RuleConfigurationError("корневой элемент YAML должен быть объектом")

        missing = [section for section in REQUIRED_SECTIONS if section not in self.data]
        if missing:
            raise RuleConfigurationError(
                "отсутствуют обязательные разделы: {0}".format(", ".join(missing))
            )

        for section in REQUIRED_SECTIONS:
            if not isinstance(self.data[section], dict):
                raise RuleConfigurationError(
                    "раздел {0} должен быть объектом".format(section)
                )

        if self.strictness not in ("soft", "normal", "strict"):
            raise RuleConfigurationError(
                "validation.strictness должен иметь значение soft, normal или strict"
            )

        priority = self.data["material_policy"].get("source_priority")
        if not isinstance(priority, list) or not priority:
            raise RuleConfigurationError(
                "material_policy.source_priority должен быть непустым списком"
            )

        required_stages = self.data["process_rules"].get("carburizing", {}).get(
            "required_stages"
        )
        if not isinstance(required_stages, list) or not required_stages:
            raise RuleConfigurationError(
                "process_rules.carburizing.required_stages должен быть непустым списком"
            )

    def severity(self, value: Any, critical: bool = False) -> Severity:
        try:
            severity = Severity(str(value).upper())
        except ValueError as exc:
            raise RuleConfigurationError(
                "неизвестный уровень серьёзности: {0}".format(value)
            ) from exc

        if critical or severity == Severity.INFO:
            return severity
        if self.strictness == "soft" and severity == Severity.ERROR:
            return Severity.WARNING
        if self.strictness == "strict" and severity == Severity.WARNING:
            return Severity.ERROR
        return severity

    def rule_enabled(self, section: str, rule_name: str, default: bool = True) -> bool:
        rule = self.data.get(section, {}).get(rule_name, {})
        if not isinstance(rule, dict):
            return default
        return bool(rule.get("enabled", default))

    def message(
        self,
        key: str,
        context: Dict[str, Any],
        default_problem: str,
        default_cause: str,
        default_recommendation: str,
    ):
        definition = self.data.get("messages", {}).get(key, {})

        def render(field: str, default: str) -> str:
            template = str(definition.get(field, default))
            try:
                return template.format(**context)
            except (KeyError, ValueError):
                return template

        return (
            render("problem", default_problem),
            render("cause", default_cause),
            render("recommendation", default_recommendation),
        )


def default_rules_path() -> Path:
    return Path(__file__).with_name("rules.yaml")


def load_rules(path=None) -> RuleBook:
    rules_path = Path(path) if path else default_rules_path()
    try:
        raw_text = rules_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuleConfigurationError(
            "не удалось прочитать {0}: {1}".format(rules_path.name, exc)
        ) from exc

    if not raw_text.strip():
        raise RuleConfigurationError("{0} пуст".format(rules_path.name))

    try:
        data = yaml.safe_load(raw_text)
    except yaml.YAMLError as exc:
        raise RuleConfigurationError(
            "ошибка синтаксиса {0}: {1}".format(rules_path.name, exc)
        ) from exc

    return RuleBook(data, raw_text, rules_path)
