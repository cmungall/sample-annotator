import os
from unittest.case import TestCase
from tests import INPUT_DIR
from sample_annotator.text_mining.TextMining import SETTINGS_FILENAME, TextMining
from sample_annotator.sample_annotator import SampleAnnotator, AnnotationReport
import unittest
import yaml
import pandas as pd
from pandas._testing import assert_frame_equal

PWD = os.path.dirname(os.path.realpath(__file__))
TEST_DATA = os.path.join(INPUT_DIR, 'test_sample_info.yaml')


class TestNER(unittest.TestCase):
    """
    Test runner's NER process
    """
    def test_ner(self):

        annotator = SampleAnnotator()
        report = AnnotationReport()
        
        with open(TEST_DATA) as stream:
            test_obj = yaml.load(stream, Loader=yaml.FullLoader)

        for t in test_obj.get('tests'):
            source = None
            desc = t.get('description', None)
            if desc == 'TEST(NER)':
                expected_df = pd.DataFrame()
                sample = t.get('sample')
                report.input = sample
                annotator.perform_text_mining(sample, report)
                expected_output = t.get('output')
                # Assertions
                for key in expected_df.keys():
                    assert sample[key] == expected_output[key]
        
