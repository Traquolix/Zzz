"""Tests for Scale processing step.

Validates factor application, dtype handling, edge cases, and immutability.
"""

from __future__ import annotations

import numpy as np

from processor.processing_tools.processing_steps.scale import Scale

from .conftest import make_measurement


class TestScaleBasic:
    """Core scaling behavior."""

    async def test_factor_applied_correctly(self, small_batch):
        step = Scale(factor=213.05)
        m = make_measurement(small_batch)
        result = await step.process(m)

        np.testing.assert_allclose(result["values"], small_batch * 213.05, rtol=1e-12)

    async def test_identity_factor(self, small_batch):
        step = Scale(factor=1.0)
        m = make_measurement(small_batch)
        result = await step.process(m)

        np.testing.assert_array_equal(result["values"], small_batch)

    async def test_zero_factor(self, small_batch):
        step = Scale(factor=0.0)
        m = make_measurement(small_batch)
        result = await step.process(m)

        np.testing.assert_array_equal(result["values"], np.zeros_like(small_batch))

    async def test_negative_factor(self, small_batch):
        step = Scale(factor=-1.0)
        m = make_measurement(small_batch)
        result = await step.process(m)

        np.testing.assert_array_equal(result["values"], -small_batch)

    async def test_production_factor(self, section_batch):
        """Verify production factor 213.05 on section-sized data."""
        step = Scale(factor=213.05)
        m = make_measurement(section_batch)
        result = await step.process(m)

        assert result["values"].shape == section_batch.shape
        np.testing.assert_allclose(result["values"], section_batch * 213.05, rtol=1e-12)


class TestScaleInputHandling:
    """Input type and shape handling."""

    async def test_list_input_converted_to_float64(self):
        step = Scale(factor=2.0)
        m = make_measurement(np.array([1.0, 2.0, 3.0]))
        m["values"] = [1.0, 2.0, 3.0]  # list, not ndarray
        result = await step.process(m)

        assert isinstance(result["values"], np.ndarray)
        np.testing.assert_array_equal(result["values"], [2.0, 4.0, 6.0])

    async def test_1d_input(self):
        step = Scale(factor=3.0)
        values = np.array([10.0, 20.0, 30.0])
        result = await step.process(make_measurement(values))

        np.testing.assert_array_equal(result["values"], [30.0, 60.0, 90.0])

    async def test_empty_array(self):
        step = Scale(factor=213.05)
        values = np.array([])
        result = await step.process(make_measurement(values))

        assert result["values"].size == 0

    async def test_none_input_returns_none(self):
        step = Scale(factor=213.05)
        assert await step.process(None) is None


class TestScaleImmutability:
    """Verify input data is not modified."""

    async def test_does_not_modify_input_array(self, small_batch):
        step = Scale(factor=213.05)
        original = small_batch.copy()
        m = make_measurement(small_batch)
        await step.process(m)

        np.testing.assert_array_equal(small_batch, original)

    async def test_output_is_separate_dict(self, small_batch):
        step = Scale(factor=2.0)
        m = make_measurement(small_batch)
        result = await step.process(m)

        assert result is not m

    async def test_metadata_preserved(self, small_batch):
        step = Scale(factor=2.0)
        m = make_measurement(small_batch, fiber_id="carros", sampling_rate_hz=125.0)
        result = await step.process(m)

        assert result["fiber_id"] == "carros"
        assert result["sampling_rate_hz"] == 125.0


class TestScaleDeterminism:
    """Verify deterministic output."""

    async def test_same_input_twice_identical(self, small_batch):
        step = Scale(factor=213.05)
        r1 = await step.process(make_measurement(small_batch.copy()))
        r2 = await step.process(make_measurement(small_batch.copy()))

        np.testing.assert_array_equal(r1["values"], r2["values"])


class TestScaleNumericalEdgeCases:
    """Numerical edge cases."""

    async def test_nan_propagation(self):
        step = Scale(factor=213.05)
        values = np.array([[1.0, np.nan, 3.0]])
        result = await step.process(make_measurement(values))

        assert np.isnan(result["values"][0, 1])
        np.testing.assert_allclose(result["values"][0, 0], 213.05, rtol=1e-12)

    async def test_inf_propagation(self):
        step = Scale(factor=213.05)
        values = np.array([[np.inf, -np.inf, 0.0]])
        result = await step.process(make_measurement(values))

        assert result["values"][0, 0] == np.inf
        assert result["values"][0, 1] == -np.inf
        assert result["values"][0, 2] == 0.0

    async def test_dtype_preserved_as_float64(self, small_batch):
        step = Scale(factor=213.05)
        result = await step.process(make_measurement(small_batch))

        assert result["values"].dtype == np.float64
