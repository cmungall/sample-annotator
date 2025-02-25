# -*- coding: utf-8 -*-
import os
from tests import MODEL_DIR, INPUT_DIR, OUTPUT_DIR, EXAMPLE_DIR, EXAMPLE_OUTDIR
from os.path import isfile, join
from sample_annotator import SampleAnnotator
from sample_annotator.metadata.sample_schema import SampleSchema
import pandas as pd

"""Test the module can be imported."""

import unittest
import yaml
import json

TEST_DATA = os.path.join(INPUT_DIR, 'test_sample_info.yaml')
REPORT_OUT = os.path.join(OUTPUT_DIR, 'report.tsv')
SAMPLES_OUT = os.path.join(OUTPUT_DIR, 'samples.yaml')


class TestAnnotate(unittest.TestCase):
    """annotation test."""

    def test_examples(self):
        annotator = SampleAnnotator()
        contents = [join(EXAMPLE_DIR, f) for f in os.listdir(EXAMPLE_DIR)]
        json_files = [f for f in contents if f.endswith('.json')]
        for file in json_files:
            # print(f'Loading: {file}')
            with open(file) as stream:
                base = os.path.splitext(os.path.basename(file))[0]
                samples = json.load(stream)
                # print(samples)
                report = annotator.annotate_all(samples)
                with open(os.path.join(EXAMPLE_OUTDIR, base + '-output.yaml'), 'w') as stream:
                    yaml.safe_dump(report.all_outputs(), stream)
                rpt_file = os.path.join(EXAMPLE_OUTDIR, base + '-report.tsv')
                report.as_dataframe().to_csv(rpt_file, sep='\t', index=False)

    def test_annotate(self):
        annotator = SampleAnnotator()
        with open(TEST_DATA) as stream:
            test_obj = yaml.load(stream, Loader=yaml.SafeLoader)

        cumulative_df = None
        output_samples = []
        for t in test_obj.get('tests'):
            desc = t.get('description', None)
            print(f'TEST: {desc}')
            sample = t.get('sample')
            report = annotator.annotate(sample)
            print(report)
            output_samples.append(report.output)
            df = report.as_dataframe()
            # print(df)

            if 'must_pass' in t:
                assert report.passes() == t.get('must_pass')

            mbc = report.messages_by_category()
            # print(mbc)
            expected_failures = t.get('expected_failures', {})
            print(f'EF={expected_failures}')
            for category, num_expected in expected_failures.items():
                num_actual_messages = len(mbc.get(category, []))
                print(f'Expected = {num_expected} actual={num_actual_messages}')
                if isinstance(num_expected, int):
                    assert num_expected == num_actual_messages
                elif num_expected.startswith(">"):
                    assert num_actual_messages > int(num_expected.replace('>', ''))
                elif num_expected.startswith("="):
                    assert num_actual_messages == int(num_expected.replace('=', ''))
                elif str(num_expected).isdigit():
                    assert num_actual_messages == int(num_expected)
                else:
                    assert False

            if cumulative_df is None:
                cumulative_df = df
            else:
                # cumulative_df.append(df)
                cumulative_df = pd.concat([cumulative_df, df], ignore_index=True)
        cumulative_df.to_csv(REPORT_OUT, sep='\t', index=False)
        with open(SAMPLES_OUT, 'w') as stream:
            yaml.safe_dump(output_samples, stream)
