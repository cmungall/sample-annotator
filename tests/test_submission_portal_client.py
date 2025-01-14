import sys
from sample_annotator.clients.submission_portal_client import SubmissionPortalClient
import unittest
import os.path
 

#A .env file needs to be supplies in the 'inputs' folder for this.
class TestSubmissionPortalClient(unittest.TestCase):

    def test_get_submission(self):
        client = SubmissionPortalClient('inputs/.env')
        r = client.get_submission_json('353d751f-cff0-4558-9051-25a87ba00d3f')
        assert type(r) == dict

    def test_process_json_response(self):
        client = SubmissionPortalClient('inputs/.env')
        r = client.get_submission_json('353d751f-cff0-4558-9051-25a87ba00d3f')
        biosample_db_lis = client.process_json_response(r)
        assert biosample_db_lis[0][0]['samp_collec_method'] == 'Kit 6'
        assert type(biosample_db_lis[0][0]) == dict

    def test_dump_db(self):
        client = SubmissionPortalClient('inputs/.env')
        r = client.get_submission_json('353d751f-cff0-4558-9051-25a87ba00d3f')
        biosample_db_lis = client.process_json_response(r)
        for i in range(0,len(biosample_db_lis)):
            client.dump_db(biosample_db_lis[i],"output/output_" + str(i) + ".json")
        assert os.path.isfile('output/output_0.json')

        with open('output/output_0.json', "r") as f:
            lines = f.readlines()
        assert len(lines) == 11911
        

