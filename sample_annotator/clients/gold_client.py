import logging
import os
import sys

import yaml
import json
from time import sleep
from typing import Tuple, List, Dict, Any, Union, TextIO

from diskcache import Cache
import click
import requests

from requests.auth import HTTPBasicAuth


USERPASS = Tuple[str, str]
URL = str
# JSON = Union[Dict[str, Any], List[Dict[str, Any]]]
JSON = Any
SampleDict = JSON
StudyDict = JSON
ProjectDict = JSON
ApDict = JSON

FILENAME = Union[str, bytes, os.PathLike]

CACHEDIR = "cachedir"
cache = Cache(CACHEDIR)

# this was for gold records that were known to cause the API
# to repond with a 5xx. These have currently been fixed,
# but leaving this in as a stub in case this happens again
EXCLUSION_LIST = []


@cache.memoize()
@cache.memoize()
def _fetch_url(endpoint_url, params, user, passwd) -> JSON:
    attempt = 0
    while attempt < 4:
        results = requests.get(
            endpoint_url, params=params, auth=HTTPBasicAuth(user, passwd)
        )
        logging.info(f"STATUS={results.status_code}")
        if results.status_code == 200:
            return results.json()
        else:
            logging.error(
                f"API call to {endpoint_url} failed, code={results.status_code}; attempt={attempt} [pausing]"
            )
            sleep(5**attempt)
            attempt += 1
    raise Exception(f"API call to {endpoint_url} failed after {attempt} attempts")


