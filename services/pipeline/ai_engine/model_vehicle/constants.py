"""Constants for vehicle detection and speed estimation.

These constants are extracted from magic numbers throughout the codebase
to improve maintainability and make tuning parameters explicit.
"""

# GLRT (Generalized Likelihood Ratio Test) parameters
GLRT_EDGE_SAFETY_SAMPLES = 15  # Samples excluded at signal edges to avoid boundary effects
GLRT_DEFAULT_WINDOW = 20  # Window size for GLRT calculation

# Vehicle counting
COUNTING_STEP_SAMPLES = 250  # Step size for sliding window in counting

# Speed calculation
SPEED_CONVERSION_FACTOR = 3.6  # m/s to km/h conversion
DEFAULT_EPSILON = 1e-8  # Small value to prevent division by zero
