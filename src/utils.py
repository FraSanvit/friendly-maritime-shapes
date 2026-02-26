"""Utilis."""

from pathlib import Path

import numpy as np
import pandas as pd
import geopandas as gpd

from shapely.geometry import Point, Polygon
from scipy.spatial import Voronoi, cKDTree
import matplotlib.pyplot as plt

import config as cnf


REQUIRED_COLUMNS = {
    "shape_id",
    "country_id",
    "geometry",
    "shape_class",
}


def read_and_validate_shapes(path):
    """
    Read a GeoDataFrame, check required columns,
    and ensure CRS is EPSG:3035.

    Parameters
    ----------
    path : str or Path
        Path to the parquet file.

    Returns
    -------
    gpd.GeoDataFrame

    Raises
    ------
    ValueError
        If required columns are missing.
    """
    path = Path(path)
    gdf = gpd.read_parquet(path)

    missing = REQUIRED_COLUMNS - set(gdf.columns)

    if missing:
        missing_str = ", ".join(sorted(missing))
        raise ValueError(f"{path.name} is missing required columns: {missing_str}")
    
    if gdf.crs is None:
        raise ValueError(f"{path.name} has no CRS defined.")
    
    gdf = gdf.to_crs(cnf.CRS)
    
    return gdf


def get_coastal_subregions(shape, ref):
    """
    Select coastal subregions from 'shape' that border the national maritime
    polygons in 'ref'. Only countries with maritime polygons are considered.

    Parameters
    ----------
    shape : gpd.GeoDataFrame
        Sub-national shapes (no maritime shapes yet).
    ref : gpd.GeoDataFrame
        Reference shapes with national maritime polygons (shape_class == "maritime").

    Returns
    -------
    coastal_subregions : gpd.GeoDataFrame
        Subregions from 'shape' that are coastal (border maritime polygon).
    maritime_country_id : list
        List of country_ids that have maritime polygons.
    """

    # Identify countries with maritime
    maritime_country_id = ref.loc[
        ref["shape_class"] == "maritime", "country_id"
    ].unique()

    # Filter shape for these countries
    shape_filtered = shape[shape["country_id"].isin(maritime_country_id)].copy()

    # Loop over countries and select subregions that border maritime polygon
    coastal_subregions_list = []

    for country in maritime_country_id:
        # National maritime polygon
        maritime_poly = ref.loc[
            (ref["country_id"] == country) & (ref["shape_class"] == "maritime")
        ].union_all()

        # Subregions of the country
        country_shapes = shape_filtered[shape_filtered["country_id"] == country].copy()

        # Keep only subregions that touch the sea
        country_shapes["borders_maritime"] = country_shapes.geometry.apply(
            lambda g: g.intersects(maritime_poly)
        )

        bordering_subregions = country_shapes[country_shapes["borders_maritime"]].copy()

        # Optionally, mark them as ready for maritime assignment
        bordering_subregions["shape_class"] = "maritime"

        coastal_subregions_list.append(bordering_subregions)

    # Combine all countries
    coastal_subregions = gpd.GeoDataFrame(
        pd.concat(coastal_subregions_list, ignore_index=True), crs=shape.crs
    )

    return coastal_subregions, maritime_country_id