class GoldClient:
    """
    A wrapper for fetching from the GOLD API

    `Gold Service Docs <https://docs.google.com/document/d/1PgrFYmc7AU7Kd5Dtg-xbpAyC6ZcLw4ChFwg3bHV1JQg/edit>`_

    """

    gold_key: USERPASS = None
    url: URL = "https://gold.jgi.doe.gov/rest/nmdc"
    num_calls = 0

    def load_key(self, path: str) -> None:
        """
        Loads username/password key from a path

        Should be a one-line file with entry USER:PASS
        :param path:
        :return: username-password
        """
        with open(path) as stream:
            lines = stream.readlines()
            [user, passwd] = lines[0].strip().split(":")
            self.gold_key = user, passwd

    def _normalize_id(self, id: str) -> str:
        """
        Translates a CURIE into LocalId form

        :param id: CURIE or LocalId
        :return: LocalId
        """
        return id.replace("gold:", "")

    def _call(self, endpoint: str, params: Dict = {}) -> JSON:
        (user, passwd) = self.gold_key
        endpoint_url = f"{self.url}/{endpoint}"
        obj = _fetch_url(endpoint_url, params, user, passwd)
        self.num_calls += 1
        return obj

    def clear_cache(self) -> None:
        cache.clear()

    def fetch_projects_by_study(self, id: str) -> List[SampleDict]:
        """

        :param id: study id e.g Gs0144570
        :return: List of sample Dict objects
        """
        id = self._normalize_id(id)
        results = self._call("projects", {"studyGoldId": id})
        return results

    def fetch_biosamples_by_study(
        self, id: str, include_project=True
    ) -> List[SampleDict]:
        """
        Fetches all samples for a study

        :param id: e.g. Gs0144570
        :param include_project: if True, adds a field for the project object
        :return: List of sample Dict objects
        """
        id = self._normalize_id(id)
        if id in EXCLUSION_LIST:
            biosamples = []
        else:
            biosamples = self._call("biosamples", {"studyGoldId": id})
            if include_project:
                projects = self.fetch_projects_by_study(id)
                # weave projects in samples
                samples_by_id = {
                    sample["biosampleGoldId"]: sample for sample in biosamples
                }
                for project in projects:
                    sample_id = project["biosampleGoldId"]
                    if sample_id is None:
                        continue
                    if sample_id not in samples_by_id:
                        logging.error(f"Sample {sample_id} not not samples for {id}")
                        logging.error(f"All samples: {samples_by_id.keys()}")
                        logging.error(f"Projects: {len(projects)}")
                        logging.error(f"Project: {project}")
                        # known exceptions: Gb0096893
                        # raise Exception(f'Sample {sample_id} is not in samples for {id}')
                        continue
                    sample = samples_by_id[sample_id]
                    logging.debug(
                        f'Adding project {project["projectGoldId"]} to {sample_id}'
                    )
                    if "projects" not in sample:
                        sample["projects"] = []
                    sample["projects"].append(project)
        return biosamples

    def fetch_study(self, id: str, include_biosamples=False) -> StudyDict:
        """
        :param id: E.g. Gs0144570
        :param include_biosamples: if true, will also inject all biosamples for study
        :return:
        """
        id = self._normalize_id(id)
        logging.info(f"Fetching study: {id}")
        results = self._call("studies", {"studyGoldId": id})

        if not results:
            logging.warning(f"No study found for ID: {id}")
            return {}  # or None?

        study = results[0]
        if include_biosamples:
            study["biosamples"] = self.fetch_biosamples_by_study(id)
        return study

    def fetch_study_by_biosample_id(
        self, id: str, include_biosamples=False, directory: str = None
    ) -> StudyDict:
        """
        given a biosample ID, fetch the containing study

        :param id: E.g. Gb0011929
        :param include_biosamples: if true, will also inject all biosamples for study (including the specified sample)
        :return:
        """
        id = self._normalize_id(id)
        logging.info(f"Fetching study: {id}")
        results = self._call("studies", {"biosampleGoldId": id})
        if len(results) == 0:
            # some samples do not have studies, e.g https://gold.jgi.doe.gov/biosample?id=Gb0051032
            logging.warning(f"No study for {id}; creating a stub")
            study = {"studyGoldId": f"GsFAKE-{id}"}
        else:
            study = results[0]
        if include_biosamples:
            study["biosamples"] = self.fetch_biosamples_by_study(study["studyGoldId"])
            logging.info(f'  Fetched biosamples for {id} == {len(study["biosamples"])}')
        return study

    def fetch_studies_by_biosample_ids(
        self, ids: List[str], directory: str = None
    ) -> List[StudyDict]:
        """
        Given a list of biosample IDs, return the set of all studies that contain these

        The study objects will also include lists of biosamples, and will include samples not in the original set

        :param ids: E.g. Gb0011929, ...
        :return:
        """
        logging.info(f"Fetching {len(ids)} samples")
        biosample_to_study = {}
        studies = []
        n = 0
        for biosample_id in ids:
            n += 1
            logging.debug(
                f"{biosample_id} is {n} of {len(ids)} // TOT: {len(biosample_to_study.keys())}"
            )
            # NOTE: the logic here is intended to avoid repeated API calls
            # no longer necessary as we cache API calls to disk
            if biosample_id in biosample_to_study:
                logging.debug(
                    f"Skipping {biosample_id} as already part of {biosample_to_study[biosample_id]}"
                )
            else:
                study = self.fetch_study_by_biosample_id(
                    biosample_id, include_biosamples=True, directory=directory
                )
                logging.info(
                    f"Fetched study for {biosample_id} SAMPLES= {len(study['biosamples'])}"
                )
                for biosample in study["biosamples"]:
                    sid = biosample["biosampleGoldId"]
                    logging.info(f'Adding {sid} to {study["studyGoldId"]}')
                    biosample_to_study[sid] = study["studyGoldId"]
                studies.append(study)
        return studies

    def fetch_studies(self, ids: List[str], **kwargs) -> List[StudyDict]:
        """
        Fetches multiple studies

        :param ids:
        :param kwargs:
        :return:
        """
        logging.info(f"Fetching {len(ids)} studies")
        return [self.fetch_study(id, **kwargs) for id in ids]

    def fetch_studies_from_file(self, path: str, **kwargs) -> List[StudyDict]:
        """

        :param path:
        :param kwargs:
        :return:
        """
        ids = []
        with open(path) as file:
            for line in file:
                if line.startswith("Gs"):
                    ids.append(line.strip())
        return self.fetch_studies(ids, **kwargs)

    def fetch_biosamples_by_project(self, id: str) -> List[SampleDict]:
        """Fetch the biosample from which the sequencing project
        was generated.

        :param id: GOLD project id. Ex.: Gp0503330
        :return: List of SampleDict objects
        """
        id = self._normalize_id(id)
        results = self._call("biosamples", {"projectGoldId": id})
        return results

    def fetch_study_by_project(self, id: str) -> List[StudyDict]:
        """Fetch the study for which the sequencing project
        was performed.

        :param id: GOLD project id. Ex.: Gp0503330
        :return: List of SampleDict objects
        """
        id = self._normalize_id(id)
        results = self._call("studies", {"projectGoldId": id})
        return results

    def fetch_analysis_projects_by_study(self, id: str) -> List[ApDict]:
        """Fetch the APs for which the study dataset id is given.

        :param id: GOLD study id. Ex.: Gs0154044
        :return: List of SampleDict objects
        """
        id = self._normalize_id(id)
        results = self._call("analysis_projects", {"studyGoldId": id})
        return results
        
        

