import json
import csv
from typing import Dict, List, Any
import click
from oaklib import get_adapter
from oaklib.datamodels.vocabulary import IS_A


@click.command()
@click.option("--input-file", "-i", default="gold-cache.json", help="Path to the input JSON file.")
@click.option("--output-file", "-o", default="biosamples.tsv", help="Path to the output TSV file.")
def main(input_file: str, output_file: str) -> None:
    """
    This script processes a JSON file containing biosample metadata and
    outputs a TSV file with one row per biosample and its associated projects.
    """

    adapter = get_adapter("sqlite:obo:envo")  # slowest part?!

    biome_id = "ENVO:00000428"  # Biome
    environmental_material_id = "ENVO:00010483"  # Environmental material
    abp = "ENVO:01000813"  # astronomical body part

    # Get all subclasses (descendants) of 'biome'
    biome_subclasses = adapter.descendants(biome_id, reflexive=False, predicates=[IS_A])
    biome_subclasses = list(biome_subclasses)  # Convert to a list for easier handling

    # Get all subclasses (descendants) of 'environmental material'
    environmental_material_subclasses = adapter.descendants(environmental_material_id, reflexive=False,
                                                            predicates=[IS_A])
    environmental_material_subclasses = list(environmental_material_subclasses)  # Convert to a list

    abp_subclasses = adapter.descendants(abp, reflexive=False, predicates=[IS_A])
    abp_subclasses = list(abp_subclasses)  # Convert to a list

    non_biome_non_em_abps = list(set(abp_subclasses) - set(biome_subclasses) - set(environmental_material_subclasses))

    # Load the JSON data
    with open(input_file, "r") as f:
        data: List[Dict[str, Any]] = json.load(f)

    # Open the output TSV file
    with open(output_file, "w", newline="") as f:
        # Create a CSV writer with tab delimiter
        writer = csv.writer(f, delimiter="\t")

        # Write the header row
        writer.writerow([
            "studyGoldId", "biosampleGoldId", "biosampleName", "description",
            "ecosystemPathId", "ecosystem", "ecosystemCategory", "ecosystemType", "ecosystemSubtype",
            "specificEcosystem",
            "envoBroadScaleId", "envoBroadScaleLabel", "bad_ebs",
            "envoLocalScaleId", "envoLocalScaleLabel", "bad_els",
            "envoMediumId", "envoMediumLabel", "bad_em",
            "mixsPackage",
            "ncbiTaxId", "ncbiTaxName",
            "modDate",
            "ncbiBioProjectAccession", "ncbiBioSampleAccession",
            "projectGoldId", "sraExperimentIds"
        ])

        # Iterate over the biosamples in the JSON data
        for item in data:
            study_gold_id: str = item["studyGoldId"]
            for biosample in item["biosamples"]:
                # Extract the required fields from the biosample data
                biosample_gold_id: str = biosample["biosampleGoldId"]
                biosample_name: str = biosample["biosampleName"]
                description: str = biosample["description"]

                ecosystem_path_id: int = biosample["ecosystemPathId"]
                ecosystem: str = biosample["ecosystem"]
                ecosystem_category: str = biosample["ecosystemCategory"]
                ecosystem_type: str = biosample["ecosystemType"]
                ecosystem_subtype: str = biosample["ecosystemSubtype"]
                specific_ecosystem: str = biosample["specificEcosystem"]

                envo_broad_scale_id: str = biosample["envoBroadScale"]["id"].replace("_", ":")
                envo_broad_scale_label: str = biosample["envoBroadScale"]["label"]
                bad_ebs = envo_broad_scale_id not in biome_subclasses
                envo_local_scale_id: str = biosample["envoLocalScale"]["id"].replace("_", ":")
                envo_local_scale_label: str = biosample["envoLocalScale"]["label"]
                bad_els = envo_local_scale_id not in non_biome_non_em_abps
                envo_medium_id: str = biosample["envoMedium"]["id"].replace("_", ":")
                envo_medium_label: str = biosample["envoMedium"]["label"]
                bad_em = envo_medium_id not in environmental_material_subclasses
                mixs_package: str = biosample["mixsPackage"]
                ncbi_tax_id: int = biosample["ncbiTaxId"]
                ncbi_tax_name: str = biosample["ncbiTaxName"]
                mod_date: str = biosample["modDate"]

                ncbi_bio_project_accessions = []
                ncbi_bio_sample_accessions = []
                project_gold_ids = []
                sra_experiment_ids = []

                for project in biosample["projects"]:
                    ncbi_bio_project_accessions.append(project["ncbiBioProjectAccession"])
                    ncbi_bio_sample_accessions.append(project["ncbiBioSampleAccession"])
                    project_gold_ids.append(project["projectGoldId"])
                    sra_experiment_ids.extend(project["sraExperimentIds"])

                # Join the lists into strings with a delimiter (e.g., semicolon)
                ncbi_bio_project_accessions_str = ";".join(sorted(list(set(ncbi_bio_project_accessions))))
                ncbi_bio_sample_accessions_str = ";".join(sorted(list(set(ncbi_bio_sample_accessions))))
                project_gold_ids_str = ";".join(sorted(list(set(project_gold_ids))))
                sra_experiment_ids_str = ";".join(sorted(list(set(sra_experiment_ids))))

                writer.writerow([
                    study_gold_id, biosample_gold_id, biosample_name, description,
                    ecosystem_path_id, ecosystem, ecosystem_category, ecosystem_type, ecosystem_subtype,
                    specific_ecosystem,
                    envo_broad_scale_id, envo_broad_scale_label, bad_ebs,
                    envo_local_scale_id, envo_local_scale_label, bad_els,
                    envo_medium_id, envo_medium_label, bad_em,
                    mixs_package,
                    ncbi_tax_id, ncbi_tax_name,
                    mod_date,
                    ncbi_bio_project_accessions_str,  # Write the concatenated string
                    ncbi_bio_sample_accessions_str,  # Write the concatenated string
                    project_gold_ids_str,  # Write the concatenated string
                    sra_experiment_ids_str,  # Write the concatenated string
                ])


if __name__ == "__main__":
    main()