def split_maritime_by_proximity(
    shape,
    ref,
    grid_spacing=0.1,
    coast_spacing=20000,
):
    """
    Split national maritime areas and assign them to coastal subregions
    based on proximity to coastline.

    Optimization:
    - if a country has only 1 coastal subregion, assign maritime polygon directly
      to that subregion (skip grid & Voronoi).

    Parameters
    ----------
    shape : GeoDataFrame
        Custom shape file to be extended to maritime (shape_id, country_id, geometry)
    ref : GeoDataFrame
        Reference shapes with national maritime polygons (shape_class == 'maritime')
    grid_spacing : float
        Grid spacing in maritime area (degrees)
    coast_spacing : float
        Spacing of coastal sampling points (meters)

    Returns
    -------
    GeoDataFrame
        Maritime polygons per subregion
        Columns: country_id, shape_id, geometry
    """

    coastal_subregions, maritime_country_id = get_coastal_subregions(shape, ref)

    results = []

    for country in maritime_country_id:
        print(f"Processing {country}")

        # National maritime polygon (area to fill)
        maritime_poly = ref.loc[
            (ref.country_id == country) & (ref.shape_class == "maritime"),
            "geometry",
        ].union_all()

        if maritime_poly.is_empty:
            print(f"  No maritime polygon for {country}")
            continue

        # Coastal subregions for this country
        subregions = coastal_subregions[coastal_subregions.country_id == country].copy()

        if subregions.empty:
            print(f"  No coastal subregions for {country}")
            continue

        # Optimization: if only one subregion, assign directly
        if subregions.shape_id.nunique() == 1:
            shape_id = subregions.shape_id.unique()[0]
            results.append(
                {
                    "country_id": country,
                    "shape_id": shape_id,
                    "geometry": maritime_poly,
                }
            )
            print("  Only one subregion, assigned full maritime area")
            continue

        # Sample coastal points
        coastal_points = []
        coastal_shape_ids = []

        for _, row in subregions.iterrows():
            pts = sample_true_coastal_points(
                row.geometry,
                maritime_poly,
                coast_spacing,
            )
            if not pts:
                continue

            coastal_points.extend(pts)
            coastal_shape_ids.extend([row.shape_id] * len(pts))

        if not coastal_points:
            print(f"  No coastal points generated for {country}, assigning evenly")
            # fallback: assign whole maritime polygon to first subregion
            shape_id = subregions.shape_id.iloc[0]
            results.append(
                {
                    "country_id": country,
                    "shape_id": shape_id,
                    "geometry": maritime_poly,
                }
            )
            continue

        coast_coords = np.array([[p.x, p.y] for p in coastal_points])
        coast_tree = cKDTree(coast_coords)

        # Grid points inside maritime polygon
        grid_points = generate_grid_points(maritime_poly, grid_spacing)

        if len(grid_points) < 2:
            print(f"  Grid too sparse for {country}, assigning to first subregion")
            shape_id = coastal_shape_ids[0]
            results.append(
                {
                    "country_id": country,
                    "shape_id": shape_id,
                    "geometry": maritime_poly,
                }
            )
            continue

        grid_coords = np.array([[p.x, p.y] for p in grid_points])

        # Voronoi tessellation
        vor = Voronoi(grid_coords)
        vor_polys = voronoi_finite_polygons(vor)

        # Assign Voronoi cells to nearest coastal point
        for coords in vor_polys:
            poly = Polygon(coords)
            if not poly.is_valid:
                continue

            clipped = poly.intersection(maritime_poly)
            if clipped.is_empty or clipped.area == 0:
                continue

            centroid = clipped.centroid
            _, idx = coast_tree.query([centroid.x, centroid.y])

            results.append(
                {
                    "country_id": country,
                    "shape_id": coastal_shape_ids[idx],
                    "geometry": clipped,
                }
            )

    # Dissolve per subregion
    gdf = gpd.GeoDataFrame(results, crs=coastal_subregions.crs)
    gdf = gdf.dissolve(by=["country_id", "shape_id"], as_index=False)

    gdf = gdf.merge(
        shape[["shape_id", "country_id", "name", "type", "proper"]],
        on=["shape_id", "country_id"],
        how="left",
    )

    gdf["shape_class"] = "maritime"

    gdf_combined = pd.concat([shape, gdf], ignore_index=True)

    # Save as parquet
    output_path = cnf.result_shape_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    gdf_combined.to_parquet(output_path, index=False)

    # Plot the combined shapes
    plot_map(gdf)

    return gdf_combined


def plot_map(gdf, title=None):
    """
    Plot GeoDataFrame and save PNG next to the parquet result.
    """

    png_path = cnf.result_shape_path.with_suffix(".png")
    png_path.parent.mkdir(parents=True, exist_ok=True)

    color_map = {"maritime": "lightblue", "land": "steelblue"}

    fig, ax = plt.subplots(figsize=(8, 8))
    gdf.plot(
        ax=ax, color=gdf["shape_class"].map(color_map), edgecolor="white", linewidth=0.5
    )

    if title is not None:
        ax.set_title(title, fontsize=14)

    plt.savefig(png_path, dpi=300, bbox_inches="tight")
    plt.show()
    plt.close()

    return png_path


def voronoi_finite_polygons(vor):
    """Return finite Voronoi polygons from a scipy Voronoi object."""
    polygons = []
    for region in vor.regions:
        if not region or -1 in region:
            continue
        polygons.append([vor.vertices[i] for i in region])
    return polygons


def sample_true_coastal_points(subregion_geom, maritime_poly, spacing):
    """
    Sample points along the true coastline of a subregion,
    defined as boundary(subregion ∩ maritime).
    """

    coastal_area = subregion_geom.intersection(maritime_poly)

    if coastal_area.is_empty:
        return []

    boundary = coastal_area.boundary

    if boundary.geom_type == "LineString":
        lines = [boundary]
    elif boundary.geom_type == "MultiLineString":
        lines = list(boundary.geoms)
    else:
        return []

    points = []
    for line in lines:
        if line.length == 0:
            continue
        n = max(int(line.length // spacing), 1)
        for i in range(n + 1):
            points.append(line.interpolate(i / n, normalized=True))

    return points


def generate_grid_points(polygon, spacing):
    """Generate a regular grid of points inside a polygon."""
    minx, miny, maxx, maxy = polygon.bounds
    xs = np.arange(minx, maxx, spacing)
    ys = np.arange(miny, maxy, spacing)
    pts = [Point(x, y) for x in xs for y in ys]
    return [p for p in pts if p.within(polygon)]
