"""Scale step - multiply signal values by a constant factor.

Used to convert between physical units and ADC counts.
Example: DAS floatData in rad/(s*m) -> int16-equivalent ADC counts.
"""

from typing import Any, Dict, Optional

import numpy as np

from processor.processing_tools.processing_steps.base_step import ProcessingStep


class Scale(ProcessingStep):
    """Multiply signal values by a constant factor.

    Args:
        factor: Multiplication factor (e.g., 1/dataScale = 213.05)
    """

    def __init__(self, factor: float = 1.0):
        super().__init__("scale")
        self.factor = factor

    async def process(self, measurement_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if measurement_data is None:
            return None

        result = measurement_data.copy()
        values = result.get("values", [])
        if not isinstance(values, np.ndarray):
            values = np.asarray(values, dtype=np.float64)
        result["values"] = values * self.factor
        return result
