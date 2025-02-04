import click
import osmnx as ox
import pandas as pd
import time
from typing import List, Dict, Any

# Default file paths
default_tsv_file = "../downloads/Marina Nieto-Caballero air study proposed local scale - merged and curated (1).tsv"
default_output_file = "../local/osm_all_features_results.tsv"

# Threshold for flagging uncommon features
uncommon_threshold = 0.2


def fetch_osm_features(lat: float, lon: float, dist: int = 1000) -> pd.DataFrame:
    """
    Fetch OpenStreetMap (OSM) features near a specified latitude and longitude.

    :param lat: Latitude of the location.
    :param lon: Longitude of the location.
    :param dist: Search radius in meters (default is 1000).
    :return: DataFrame containing the fetched OSM features.
    """
    tags = {
        'aeroway': True, 'amenity': True, 'barrier': True, 'boundary': True, 'building': True,
        'emergency': True, 'geological': True, 'highway': True, 'historic': True, 'landuse': True,
        'leisure': True, 'man_made': True, 'military': True, 'natural': True, 'place': True,
        'surface': True, 'tourism': True, 'water': True, 'waterway': True, 'wetland': True
    }
    return ox.features_from_point((lat, lon), tags=tags, dist=dist)


def process_osm_data(tsv_file: str, output_file: str) -> None:
    """
    Processes a TSV file with coordinates and fetches OSM features for each location.

    :param tsv_file: Path to the input TSV file.
    :param output_file: Path to save the results.
    """
    df = pd.read_csv(tsv_file, sep='\t')
    results: List[Dict[str, Any]] = []

    for idx, row in df.iterrows():
        lat, lon = row['lat val'], row['lon val']
        sample_name = row['sample name']

        click.echo(f"Processing {idx + 1}/{len(df)}: Sample '{sample_name}' at ({lat}, {lon})")

        try:
            features = fetch_osm_features(lat, lon)
            if features.empty:
                feature_info = "No features found"
            else:
                feature_info = [
                    ", ".join(
                        f"{k}: {v}" for k, v in feature.items()
                        if pd.notnull(v) and k != 'geometry' and (
                                k in ['name', 'name:en', 'old_name', 'old_name:en'] or (
                                not k.startswith('name:') and not k.startswith('old_name:')
                        )
                        )
                    )
                    for _, feature in features.iterrows()
                ]
                feature_info = feature_info if feature_info else ['No English name found']

            for info in feature_info:
                results.append({
                    'sample_name': sample_name,
                    'latitude': lat,
                    'longitude': lon,
                    'feature_info': info
                })
        except Exception as e:
            click.echo(f"Error fetching data for Sample '{sample_name}': {e}", err=True)
            results.append({
                'sample_name': sample_name,
                'latitude': lat,
                'longitude': lon,
                'feature_info': f"Error fetching data: {e}"
            })

        time.sleep(1)  # 1-second delay between requests

    results_df = pd.DataFrame(results)

    # Identify and flag uncommon features across samples
    feature_counts = results_df['feature_info'].value_counts()
    total_samples = len(df)
    dynamic_column_name = f"lt_{int(uncommon_threshold * 100)}_pct_of_samples"
    results_df[dynamic_column_name] = results_df['feature_info'].apply(
        lambda x: True if feature_counts[x] / total_samples < uncommon_threshold else False
    )

    # Save to TSV
    results_df.to_csv(output_file, sep='\t', index=False)
    click.echo(f"OSM feature extraction completed. Results saved to '{output_file}'.")


@click.command()
@click.option('--tsv-file', type=click.Path(exists=True), default=default_tsv_file, help="Path to input TSV file.")
@click.option('--output-file', type=click.Path(), default=default_output_file, help="Path to save the output TSV file.")
def main(tsv_file: str, output_file: str) -> None:
    """
    CLI tool for extracting OpenStreetMap features based on provided coordinates in a TSV file.
    """
    process_osm_data(tsv_file, output_file)


if __name__ == "__main__":
    main()
