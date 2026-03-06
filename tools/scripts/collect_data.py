#!/usr/bin/env python3
"""Collect DAS data samples from Kafka topics for offline experimentation.

Captures raw and/or processed data from specified fibers for a configurable
duration. Saves to NumPy format for easy analysis.

Usage:
    # Collect 2 minutes of raw carros data
    python scripts/collect_data.py --fiber carros --duration 120 --raw

    # Collect 3 minutes of processed data from all fibers
    python scripts/collect_data.py --duration 180 --processed

    # Collect both raw and processed for mathis
    python scripts/collect_data.py --fiber mathis --duration 120 --raw --processed

Requirements:
    pip install confluent-kafka numpy

Environment variables:
    KAFKA_BOOTSTRAP_SERVERS: Kafka broker address (default: localhost:9092)
    SCHEMA_REGISTRY_URL: Schema registry URL (default: http://localhost:8081)
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

try:
    from confluent_kafka import Consumer, KafkaError, KafkaException
    from confluent_kafka.schema_registry import SchemaRegistryClient
    from confluent_kafka.schema_registry.avro import AvroDeserializer
except ImportError:
    print("Error: confluent-kafka not installed.")
    print("Install with: pip install confluent-kafka")
    sys.exit(1)


class DataCollector:
    """Collects DAS data from Kafka topics."""

    def __init__(
        self,
        bootstrap_servers: str,
        schema_registry_url: str,
        fibers: list[str] | None = None,
        collect_raw: bool = True,
        collect_processed: bool = False,
    ):
        self.bootstrap_servers = bootstrap_servers
        self.schema_registry_url = schema_registry_url
        self.fibers = fibers  # None = all fibers
        self.collect_raw = collect_raw
        self.collect_processed = collect_processed

        # Data storage
        self.raw_data: dict[str, list[dict]] = defaultdict(list)
        self.processed_data: dict[str, list[dict]] = defaultdict(list)

        # Timestamps for ordering
        self.raw_timestamps: dict[str, list[int]] = defaultdict(list)
        self.processed_timestamps: dict[str, list[int]] = defaultdict(list)

        self._running = False
        self._setup_consumers()

    def _setup_consumers(self):
        """Set up Kafka consumers with Avro deserialization."""
        # Schema registry client
        sr_client = SchemaRegistryClient({"url": self.schema_registry_url})

        # Common consumer config
        base_config = {
            "bootstrap.servers": self.bootstrap_servers,
            "auto.offset.reset": "latest",  # Only collect new data
            "enable.auto.commit": True,
            "session.timeout.ms": 30000,
        }

        self.consumers = []

        if self.collect_raw:
            raw_config = base_config.copy()
            raw_config["group.id"] = f"data-collector-raw-{int(time.time())}"

            # Raw data uses simple JSON (no Avro schema)
            self.raw_consumer = Consumer(raw_config)
            self.consumers.append(("raw", self.raw_consumer))

            # Subscribe to raw topics
            if self.fibers:
                topics = [f"das.raw.{f}" for f in self.fibers]
            else:
                # Subscribe to pattern - need to list topics first
                topics = self._list_raw_topics()

            if topics:
                self.raw_consumer.subscribe(topics)
                print(f"Subscribed to raw topics: {topics}")

        if self.collect_processed:
            processed_config = base_config.copy()
            processed_config["group.id"] = f"data-collector-processed-{int(time.time())}"

            # Processed data uses Avro
            try:
                # Fetch schema from registry
                schema_str = sr_client.get_latest_version("das.processed-value").schema.schema_str
                self.processed_deserializer = AvroDeserializer(sr_client, schema_str)
            except Exception as e:
                print(f"Warning: Could not fetch Avro schema: {e}")
                print("Will attempt to deserialize as JSON")
                self.processed_deserializer = None

            self.processed_consumer = Consumer(processed_config)
            self.consumers.append(("processed", self.processed_consumer))
            self.processed_consumer.subscribe(["das.processed"])
            print("Subscribed to processed topic: das.processed")

    def _list_raw_topics(self) -> list[str]:
        """List available raw topics."""
        admin_config = {"bootstrap.servers": self.bootstrap_servers}
        temp_consumer = Consumer({**admin_config, "group.id": "topic-lister"})

        try:
            metadata = temp_consumer.list_topics(timeout=10)
            topics = [t for t in metadata.topics if t.startswith("das.raw.") and not t.endswith(".params")]
            return topics
        finally:
            temp_consumer.close()

    def _deserialize_raw(self, msg) -> dict | None:
        """Deserialize raw message (JSON format from DAS hardware)."""
        try:
            value = msg.value()
            if value is None:
                return None
            return json.loads(value.decode("utf-8"))
        except Exception as e:
            print(f"Raw deserialize error: {e}")
            return None

    def _deserialize_processed(self, msg) -> dict | None:
        """Deserialize processed message (Avro format)."""
        try:
            value = msg.value()
            if value is None:
                return None

            if self.processed_deserializer:
                return self.processed_deserializer(value, None)
            else:
                # Fallback to JSON
                return json.loads(value.decode("utf-8"))
        except Exception as e:
            print(f"Processed deserialize error: {e}")
            return None

    def collect(self, duration_seconds: float, progress_interval: float = 10.0):
        """Collect data for the specified duration."""
        self._running = True
        start_time = time.time()
        last_progress = start_time
        msg_count = {"raw": 0, "processed": 0}

        print(f"\nCollecting data for {duration_seconds} seconds...")
        print("Press Ctrl+C to stop early\n")

        try:
            while self._running and (time.time() - start_time) < duration_seconds:
                # Poll each consumer
                for topic_type, consumer in self.consumers:
                    msg = consumer.poll(timeout=0.1)

                    if msg is None:
                        continue

                    if msg.error():
                        if msg.error().code() == KafkaError._PARTITION_EOF:
                            continue
                        raise KafkaException(msg.error())

                    # Deserialize and store
                    if topic_type == "raw":
                        data = self._deserialize_raw(msg)
                        if data:
                            fiber_id = msg.topic().split(".")[-1]
                            self.raw_data[fiber_id].append(data)
                            ts = data.get("timestamp_ns", data.get("timestamp", 0))
                            self.raw_timestamps[fiber_id].append(ts)
                            msg_count["raw"] += 1

                    elif topic_type == "processed":
                        data = self._deserialize_processed(msg)
                        if data:
                            fiber_id = data.get("fiber_id", "unknown")
                            if self.fibers is None or fiber_id in self.fibers:
                                self.processed_data[fiber_id].append(data)
                                self.processed_timestamps[fiber_id].append(
                                    data.get("timestamp_ns", 0)
                                )
                                msg_count["processed"] += 1

                # Progress update
                elapsed = time.time() - start_time
                if time.time() - last_progress >= progress_interval:
                    remaining = duration_seconds - elapsed
                    print(
                        f"[{elapsed:.0f}s] Raw: {msg_count['raw']} msgs, "
                        f"Processed: {msg_count['processed']} msgs | "
                        f"{remaining:.0f}s remaining"
                    )
                    last_progress = time.time()

        except KeyboardInterrupt:
            print("\nCollection interrupted by user")

        finally:
            self._running = False
            for _, consumer in self.consumers:
                consumer.close()

        elapsed = time.time() - start_time
        print(f"\nCollection complete: {elapsed:.1f} seconds")
        print(f"  Raw messages: {msg_count['raw']}")
        print(f"  Processed messages: {msg_count['processed']}")

        return msg_count

    def stop(self):
        """Stop collection."""
        self._running = False

    def save(self, output_dir: str | Path) -> dict[str, Path]:
        """Save collected data to files.

        Returns dict mapping data type to file paths.
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        saved_files = {}

        # Save raw data
        for fiber_id, messages in self.raw_data.items():
            if not messages:
                continue

            # Convert to structured numpy arrays
            timestamps = np.array(self.raw_timestamps[fiber_id], dtype=np.int64)

            # Stack values into 2D array (samples x channels)
            values_list = [np.array(m.get("values", []), dtype=np.float32) for m in messages]

            # Handle potentially different channel counts
            if values_list:
                # Find most common channel count
                channel_counts = [len(v) for v in values_list]
                expected_channels = max(set(channel_counts), key=channel_counts.count)

                # Filter to matching sizes and stack
                valid_values = [v for v in values_list if len(v) == expected_channels]
                valid_indices = [i for i, v in enumerate(values_list) if len(v) == expected_channels]

                if valid_values:
                    values = np.stack(valid_values)
                    timestamps = timestamps[valid_indices]

                    filepath = output_dir / f"raw_{fiber_id}_{timestamp}.npz"
                    np.savez_compressed(
                        filepath,
                        values=values,
                        timestamps=timestamps,
                        fiber_id=fiber_id,
                        channel_count=expected_channels,
                        sample_count=len(valid_values),
                        metadata=json.dumps({
                            "sampling_rate_hz": messages[0].get("sampling_rate_hz", 50.0),
                            "channel_start": messages[0].get("channel_start", 0),
                        }),
                    )
                    saved_files[f"raw_{fiber_id}"] = filepath
                    print(f"Saved raw {fiber_id}: {filepath}")
                    print(f"  Shape: {values.shape} (samples x channels)")

        # Save processed data
        for fiber_id, messages in self.processed_data.items():
            if not messages:
                continue

            timestamps = np.array(self.processed_timestamps[fiber_id], dtype=np.int64)
            values_list = [np.array(m.get("values", []), dtype=np.float32) for m in messages]

            if values_list:
                # Group by section
                sections = defaultdict(list)
                section_timestamps = defaultdict(list)

                for i, m in enumerate(messages):
                    section = m.get("section", "default")
                    sections[section].append(values_list[i])
                    section_timestamps[section].append(timestamps[i])

                for section, section_values in sections.items():
                    if not section_values:
                        continue

                    # Find most common channel count for this section
                    channel_counts = [len(v) for v in section_values]
                    expected_channels = max(set(channel_counts), key=channel_counts.count)

                    valid_values = [v for v in section_values if len(v) == expected_channels]
                    valid_indices = [i for i, v in enumerate(section_values) if len(v) == expected_channels]

                    if valid_values:
                        values = np.stack(valid_values)
                        ts = np.array(section_timestamps[section], dtype=np.int64)[valid_indices]

                        # Get metadata from first message
                        first_msg = next(m for m in messages if m.get("section") == section)
                        proc_meta = first_msg.get("processing_metadata", {})

                        filepath = output_dir / f"processed_{fiber_id}_{section}_{timestamp}.npz"
                        np.savez_compressed(
                            filepath,
                            values=values,
                            timestamps=ts,
                            fiber_id=fiber_id,
                            section=section,
                            channel_count=expected_channels,
                            sample_count=len(valid_values),
                            metadata=json.dumps({
                                "sampling_rate_hz": first_msg.get("sampling_rate_hz", 10.0),
                                "channel_start": first_msg.get("channel_start", 0),
                                "model_hint": first_msg.get("model_hint"),
                                "original_sampling_rate_hz": proc_meta.get("original_sampling_rate_hz"),
                                "decimation_factor": proc_meta.get("decimation_factor"),
                            }),
                        )
                        saved_files[f"processed_{fiber_id}_{section}"] = filepath
                        print(f"Saved processed {fiber_id}/{section}: {filepath}")
                        print(f"  Shape: {values.shape} (samples x channels)")

        return saved_files


