"""优化模式不能跳过用于发布数据的关键断言。"""

import subprocess
import sys

import pytest

from download_data import ROOT


@pytest.mark.parametrize("operation", [
    "from q2_sql_analysis.run_q22 import verify_results\nverify_results([], [{'wrong': 1}], {})",
    "import pandas as pd\nfrom q3_etl_pipeline.pipeline import validate_output\nvalidate_output(None, pd.DataFrame({'quantity': [-1]}), None, None, None, 100)",
])
def test_business_validation_remains_active_in_optimized_python(operation):
    code = "try:\n" + "\n".join("    " + line for line in operation.splitlines())
    code += "\nexcept AssertionError:\n    print('invalid data rejected')\nelse:\n    raise SystemExit('invalid data accepted')\n"
    result = subprocess.run([sys.executable, "-O", "-c", code], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr or result.stdout
    assert result.stdout.strip() == "invalid data rejected"
