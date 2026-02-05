"""Run add maritime shapes to custom shapefile."""

from utils import read_and_validate_shapes, split_maritime_by_proximity
import config as cnf


def add_maritime_shapes():
    """Add maritime shapes to custom shapes based on proximity to reference shapes."""
    ref = read_and_validate_shapes(cnf.ref_shape_path)
    shape = read_and_validate_shapes(cnf.custom_shape_path)

    split_maritime_by_proximity(
        shape,
        ref,
        grid_spacing=0.1,
        coast_spacing=20000,
    )


if __name__ == "__main__":
    add_maritime_shapes()