@click.group()
@click.option("-v", "--verbose", count=True)
@click.option("-q", "--quiet")
def main(verbose: int, quiet: bool):
    """Main."""
    if verbose >= 2:
        logging.basicConfig(level=logging.DEBUG)
    elif verbose == 1:
        logging.basicConfig(level=logging.INFO)
    else:
        logging.basicConfig(level=logging.WARNING)
    if quiet:
        logging.basicConfig(level=logging.ERROR)


@main.command()
@click.argument("idfile")
@click.option(
    "-d",
    "--directory",
    help="if specified, calls in iterative fashion, making one file per study in dir",
)
@click.option(
    "--output",
    "-o",
    type=click.File(mode="w"),
    default=sys.stdout,
    help="Path to output file",
)
@click.option(
    "-O", "--output-format", default="yaml", help=f"Desired output format: json or yaml"
)
@click.option(
    "--include-biosamples/--no-include-biosamples",
    default=False,
    help="if set, include full biosamples",
)
@click.option(
    "--clear-cache/--no-clear-cache",
    default=False,
    help="if set, will clear the API call cache",
)
@click.option(
    "--authentication-file",
    "-A",
    default="config/gold-key.txt",
    help="Path auth file. Contents should be user:pass",
)
def fetch_studies(
    idfile,
    directory,
    clear_cache,
    output: TextIO,
    output_format,
    authentication_file,
    **args,
):
    """
    Fetch studies from gold, given a list of either

      * GOLD biosample IDs
      * GOLD study IDs

    Cacheing to disk is used so that if an API call fails or the script stops, it can be resumed
    and continue where it left off.

    Querying the GOLD API requires a name and password. This should be encoded as USER:PASS and placed in
    a file that can be passed via the command line (-A)

    The data structure returned is a list of studies. Each study has a list of biosamples. Each
    biosample may have a project nested under it.

    Because the GOLD API doesn't return this as one payload, this script takes care of the logic
    to weave multiple API calls together.

    E.g.

    Fetch all studies where IDs are in a file:
        goldapi fetch-studies -A config/gold-key.txt tests/inputs/gold-studies-subset.tsv

    As above, save as YAML, include sample data:
        goldapi fetch-studies -O yaml -o foo.yaml --include-biosamples -A config/gold-key.txt tests/inputs/gold-studies-subset.tsv
    """
    logging.info(f"Additional args: {args}")
    gc = GoldClient()
    gc.load_key(authentication_file)
    if clear_cache:
        gc.clear_cache()
    ids = []
    with open(idfile) as file:
        for line in file:
            if line.startswith("Gs") or line.startswith("Gb"):
                ids.append(line.strip())
    if len(ids) == 0:
        raise Exception(f"No ids in {idfile}")
    study_ids = [id for id in ids if id.startswith("Gs")]
    biosample_ids = [id for id in ids if id.startswith("Gb")]
    id_type = None
    if len(study_ids) > 0:
        if len(biosample_ids) > 0:
            raise Exception(f"Cannot mix and match study and sample IDs")
        else:
            id_type = "study"
    else:
        id_type = "biosample"
    if directory and id_type == "study":
        for id in ids:
            study = gc.fetch_study(id, **args)
            logging.info(f"Retrieved {id}")
            outpath = f"{directory}/{id}.{output_format}"
            with open(outpath, "w") as stream:
                if output_format == "yaml":
                    yaml.dump(
                        study, stream=stream, default_flow_style=False, sort_keys=False
                    )
                else:
                    json.dump(study, stream, indent=2, sort_keys=True)
    else:
        if id_type == "study":
            studies = gc.fetch_studies(ids, **args)
        else:
            studies = gc.fetch_studies_by_biosample_ids(ids, directory=directory)
        logging.info(f"Retrieved {len(studies)} studies")
        with output as stream:
            if output_format == "yaml":
                yaml.dump(
                    studies, stream=stream, default_flow_style=False, sort_keys=False
                )
            else:
                json.dump(studies, stream, indent=2, sort_keys=True)
    logging.info(f"DONE. Calls = {gc.num_calls}")


if __name__ == "__main__":
    main()
