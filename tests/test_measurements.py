# -*- coding: utf-8 -*-
import os
from tests import MODEL_DIR, INPUT_DIR, OUTPUT_DIR

from sample_annotator.measurements.measurements import MeasurementEngine
from sample_annotator.report_model import AnnotationReport

"""Test the module can be imported."""

import unittest
import csv

class TestMeasurements(unittest.TestCase):
    """annotation test."""

    def test_functionality(self):
        report = AnnotationReport(messages=[])
        m = MeasurementEngine()
        qv = m.repair('2cm', report=report)
        print(qv)


    def test_salinity(self):
        tsv_file = open("./tests/inputs/salinity_summary.tsv")
        salinity_data = csv.reader(tsv_file, delimiter="\t")

        report = AnnotationReport(messages=[])
        m = MeasurementEngine()

        for row in salinity_data:
            print(row)

            qv = m.repair(row[1], report=report)
            print(qv)

