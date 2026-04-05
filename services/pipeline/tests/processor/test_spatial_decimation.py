"""Tests for SpatialDecimation processing step.

Validates channel selection, stride, channel range mapping,
and edge cases.
"""

from __future__ import annotations

import numpy as np
import pytest

from processor.processing_tools.processing_steps.spatial_decimation import (
    SpatialDecimation,
)

from .conftest import (
    SECTION_CHANNEL_START,
    SECTION_CHANNEL_STOP,
    SECTION_DECIMATED_CHANNELS,
    SPATIAL_DECIMATION_FACTOR,
    make_measurement,
)


class TestSpatialDecimationBasic:
    """Core channel selection behavior."""

    async def test_factor_1_no_decimation(self):
        step = SpatialDecimation(factor=1)
        values = np.arange(24 * 10, dtype=np.float64).reshape(24, 10)
        m = make_measurement(values)
        result = await step.process(m)

        assert result["values"].shape == (24, 10)
        np.testing.assert_array_equal(result["values"], values)

    async def test_factor_2_keeps_every_other(self):
        step = SpatialDecimation(factor=2)
        values = np.arange(10, dtype=np.float64).reshape(1, 10)
        m = make_measurement(values)
        result = await step.process(m)

        # Channels [0, 2, 4, 6, 8]
        np.testing.assert_array_equal(result["values"][0], [0, 2, 4, 6, 8])
        assert result["channel_count"] == 5

    async def test_factor_3_keeps_every_third(self):
        step = SpatialDecimation(factor=3)
        values = np.arange(9, dtype=np.float64).reshape(1, 9)
        m = make_measurement(values)
        result = await step.process(m)

        np.testing.assert_array_equal(result["values"][0], [0, 3, 6])
        assert result["channel_count"] == 3

    async def test_production_config(self, raw_batch):
        """Production: channels [1200:2748:3] from 5427-channel fiber."""
        step = SpatialDecimation(
            factor=SPATIAL_DECIMATION_FACTOR,
            channel_start=SECTION_CHANNEL_START,
            channel_stop=SECTION_CHANNEL_STOP,
        )
        m = make_measurement(raw_batch)
        result = await step.process(m)

        assert result["values"].shape == (24, SECTION_DECIMATED_CHANNELS)
        assert result["channel_count"] == SECTION_DECIMATED_CHANNELS


class TestSpatialDecimationChannelRange:
    """Channel start/stop with msg_channel_start offset."""

    async def test_channel_range_selection(self):
        """Select channels [3:8] from 10-channel message."""
        step = SpatialDecimation(factor=1, channel_start=3, channel_stop=8)
        values = np.arange(10, dtype=np.float64).reshape(1, 10)
        m = make_measurement(values, channel_start=0)
        result = await step.process(m)

        np.testing.assert_array_equal(result["values"][0], [3, 4, 5, 6, 7])

    async def test_channel_range_with_stride(self):
        """Select channels [2:10:3] → channels 2, 5, 8."""
        step = SpatialDecimation(factor=3, channel_start=2, channel_stop=10)
        values = np.arange(10, dtype=np.float64).reshape(1, 10)
        m = make_measurement(values, channel_start=0)
        result = await step.process(m)

        np.testing.assert_array_equal(result["values"][0], [2, 5, 8])

    async def test_nonzero_msg_channel_start(self):
        """Message starts at channel 500. Section [1200:1210] → local [700:710]."""
        step = SpatialDecimation(factor=1, channel_start=1200, channel_stop=1210)
        # 1000 channels, starting at global 500
        values = np.arange(1000, dtype=np.float64).reshape(1, 1000)
        m = make_measurement(values, channel_start=500)
        result = await step.process(m)

        # local_start = 1200 - 500 = 700, local_stop = 1210 - 500 = 710
        expected = values[0, 700:710]
        np.testing.assert_array_equal(result["values"][0], expected)
        assert result["channel_count"] == 10

    async def test_section_beyond_message_returns_none(self):
        """Section [1200:2748] but message only has 100 channels → empty selection."""
        step = SpatialDecimation(factor=3, channel_start=1200, channel_stop=2748)
        values = np.ones((24, 100))
        m = make_measurement(values, channel_start=0)
        result = await step.process(m)

        # local_start = max(0, 1200-0) = 1200, but only 100 channels
        # local_stop = min(100, 2748-0) = 100
        # slice [1200:100:3] → empty
        assert result is None

    async def test_no_channel_bounds_uses_all(self):
        step = SpatialDecimation(factor=2)
        values = np.arange(8, dtype=np.float64).reshape(1, 8)
        m = make_measurement(values)
        result = await step.process(m)

        np.testing.assert_array_equal(result["values"][0], [0, 2, 4, 6])


class TestSpatialDecimationEdgeCases:
    """Edge cases."""

    async def test_none_input_returns_none(self):
        step = SpatialDecimation(factor=3)
        assert await step.process(None) is None

    async def test_empty_channels_unchanged(self):
        step = SpatialDecimation(factor=3)
        values = np.array([]).reshape(24, 0)
        m = make_measurement(values)
        result = await step.process(m)

        assert result["values"].shape == (24, 0)

    def test_factor_zero_raises(self):
        with pytest.raises(ValueError, match="factor must be >= 1"):
            SpatialDecimation(factor=0)

    async def test_1d_input(self):
        step = SpatialDecimation(factor=2)
        values = np.arange(10, dtype=np.float64)
        m = make_measurement(values)
        result = await step.process(m)

        np.testing.assert_array_equal(result["values"], [0, 2, 4, 6, 8])

    async def test_does_not_modify_input(self, raw_batch):
        step = SpatialDecimation(
            factor=3, channel_start=SECTION_CHANNEL_START, channel_stop=SECTION_CHANNEL_STOP
        )
        original = raw_batch.copy()
        await step.process(make_measurement(raw_batch))

        np.testing.assert_array_equal(raw_batch, original)

    async def test_metadata_updated(self):
        step = SpatialDecimation(factor=3, channel_start=100, channel_stop=200)
        values = np.ones((24, 500))
        m = make_measurement(values, channel_start=0)
        result = await step.process(m)

        assert result["spatial_decimation_factor"] == 3
        assert result["channel_start"] == 100

    async def test_channel_start_metadata_without_bounds(self):
        """Without channel_start config, preserves message's channel_start."""
        step = SpatialDecimation(factor=2)
        values = np.ones((1, 10))
        m = make_measurement(values, channel_start=500)
        result = await step.process(m)

        assert result["channel_start"] == 500


class TestSpatialDecimationDeterminism:
    """Stateless step — inherently deterministic."""

    async def test_same_input_same_output(self):
        step = SpatialDecimation(factor=3, channel_start=100, channel_stop=400)
        data = np.random.default_rng(42).standard_normal((24, 500))

        r1 = await step.process(make_measurement(data.copy()))
        r2 = await step.process(make_measurement(data.copy()))

        np.testing.assert_array_equal(r1["values"], r2["values"])
