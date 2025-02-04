import click
import pandas as pd
import rasterio
from pyproj import Transformer

# get Alaska land coverage files from https://s3-us-west-2.amazonaws.com/mrlc/NLCD_2016_Land_Cover_AK_20200724.zip
# they are in the ERDAS IMAGINE (.img) raster dataset format
# other states have newer files in GeoTIFF format

# the "Marina Nieto-Caballero air study proposed local scale" file comes from
#   https://docs.google.com/spreadsheets/d/1QpS2ZWFDGqn_NV6YcHqI58i8bS5SjN0CxIRCeUYoxuA/edit?gid=2029591052#gid=2029591052

# NLCD Land Cover Classification Dictionary
NLCD_CLASSES = {
    11: "Open Water",
    12: "Perennial Ice/Snow",
    21: "Developed, Open Space",
    22: "Developed, Low Intensity",
    23: "Developed, Medium Intensity",
    24: "Developed, High Intensity",
    31: "Barren Land",
    41: "Deciduous Forest",
    42: "Evergreen Forest",
    43: "Mixed Forest",
    51: "Dwarf Scrub",
    52: "Shrub/Scrub",
    71: "Grassland/Herbaceous",
    72: "Sedge/Herbaceous",
    73: "Lichens",
    74: "Moss",
    81: "Pasture/Hay",
    82: "Cultivated Crops",
    90: "Woody Wetlands",
    95: "Emergent Herbaceous Wetlands"
}


def classify_land_cover(nlcd_file: str, tsv_file: str, output_file: str) -> None:
    """
    Classifies land cover types for coordinates in a TSV file using an NLCD raster.

    :param nlcd_file: Path to the NLCD raster (.img) file.
    :param tsv_file: Path to the TSV file containing coordinates.
    :param output_file: Path to save the output TSV file with classification results.
    """
    try:
        # Read input TSV file
        df = pd.read_csv(tsv_file, sep='\t')

        # Open the NLCD raster
        with rasterio.open(nlcd_file) as src:
            transformer = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True)

            # Prepare results
            results = []

            for _, row in df.iterrows():
                lon, lat = row['lon val'], row['lat val']
                sample_name = row['sample name']

                # Transform coordinates to raster CRS
                x, y = transformer.transform(lon, lat)

                # Extract NLCD land cover class
                try:
                    land_cover_value = next(src.sample([(x, y)]))[0]
                    land_cover_description = NLCD_CLASSES.get(land_cover_value, "Unknown Class")
                except StopIteration:
                    land_cover_value = None
                    land_cover_description = "No Data"

                # Store results
                results.append([sample_name, land_cover_value, land_cover_description])

        # Create DataFrame
        results_df = pd.DataFrame(results, columns=['Sample Name', 'NLCD Code', 'NLCD Description'])

        # Save to TSV
        results_df.to_csv(output_file, sep='\t', index=False)

        click.echo(f"Land cover classification completed. Results saved to '{output_file}'.")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)


@click.command()
@click.option('--nlcd-file',
              type=click.Path(exists=True),
              required=True,
              default="../downloads/NLCD_2016_Land_Cover_AK_20200724.img",
              help="Path to NLCD .img file.")
@click.option('--tsv-file',
              type=click.Path(exists=True),
              required=True,
              default="../downloads/Marina Nieto-Caballero air study proposed local scale - merged and curated (1).tsv",
              help="Path to input TSV file with coordinates.")
@click.option('--output-file',
              type=click.Path(),
              required=True,
              default="../local/nlcd_land_cover_results.tsv",
              help="Path to save the output TSV file.")
def main(nlcd_file: str, tsv_file: str, output_file: str) -> None:
    """
    CLI tool for classifying land cover using an NLCD raster and a TSV file with coordinates.
    """
    classify_land_cover(nlcd_file, tsv_file, output_file)


if __name__ == "__main__":
    main()
