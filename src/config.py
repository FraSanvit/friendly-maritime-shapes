#%% Configuration file

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

scenario_name = "ehighways"

ref_shape_path = PROJECT_ROOT / f"resource/{scenario_name}/ref_shape.parquet"
custom_shape_path = PROJECT_ROOT / f"resource/{scenario_name}/shapes.parquet"
result_shape_path = PROJECT_ROOT / f"results/{scenario_name}/{scenario_name}.parquet"


