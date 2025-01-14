import click
from pymongo import MongoClient
import pandas as pd
from typing import Optional


@click.command()
@click.option('--host', default='localhost', help='MongoDB host address')
@click.option('--port', default=27017, help='MongoDB port number')
@click.option('--db-name', default='gold_metadata', help='MongoDB database name')
@click.option('--collection-name', default='biosamples', help='MongoDB collection name')
@click.option('--output-file', default='biosamples_report.tsv', help='Output TSV file path')
@click.option('--convert-underscores/--no-convert-underscores', default=True,
              help='Convert underscores to colons in .id fields')
def export_biosamples(
        host: str,
        port: int,
        db_name: str,
        collection_name: str,
        output_file: str,
        convert_underscores: bool
) -> None:
    """
    Export specified fields from a MongoDB collection to a TSV file.

    Parameters:
    - host: MongoDB host address
    - port: MongoDB port number
    - db_name: MongoDB database name
    - collection_name: MongoDB collection name
    - output_file: Path to save the output TSV file
    - convert_underscores: Convert underscores to colons in .id fields if True
    """

    # MongoDB connection setup
    client = MongoClient(f"mongodb://{host}:{port}/")
    db = client[db_name]
    collection = db[collection_name]

    # Fields to extract
    fields_to_extract = [
        "biosampleGoldId",
        "ecosystemPathId",
        "ecosystem",
        "ecosystemCategory",
        "ecosystemType",
        "ecosystemSubtype",
        "specificEcosystem",
        "mixsPackage",
        "envoBroadScale.id",
        "envoBroadScale.label",
        "envoLocalScale.id",
        "envoLocalScale.label",
        "envoMedium.id",
        "envoMedium.label"
    ]

    # Create a projection dictionary for the query
    projection = {field: 1 for field in fields_to_extract}

    # Query the collection
    documents = collection.find({}, projection)

    # Normalize MongoDB documents to a flat structure
    data = []
    for doc in documents:
        flat_doc = {}
        for field in fields_to_extract:
            # Navigate nested fields if necessary
            parts = field.split(".")
            value = doc
            for part in parts:
                value = value.get(part, None) if isinstance(value, dict) else None

            # Convert underscores to colons if applicable
            if convert_underscores and field.endswith(".id") and isinstance(value, str):
                value = value.replace("_", ":")

            flat_doc[field] = value
        data.append(flat_doc)

    # Convert to DataFrame
    df = pd.DataFrame(data)

    # Save as TSV
    df.to_csv(output_file, sep="\t", index=False)

    click.echo(f"TSV report generated: {output_file}")


if __name__ == '__main__':
    export_biosamples()
