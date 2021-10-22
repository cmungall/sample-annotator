from typing import Optional, List, Set, Any, Dict
from dataclasses import dataclass
from enum import Enum, unique
from collections import defaultdict

import logging
import pandas as pd

from nmdc_schema.nmdc import Biosample, GeolocationValue
from nmdc_schema.nmdc import slots as nmdc_slots

from .geolocation.geotools import GeoEngine
from .metadata.sample_schema import SampleSchema, underscore


from linkml_runtime.linkml_model.meta import ClassDefinition, SchemaDefinition, SlotDefinition, Definition

KEY_ENV_PACKAGE = nmdc_slots.env_package.name
KEY_CHECKLIST = 'checklist'

SAMPLE = Dict[str, Any]
STUDY = Dict[str, Any]
SCORE = float

@unique
class Category(str, Enum):
    Unclassified = 'unclassified'
    Core = 'core'
    Geo = 'geo'
    ControlledVocabulary = 'controlled-vocabulary'
    MissingCore = 'missing-core'
    Identifier = 'identifier'
    MeasurementSyntax = 'measurement-syntax'
    Units = 'units'
    UnknownField = 'unknown-field'
    Inapplicable = 'inapplicable'
    BadNull = 'bad-null'

    @staticmethod
    def list():
        return list(map(lambda c: c.value, Category))

@dataclass
class PackageCombo:
    """
    Tuple of environmental package and checklist
    """
    environmental_package: str = None
    checklist: str = None

@dataclass
class Message:
    """
    Individual report message
    """
    description: str = None
    severity: int = 1
    was_repaired: bool = None
    category: Category = Category.Unclassified
    field: str = None

    __cols__ = ['description', 'severity', 'field', 'was_repaired', 'category']

    def as_dict(self) -> Dict:
        return {v: self.__getattribute__(v) for v in vars(self)}



@dataclass
class AnnotationReport:
    """
    Annotation report for a single sample
    """
    messages: List[Message] = None
    package: PackageCombo = None
    input: SAMPLE = None
    output: SAMPLE = None
    sample_id: str = None
    annotation_sufficiency_score = 0.0

    def add_message(self, *args, **kwargs):
        m = Message(*args, **kwargs)
        if not self.messages:
            self.messages = []
        self.messages.append(m)

    def as_dataframe(self):
        items = [m.as_dict() for m in self.messages]
        return pd.DataFrame(items, columns=Message.__cols__)

    def max_severity(self):
        return max([m.severity for m in self.messages])

    def passes(self):
        return self.max_severity() == 0

    def messages_by_category(self) -> Dict:
        res = defaultdict(list)
        for m in self.messages:
            res[m.category.value].append(m)
        return res

@dataclass
class AnnotationMultiSampleReport:
    """
    Multi-report of a set of samples
    """
    reports: List[AnnotationReport] = None

    def as_dataframe(self):
        items = []
        cols = ['sample_id'] + Message.__cols__
        for r in self.reports:
            for m in r.messages:
                item = m.as_dict()
                item['sample_id'] = r.sample_id
                items.append(item)
        return pd.DataFrame(items, columns=cols)

    def all_outputs(self) -> List[SAMPLE]:
        return [r.output for r in self.reports]