def main():
    parser = argparse.ArgumentParser(
        description="Collect DAS data samples from Kafka for offline analysis",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--fiber", "-f",
        type=str,
        action="append",
        dest="fibers",
        help="Fiber ID to collect (can specify multiple). Default: all fibers",
    )
    parser.add_argument(
        "--duration", "-d",
        type=float,
        default=120.0,
        help="Collection duration in seconds (default: 120)",
    )
    parser.add_argument(
        "--raw", "-r",
        action="store_true",
        help="Collect raw data from das.raw.* topics",
    )
    parser.add_argument(
        "--processed", "-p",
        action="store_true",
        help="Collect processed data from das.processed topic",
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default="./data/collected",
        help="Output directory for saved data (default: ./data/collected)",
    )
    parser.add_argument(
        "--kafka",
        type=str,
        default=os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"),
        help="Kafka bootstrap servers",
    )
    parser.add_argument(
        "--schema-registry",
        type=str,
        default=os.getenv("SCHEMA_REGISTRY_URL", "http://localhost:8081"),
        help="Schema registry URL",
    )

    args = parser.parse_args()

    # Default to collecting raw if neither specified
    if not args.raw and not args.processed:
        args.raw = True
        print("No data type specified, defaulting to --raw")

    print("=" * 60)
    print("DAS Data Collector")
    print("=" * 60)
    print(f"Kafka: {args.kafka}")
    print(f"Schema Registry: {args.schema_registry}")
    print(f"Fibers: {args.fibers or 'all'}")
    print(f"Duration: {args.duration}s")
    print(f"Collect raw: {args.raw}")
    print(f"Collect processed: {args.processed}")
    print(f"Output: {args.output}")
    print("=" * 60)

    collector = DataCollector(
        bootstrap_servers=args.kafka,
        schema_registry_url=args.schema_registry,
        fibers=args.fibers,
        collect_raw=args.raw,
        collect_processed=args.processed,
    )

    # Handle SIGINT gracefully
    def signal_handler(sig, frame):
        print("\nStopping collection...")
        collector.stop()

    signal.signal(signal.SIGINT, signal_handler)

    # Collect data
    collector.collect(duration_seconds=args.duration)

    # Save results
    print("\nSaving collected data...")
    saved = collector.save(args.output)

    if saved:
        print(f"\nSaved {len(saved)} files to {args.output}")
        print("\nTo load in Python:")
        print("  import numpy as np")
        print(f"  data = np.load('{list(saved.values())[0]}')")
        print("  values = data['values']  # Shape: (samples, channels)")
        print("  timestamps = data['timestamps']  # Nanosecond timestamps")
    else:
        print("\nNo data collected. Check that:")
        print("  - Kafka is running and accessible")
        print("  - DAS data is being streamed to the topics")
        print("  - The specified fibers exist")


if __name__ == "__main__":
    main()
