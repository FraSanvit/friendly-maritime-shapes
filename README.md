# Friendly maritime shapes

## Overview
This repository provides Python tools to split maritime regions defined by the user into corresponding coastal subregions, based on proximity. It uses GeoPandas, Shapely, and Voronoi tessellation for flexible allocation of maritime areas. While general-purpose, one example application is the allocation of offshore wind potential.

![Plot.](/docs/fig_friendly_maritime.png "Example image.")

## User input

Create your scenario folder in `/resource/{scenario-name}`, and place your reference maritime shapefile and your custom shapefile.
In `config.py`, define your target folder (`scenario`) and specify the reference, the custom input shape and the output shape.

## Get started

```
conda env create -f requirements.yml
```

## Methodology

- **Read and validate input shapes**: Load user-defined coastal and maritime regions (GeoParquet or Shapefile). Check required columns: `shape_id`, `country_id`, `geometry`, `shape_class`.

- **Identify maritime regions per country or area**: Filter reference shapes for regions classified as maritime. Select only the countries/subregions that have maritime areas.

- **Determine coastal subregions**: Identify subregions that border the sea. Sample points along the coastline to serve as “anchors” for assignment.

- **Generate grid over maritime areas**: Create a regular grid of points over the national/area-specific maritime polygons. Grid spacing is configurable.

- **Compute Voronoi tessellation**: Build Voronoi cells from grid points to partition maritime areas. Clip cells to maritime polygon boundaries.

- **Assign maritime cells to coastal subregions**: Use proximity from Voronoi cell centroids to coastal points. Aggregate cells per subregion to create final maritime areas.

- **Save and visualize results**: Save processed GeoDataFrame as Parquet AND generate PNG maps for each scenario.

