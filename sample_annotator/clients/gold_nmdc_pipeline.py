import io
import json
import logging
import os
import pkgutil
import re
from typing import Dict, List, Union

import jsonschema
import nmdc_schema.nmdc as nmdc
import pandas as pd
import dotenv
from sample_annotator.clients.nmdc.runtime_api_client import RuntimeApiSiteClient
from linkml_runtime.dumpers import json_dumper
from linkml_runtime.linkml_model.types import XSDDateTime

from sample_annotator.clients.gold_client import (
    ApDict,
    GoldClient,
    ProjectDict,
    SampleDict,
    StudyDict,
    JSON,
)

FILE_PATH = Union[str, bytes, os.PathLike]


logger = logging.getLogger(__name__)  # module level logger


def load_dotenv():
    env_path = dotenv.find_dotenv()
    if len(env_path) > 0:
        dotenv.load_dotenv(dotenv_path=env_path, override=True)


class GoldNMDC(GoldClient):
    def __init__(self, study_id: str) -> None:

        # construct MongoDB with study_set, biosample_set, omics_processing_set
        self.nmdc_db = nmdc.Database()

        # set the GOLD study id
        self.study_id = study_id

        # load nmdc-runtime credentials from environment
        load_dotenv()

    def _get_client(self) -> RuntimeApiSiteClient:
        env = dict(os.environ)
        return RuntimeApiSiteClient(
            env["BASE_URL"], env["SITE_ID"], env["CLIENT_ID"], env["CLIENT_SECRET"]
        )

    def _runtime_mint_api_call(
        self, request_type: str, request_url: str, schema_class: str, how_many: str
    ) -> JSON:
        client = self._get_client()
        return client.request(
            request_type,
            request_url,
            {"schema_class": {"id": schema_class}, "how_many": how_many},
        ).json()

    def project_ids_subset(
        self, path_to_subset_ids: Union[str, bytes, os.PathLike]
    ) -> List[str]:
        """List of GOLD project ids to subset the retreived dataset on.

        :return: list of sample project ids in the subset
        """
        df = pd.read_csv(path_to_subset_ids)

        # this assumes that at all times there is only one
        # column in the project_ids_subset.txt file
        return df[df.columns.values[0]].to_list()

    def validate_nmdc(
        self, file_path: Union[str, bytes, os.PathLike], database_set: str = None
    ) -> bool:
        """Validate JSON files against the NMDC Schema using the
        jsonschema library.

        :param file_path: path to input JSON file
        :param database_set: optional top level database set
            (e.g, study_set, biosample_set) that contains the data,
            defaults to None
        :return: True if no validation errors are raised, else False
        """
        nmdc_json_schema_bytes = io.BytesIO(
            pkgutil.get_data("nmdc_schema", "nmdc.schema.json")
        )
        nmdc_json_schema = json.loads(nmdc_json_schema_bytes.getvalue())

        with open(file_path, "r") as fh:
            json_data = json.load(fh)

            if database_set:
                if type(json_data) == list:
                    json_data = {f"{database_set}": json_data}
                else:
                    json_data = {f"{database_set}": [json_data]}
        try:
            jsonschema.validate(instance=json_data, schema=nmdc_json_schema)
        except jsonschema.exceptions.ValidationError as err:
            logger.error(err.message)

            return False

        return True

    def project_has_output_dict(self, read_qc_path: FILE_PATH) -> List[Dict[str, str]]:
        """Get list of dictionaries as {"projectGoldId": ["has_input_ids"]}

        :param read_qc_path: path to readQC file with input output mapping
        :return: List of dicts
        """
        with open(read_qc_path) as f:
            read_qc_array = json.load(f)

        read_qc_list = []

        for item in read_qc_array:
            has_output_dict = {}
            has_output_dict[item["was_informed_by"].replace("GOLD:", "")] = item[
                "has_input"
            ][0]
            read_qc_list.append(has_output_dict)

        project_has_output_list = {
            k: [d.get(k) for d in read_qc_list if k in d]
            for k in set().union(*read_qc_list)
        }

        return project_has_output_list

    def get_pi_dict(self, nmdc_entry: Dict[str, str]) -> Dict[str, str]:
        """Get dictionary with PI information like name, email, etc.

        :param nmdc_entry: An NMDC record like study, project, etc.
        :return: dictionary with PI information.
        """
        pi_dict = next(
            (contact for contact in nmdc_entry["contacts"] if "PI" in contact["roles"])
        )

        return pi_dict

    def mod_date_handler(self, nmdc_entry: Dict[str, str]) -> XSDDateTime:
        """Compute modDate in GOLD if it has not been populated in the database.

        :param nmdc_entry: An NMDC record like study, project, etc.
        :return: XSDDateTime formatted datetime
        """
        # use below logic to determine modDate if it is not
        # populated in GOLD
        mod_date = (
            XSDDateTime(nmdc_entry.get("addDate"))
            if nmdc_entry["addDate"]
            else None
            if nmdc_entry["modDate"] is None
            else XSDDateTime(nmdc_entry["modDate"])
        )

        return mod_date

    def field_site_parser(self, biosample_name: str) -> str:
        """Parse out field site information embedded in biosampleName.

        :param biosample_name: biosampleName field from biosample endpoint.
        :return: field site
        """
        return biosample_name.split("-", 1)[1].lstrip()

    def _processing_institute_handler(self, sequencing_centers: List[str]) -> List[str]:
        """GOLD NMDC transformation pipeline specific term handler.
        Specific to the ProcessingInstitutionEnum term.

        :param sequencing_centers: List of sequencing centers as stored in GOLD
        :return: NMDC Schema compliant processing institute names
        """
        nmdc_compliant_seq_ctr = ""
        for seq_ctr in sequencing_centers:
            if re.findall(
                r"University of California[,]? San Diego", seq_ctr, flags=re.IGNORECASE
            ):
                nmdc_compliant_seq_ctr = "UCSD"

            if re.findall(
                r"Environmental Molecular Sciences Laboratory",
                seq_ctr,
                flags=re.IGNORECASE,
            ):
                nmdc_compliant_seq_ctr = "EMSL"

            if re.findall(r"Joint Genome Institute", seq_ctr, flags=re.IGNORECASE):
                nmdc_compliant_seq_ctr = "JGI"

        return nmdc_compliant_seq_ctr

    def compute_study_set(
        self, study_data: StudyDict, minted_study_id: str, sub_port_dict: Dict
    ):
        """Compute study_set parameters to be populated from the dataset."""
        pi_dict = self.get_pi_dict(study_data)

        credit_associations = []
        if "has_credit_associations" in sub_port_dict:
            for cred_assoc in sub_port_dict["has_credit_associations"]:
                credit_associations.append(
                    nmdc.CreditAssociation(
                        applied_roles=cred_assoc.get("applied_roles")
                        if "applied_roles" in cred_assoc
                        else None,
                        applies_to_person=nmdc.PersonValue(
                            name=cred_assoc["applies_to_person"]["name"]
                            if "name" in cred_assoc["applies_to_person"]
                            else None,
                            email=cred_assoc["applies_to_person"]["email"]
                            if "email" in cred_assoc["applies_to_person"]
                            else None,
                            orcid=cred_assoc["applies_to_person"]["orcid"]
                            if "orcid" in cred_assoc["applies_to_person"]
                            else None,
                            profile_image_url=cred_assoc["applies_to_person"][
                                "profile_image_url"
                            ]
                            if "profile_image_url" in cred_assoc["applies_to_person"]
                            else None,
                        ),
                        applied_role=cred_assoc.get("applied_role")
                        if "applied_role" in cred_assoc
                        else None,
                        type=cred_assoc.get("type") if "type" in cred_assoc else None,
                    )
                )

        self.nmdc_db.study_set.append(
            nmdc.Study(
                id=minted_study_id,
                description=study_data["description"]
                if study_data["description"]
                else None,
                title=study_data["studyName"] if study_data["studyName"] else None,
                name=study_data["studyName"] if study_data["studyName"] else None,
                gold_study_identifiers="GOLD:" + study_data["studyGoldId"],
                principal_investigator=nmdc.PersonValue(
                    has_raw_value=pi_dict.get("name"),
                    name=pi_dict.get("name"),
                    email=pi_dict.get("email"),
                )
                if "name" and "email" in pi_dict
                else None,
                type="nmdc:Study",
                has_credit_associations=credit_associations,
                websites=sub_port_dict["websites"]
                if "websites" in sub_port_dict
                else None,
                doi=sub_port_dict["doi"] if "doi" in sub_port_dict else None,
            )
        )

    def compute_biosample_set(
        self,
        study_id: str,
        biosamples: List[Dict[str, Union[str, Dict]]],
        minted_biosample_ids_dict: Dict[str, str],
        minted_field_research_site_ids_dict: Dict[str, str],
        projects: List[str],
        analysis_projects: List[Dict],
    ) -> SampleDict:
        """Compute biosample parameters to be populated from the dataset."""
        for biosample in biosamples:
            try:
                mod_date = self.mod_date_handler(biosample)

                # retrieve INSDC identifier information using both projects and biosamples
                insdc_biosample_identifiers = [
                    "biosample:" + proj["ncbiBioSampleAccession"]
                    for proj in projects
                    if proj["ncbiBioSampleAccession"]
                    and proj["biosampleGoldId"] == biosample["biosampleGoldId"]
                ]

                # ENVO triad term value handling
                if biosample["envoBroadScale"] is not None:
                    env_broad_scale = nmdc.ControlledIdentifiedTermValue(
                        term=nmdc.OntologyClass(
                            id=biosample["envoBroadScale"]["id"].replace("_", ":"),
                            name=biosample["envoBroadScale"]["label"],
                        ),
                        has_raw_value=biosample["envoBroadScale"]["id"],
                    )
                else:
                    env_broad_scale = None

                if biosample["envoLocalScale"] is not None:
                    env_local_scale = nmdc.ControlledIdentifiedTermValue(
                        term=nmdc.OntologyClass(
                            id=biosample["envoLocalScale"]["id"].replace("_", ":"),
                            name=biosample["envoLocalScale"]["label"],
                        ),
                        has_raw_value=biosample["envoLocalScale"]["id"],
                    )
                else:
                    env_local_scale = None

                if biosample["envoMedium"] is not None:
                    env_medium = nmdc.ControlledIdentifiedTermValue(
                        term=nmdc.OntologyClass(
                            id=biosample["envoMedium"]["id"].replace("_", ":"),
                            name=biosample["envoMedium"]["label"],
                        ),
                        has_raw_value=biosample["envoMedium"]["id"],
                    )
                else:
                    env_medium = None

                ncbi_tax_name = (
                    biosample.get("ncbiTaxName") if biosample["ncbiTaxName"] else None
                )

                if ncbi_tax_name:
                    if biosample["ncbiTaxId"] is not None:
                        samp_taxon_id = nmdc.TextValue(
                            (
                                ncbi_tax_name
                                + " "
                                + "[NCBITaxon:"
                                + str(biosample.get("ncbiTaxId"))
                                + "]"
                            )
                        )
                else:
                    samp_taxon_id = None

                # parse site identifier from GOLD
                field_site = self.field_site_parser(biosample["biosampleName"])

                # there can be multiple IMG identifiers associated with a biosample
                img_identifiers = []
                for ap in analysis_projects:
                    if biosample["biosampleGoldId"] in ap["biosampleGoldId"]:
                        if ap["imgTaxonOid"] is not None:
                            img_identifiers.append(ap["imgTaxonOid"])
                
                self.nmdc_db.biosample_set.append(
                    nmdc.Biosample(
                        # biosample identifiers
                        id=minted_biosample_ids_dict[biosample["biosampleGoldId"]],
                        gold_biosample_identifiers="GOLD:"
                        + biosample["biosampleGoldId"],
                        insdc_biosample_identifiers=insdc_biosample_identifiers,
                        # metadata fields
                        description=biosample.get("description")
                        if biosample["description"]
                        else None,
                        name=biosample.get("biosampleName")
                        if biosample["biosampleName"]
                        else None,
                        part_of=study_id,
                        ncbi_taxonomy_name=ncbi_tax_name,
                        samp_taxon_id=samp_taxon_id,
                        samp_name=field_site if field_site else None,
                        type="nmdc:Biosample",
                        img_identifiers=img_identifiers,
                        # biosample date information
                        add_date=XSDDateTime(biosample.get("addDate"))
                        if biosample["addDate"]
                        else None,
                        collection_date=nmdc.TimestampValue(
                            has_raw_value=biosample.get("dateCollected", "")
                        )
                        if biosample["dateCollected"]
                        else None,
                        mod_date=mod_date,
                        # environment metadata fields
                        env_broad_scale=env_broad_scale,
                        env_local_scale=env_local_scale,
                        env_medium=env_medium,
                        # Earth fields
                        depth=nmdc.QuantityValue(
                            has_raw_value=biosample.get("depthInMeters"),
                            has_unit="meters",
                        )
                        if biosample["depthInMeters"]
                        else None,
                        elev=biosample.get("elevationInMeters")
                        if biosample["elevationInMeters"]
                        else None,
                        alt=nmdc.QuantityValue(
                            has_raw_value=biosample.get("altitudeInMeters"),
                            has_unit="meters",
                        )
                        if biosample["altitudeInMeters"]
                        else None,
                        subsurface_depth=nmdc.QuantityValue(
                            has_raw_value=biosample.get("subsurfaceDepthInMeters"),
                            has_unit="meters",
                        )
                        if biosample["subsurfaceDepthInMeters"]
                        else None,
                        # chemical metadata fields
                        diss_oxygen=nmdc.QuantityValue(
                            has_raw_value=biosample.get("oxygenConcentration")
                        )
                        if biosample["oxygenConcentration"]
                        else None,
                        nitrite=nmdc.QuantityValue(
                            has_raw_value=biosample.get("nitrateConcentration")
                        )
                        if biosample["nitrateConcentration"]
                        else None,
                        ph=biosample.get("ph") if biosample["ph"] else None,
                        pressure=nmdc.QuantityValue(
                            has_raw_value=biosample.get("pressure")
                        )
                        if biosample["pressure"]
                        else None,
                        # ecosystem collected from fields
                        ecosystem=biosample.get("ecosystem")
                        if biosample["ecosystem"]
                        else None,
                        ecosystem_category=biosample.get("ecosystemCategory")
                        if biosample["ecosystemCategory"]
                        else None,
                        ecosystem_subtype=biosample.get("ecosystemSubtype")
                        if biosample["ecosystemSubtype"]
                        else None,
                        ecosystem_type=biosample.get("ecosystemType")
                        if biosample["ecosystemType"]
                        else None,
                        specific_ecosystem=biosample.get("specificEcosystem")
                        if biosample["specificEcosystem"]
                        else None,
                        # collection site metadata
                        geo_loc_name=nmdc.TextValue(
                            has_raw_value=biosample.get("geoLocation")
                        )
                        if biosample["geoLocation"]
                        else None,
                        lat_lon=nmdc.GeolocationValue(
                            latitude=nmdc.DecimalDegree(
                                biosample.get("latitude")
                            ),
                            longitude=nmdc.DecimalDegree(
                                biosample.get("longitude")
                            ),
                            has_raw_value=str(biosample.get("latitude"))
                            + " "
                            + str(biosample.get("longitude"))
                        )
                        if biosample["latitude"] and biosample["longitude"]
                        else None,
                        habitat=biosample.get("habitat")
                        if biosample["habitat"]
                        else None,
                        location=biosample.get("isoCountry")
                        if biosample["isoCountry"]
                        else None,
                        # collection metadata fields
                        host_name=biosample.get("hostName")
                        if biosample["hostName"]
                        else None,
                        host_taxid=nmdc.TextValue(
                            has_raw_value=biosample.get("hostNcbiTaxid")
                        )
                        if biosample["hostNcbiTaxid"]
                        else None,
                        temp=nmdc.QuantityValue(
                            has_numeric_value=biosample.get(
                                "sampleCollectionTemperature"
                            )
                        )
                        if biosample["sampleCollectionTemperature"]
                        else None,
                        sample_collection_site=biosample.get("sampleCollectionSite")
                        if biosample["sampleCollectionSite"]
                        else biosample.get("sampleBodySite")
                        if biosample["sampleBodySite"]
                        else None,
                        collected_from=minted_field_research_site_ids_dict[
                            biosample["biosampleGoldId"]
                        ],
                    )
                )
            except Exception as e:
                logger.error(
                    f"Biosample not properly annotated: {biosample['biosampleGoldId']}\n"
                    f"Reason: {e}"
                )

    def compute_project_set(
        self,
        study_id: str,
        projects: List[Dict[str, Union[str, Dict]]],
        minted_biosample_ids_dict: Dict[str, str],
        minted_project_ids_dict: Dict[str, str],
    ) -> ProjectDict:
        """Compute sequencing project parameters to be populated from the dataset."""
        for project in projects:
            try:
                pi_dict = self.get_pi_dict(project)

                mod_date = self.mod_date_handler(project)

                read_qc_path = os.path.join(
                    os.path.dirname(os.path.abspath(__file__)),
                    "nmdc",
                    "input",
                    "EMP_soil_readQC.json",
                )

                project_has_output_dict = self.project_has_output_dict(
                    read_qc_path=read_qc_path
                )

                # create value for has_output attribute
                if project["projectGoldId"] in self.project_has_output_dict(
                    read_qc_path=read_qc_path
                ):
                    has_output = project_has_output_dict[project["projectGoldId"]]
                else:
                    # logger message indicating that has_output cannot be computed
                    # fix for warning: readQC file needs to provided for computation
                    # of this value
                    logger.warning(
                        f"readQC input output mapping file not provided for {project['projectGoldId']}"
                    )
                    has_output = None

                self.nmdc_db.omics_processing_set.append(
                    nmdc.OmicsProcessing(
                        # omics processing metadata
                        id=minted_project_ids_dict[project["projectGoldId"]],
                        name=project.get("projectName")
                        if project["projectName"]
                        else None,
                        gold_sequencing_project_identifiers="GOLD:"
                        + project["projectGoldId"]
                        if project["projectGoldId"]
                        else None,
                        ncbi_project_name=project.get("projectName")
                        if project["projectName"]
                        else None,
                        type="nmdc:OmicsProcessing",
                        has_input=minted_biosample_ids_dict[project["biosampleGoldId"]],
                        has_output=has_output,
                        part_of=study_id,
                        # omics processing date fields
                        add_date=XSDDateTime(project.get("addDate"))
                        if project["addDate"]
                        else None,
                        mod_date=mod_date,
                        principal_investigator=nmdc.PersonValue(
                            has_raw_value=pi_dict.get("name"),
                            name=pi_dict.get("name"),
                            email=pi_dict.get("email"),
                        )
                        if "name" and "email" in pi_dict
                        else None,
                        # sequencing details fields
                        omics_type=nmdc.ControlledTermValue(
                            has_raw_value=project.get("sequencingStrategy")
                        )
                        if project["sequencingStrategy"]
                        else None,
                        instrument_name=project.get("seqMethod")[0]
                        if project["seqMethod"]
                        else None,
                        processing_institution=self._processing_institute_handler(
                            project["sequencingCenters"]
                        )
                        if project["sequencingCenters"]
                        else None,
                    )
                )
            except:
                logger.error(
                    f"Omics processing set not properly annotated: {project['projectGoldId']}"
                )

    def compute_analysis_project_set(self, analysis_projects: List[str]) -> ApDict:
        """Compute analysis project parameters to be populated from the dataset."""
        # TODO: AP handling code to be revised after
        # determining which slots are actually required
        for ap in analysis_projects:
            mod_date = self.mod_date_handler(ap)

            if re.search("Metagenome Analysis", ap["apType"], re.IGNORECASE):
                self.nmdc_db.metagenome_annotation_activity_set.append(
                    nmdc.MetagenomeAnnotationActivity(
                        id="nmdc:" + ap["apGoldId"],
                        name=ap["apName"],
                        part_of="nmdc:" + self.study_id,
                        execution_resource="",
                        git_url="",
                        has_input=["nmdc:" + ap_i for ap_i in ap["projects"]],
                        has_output="nmdc:" + ap["apGoldId"],
                        type=ap["apType"],
                        started_at_time=XSDDateTime(ap["addDate"]),
                        ended_at_time=XSDDateTime(mod_date),
                        was_informed_by="",
                        gold_analysis_project_identifiers="GOLD:" + ap["apGoldId"],
                    )
                )

            if re.search("Metatranscriptome Analysis", ap["apType"], re.IGNORECASE):
                self.nmdc_db.metatranscriptome_activity_set.append(
                    nmdc.MetatranscriptomeAnnotationActivity(
                        id="nmdc:" + ap["apGoldId"],
                        name=ap["apName"],
                        part_of="nmdc:" + self.study_id,
                        execution_resource="",
                        git_url="",
                        has_input=["nmdc:" + ap_i for ap_i in ap["projects"]],
                        has_output="nmdc:" + ap["apGoldId"],
                        type=ap["apType"],
                        started_at_time=XSDDateTime(ap["addDate"]),
                        ended_at_time=XSDDateTime(mod_date),
                        was_informed_by="",
                        gold_analysis_project_identifiers="GOLD:" + ap["apGoldId"],
                    )
                )

    def transform_gold_nmdc(
        self, file_path: Union[str, bytes, os.PathLike] = None
    ) -> str:
        """Transform any dataset fetched from GOLD Database into
        NMDC Schema compliant JSON data.

        :param study_id: Gold study id
        :param file_path: optional file name argument to write JSON dump
            output to
        :return: JSON string
        """
        projects = self.fetch_projects_by_study(self.study_id)

        biosamples = self.fetch_biosamples_by_study(self.study_id)

        analysis_projects = self.fetch_analysis_projects_by_study(self.study_id)

        path_to_subset_ids = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "nmdc",
            "input",
            "project_ids_subset.txt",
        )

        projects_subset = self.project_ids_subset(path_to_subset_ids)

        if projects_subset:
            # subsetted list of projects filtered
            projects = [
                proj for proj in projects if proj["projectGoldId"] in projects_subset
            ]

            biosamples_subset = [proj["biosampleGoldId"] for proj in projects]

            # subsetted list of biosamples filtered
            biosamples = [
                samp
                for samp in biosamples
                if samp["biosampleGoldId"] in biosamples_subset
            ]

            # subsetted list of analysis projects filtered
            analysis_projects = [
                ap
                for ap in analysis_projects
                if any(e in projects_subset for e in ap["projects"])
            ]

        minted_study_id = self._runtime_mint_api_call(
            "POST", "/pids/mint", "nmdc:Study", 1
        )
        study_data = self.fetch_study(id=self.study_id)

        study_data_portal = (
            self._get_client().request("GET", f"/studies/gold:{self.study_id}").json()
        )
        self.compute_study_set(study_data, minted_study_id[0], study_data_portal)

        minted_biosample_ids = self._runtime_mint_api_call(
            "POST", "/pids/mint", "nmdc:Biosample", len(biosamples)
        )
        gold_biosample_ids = [biosample["biosampleGoldId"] for biosample in biosamples]
        minted_biosample_ids_dict = dict(zip(gold_biosample_ids, minted_biosample_ids))

        # code block ensuring that a FieldResearchSite id is associated with
        # all biosamples from the same site
        site_ids = [
            {
                biosample["biosampleGoldId"]: self.field_site_parser(
                    biosample["biosampleName"]
                ).split(" ")[0]
            }
            for biosample in biosamples
        ]
        gold_site_ids_dict = {}
        site_vals_list = []
        for site in site_ids:
            for gb, site_id in site.items():
                gold_site_ids_dict[gb] = site_id
                site_vals_list.append(site_id)
        site_vals_list = set(site_vals_list)
        minted_field_research_site_ids = self._runtime_mint_api_call(
            "POST", "/pids/mint", "nmdc:FieldResearchSite", len(site_vals_list)
        )
        site_ids_dict = dict(zip(site_vals_list, minted_field_research_site_ids))
        gold_biosample_ids = [biosample["biosampleGoldId"] for biosample in biosamples]
        minted_field_research_site_ids_dict = {
            k: site_ids_dict.get(v, v) for k, v in gold_site_ids_dict.items()
        }

        minted_project_ids = self._runtime_mint_api_call(
            "POST", "/pids/mint", "nmdc:OmicsProcessing", len(projects)
        )
        gold_project_ids = [project["projectGoldId"] for project in projects]
        minted_project_ids_dict = dict(zip(gold_project_ids, minted_project_ids))

        # refactor: nested loop to associate analysis project information with biosample
        # reason: individual API calls to analysis_projects endpoint with biosample id as
        # query parameter are expensive
        for ga in analysis_projects:
            for gb in biosamples:
                for gp_a in ga["projects"]:
                    for gp_b in gb["projects"]:
                        if gp_a == gp_b["projectGoldId"]:
                            if "biosampleGoldId" in ga:
                                ga["biosampleGoldId"].append(gb["biosampleGoldId"])
                            else:
                                ga["biosampleGoldId"] = gb["biosampleGoldId"]

        self.compute_biosample_set(
            minted_study_id[0],
            biosamples,
            minted_biosample_ids_dict,
            minted_field_research_site_ids_dict,
            projects,
            analysis_projects,
        )

        # TODO: enable if you want to pull sequencing project information from GOLD
        self.compute_project_set(
            minted_study_id[0],
            projects,
            minted_biosample_ids_dict,
            minted_project_ids_dict,
        )

        # TODO: enable if you want to pull AP information from GOLD
        # self.compute_analysis_project_set(analysis_projects)

        # dump JSON string serialization of NMDC Schema object
        json_str = json_dumper.dumps(self.nmdc_db, inject_type=False)

        # if file_path is provided then additionally write to file at path
        if file_path:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(json.loads(json_str), f, ensure_ascii=False, indent=4)

        return json_str
