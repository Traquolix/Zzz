#!/usr/bin/env python3
"""
Generate channel coordinates from fiber coordinate data.

This script takes coordinate data from a fiber JSON file and formats it
for SQL insertion into the database. Optionally merges landmark labels
from a separate landmarks JSON file.

Usage:
    python generate_channel_coordinates.py fiber_data.json output.sql [landmarks.json]
"""

import json
import sys
from typing import List, Tuple, Optional

def escape_sql_string(value: str) -> str:
    """Escape a string for safe SQL insertion.

    Escapes single quotes and backslashes to prevent SQL injection.
    """
    if value is None:
        return 'NULL'
    # Escape backslashes first, then single quotes
    escaped = value.replace('\\', '\\\\').replace("'", "''")
    return escaped


def validate_identifier(value: str, field_name: str) -> str:
    """Validate that an identifier contains only safe characters.

    Allows alphanumeric, hyphens, underscores, and spaces.
    Raises ValueError if invalid characters are found.
    """
    import re
    if not re.match(r'^[\w\s\-]+$', value, re.UNICODE):
        raise ValueError(f"Invalid characters in {field_name}: {value!r}. "
                        f"Only alphanumeric, spaces, hyphens, and underscores allowed.")
    return value


def format_sql_insert(fiber_id: str, fiber_name: str,
                      coordinates: List[Tuple[float, float]],
                      landmark_labels: List[str] = None,
                      color: str = '#3b82f6') -> str:
    """Generate SQL INSERT statement with proper escaping."""
    # Validate identifiers to prevent SQL injection
    fiber_id = validate_identifier(fiber_id, 'fiber_id')
    fiber_name = validate_identifier(fiber_name, 'fiber_name')

    # Validate color format (hex color or named color)
    import re
    if not re.match(r'^#[0-9a-fA-F]{6}$|^[a-zA-Z]+$', color):
        raise ValueError(f"Invalid color format: {color!r}. Expected hex (#RRGGBB) or named color.")

    coord_str = ', '.join(f'({lon}, {lat})' if lon is not None else '(NULL, NULL)'
                          for lon, lat in coordinates)

    # Format landmark labels as SQL array with proper escaping
    if landmark_labels:
        labels_str = ', '.join(
            f"'{escape_sql_string(label)}'" if label else 'NULL'
            for label in landmark_labels
        )
        landmark_sql = f', [{labels_str}]'
    else:
        # Create array of NULLs matching coordinates length
        null_labels = ', '.join('NULL' for _ in coordinates)
        landmark_sql = f', [{null_labels}]'

    # All string values are now properly escaped
    sql = f"""-- Auto-generated cable data for {escape_sql_string(fiber_id)}
INSERT INTO sequoia.fiber_cables (fiber_id, fiber_name, channel_coordinates, landmark_labels, color) VALUES
('{escape_sql_string(fiber_id)}', '{escape_sql_string(fiber_name)}', [{coord_str}]{landmark_sql}, '{escape_sql_string(color)}');
"""
    return sql

def load_landmarks(landmarks_file: str, total_channels: int) -> Optional[List[Optional[str]]]:
    """
    Load landmarks from a separate JSON file and create an array matching channel count.

    Expected format:
    {
      "fiber_id": "carros",
      "landmarks": {
        "0": "Port - Start",
        "400": "km 1.2 - Garibaldi",
        ...
      }
    }
    """
    try:
        with open(landmarks_file, 'r') as f:
            landmark_data = json.load(f)

        # Create array of None values
        landmark_labels = [None] * total_channels

        # Fill in landmarks at specified channel indices
        landmarks = landmark_data.get('landmarks', {})
        for channel_str, label in landmarks.items():
            channel_idx = int(channel_str)
            if 0 <= channel_idx < total_channels:
                landmark_labels[channel_idx] = label
            else:
                print(f"Warning: Channel {channel_idx} out of range (0-{total_channels-1})", file=sys.stderr)

        return landmark_labels
    except FileNotFoundError:
        print(f"Warning: Landmarks file not found: {landmarks_file}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"Warning: Error loading landmarks: {e}", file=sys.stderr)
        return None

def main():
    if len(sys.argv) < 3 or len(sys.argv) > 4:
        print("Usage: python generate_channel_coordinates.py fiber_data.json output.sql [landmarks.json]")
        print("\nExamples:")
        print("  python generate_channel_coordinates.py cables/carros.json init/05_load_carros.sql")
        print("  python generate_channel_coordinates.py cables/carros.json init/05_load_carros.sql cables/carros_landmarks.json")
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = sys.argv[2]
    landmarks_file = sys.argv[3] if len(sys.argv) == 4 else None

    # Load fiber data from JSON
    with open(input_file, 'r') as f:
        data = json.load(f)

    fiber_id = data.get('fiber_id', data.get('id', 'unknown'))
    fiber_name = data.get('fiber_name', data.get('name', 'Unknown Cable'))
    color = data.get('color', '#3b82f6')

    # Use coordinates directly from the JSON - no interpolation
    if 'coordinates' not in data:
        print("Error: JSON must contain 'coordinates' key", file=sys.stderr)
        sys.exit(1)

    # Use coordinates as-is: each coordinate becomes one channel
    # Keep nulls as (NULL, NULL) for channels without GPS data
    coordinates = []
    for coord in data['coordinates']:
        if coord[0] is not None and coord[1] is not None:
            coordinates.append((float(coord[0]), float(coord[1])))
        else:
            coordinates.append((None, None))

    print(f"Using {len(coordinates)} coordinates directly from input (no interpolation)", file=sys.stderr)
    valid_count = sum(1 for c in coordinates if c[0] is not None)
    null_count = len(coordinates) - valid_count
    print(f"  Valid: {valid_count}, Null: {null_count}", file=sys.stderr)

    # Load landmark labels from separate file (if provided) or from fiber JSON
    landmark_labels = None
    if landmarks_file:
        print(f"Loading landmarks from: {landmarks_file}", file=sys.stderr)
        landmark_labels = load_landmarks(landmarks_file, len(coordinates))
        if landmark_labels:
            landmark_count = sum(1 for label in landmark_labels if label)
            print(f"  Landmarks: {landmark_count} defined", file=sys.stderr)
    else:
        # Fall back to landmark_labels in fiber JSON (for backward compatibility)
        landmark_labels = data.get('landmark_labels', None)
        if landmark_labels:
            # Validate that landmark_labels array matches coordinates length
            if len(landmark_labels) != len(coordinates):
                print(f"Warning: landmark_labels length ({len(landmark_labels)}) doesn't match coordinates length ({len(coordinates)})", file=sys.stderr)
                print("  Padding or truncating landmark_labels to match coordinates", file=sys.stderr)
                # Pad with None or truncate
                if len(landmark_labels) < len(coordinates):
                    landmark_labels = landmark_labels + [None] * (len(coordinates) - len(landmark_labels))
                else:
                    landmark_labels = landmark_labels[:len(coordinates)]

            # Count non-null landmarks
            landmark_count = sum(1 for label in landmark_labels if label)
            print(f"  Landmarks: {landmark_count} defined (from fiber JSON)", file=sys.stderr)
        else:
            print("  Landmarks: None (will use NULL array)", file=sys.stderr)

    # Generate SQL
    sql = format_sql_insert(fiber_id, fiber_name, coordinates, landmark_labels, color)

    # Write to file
    with open(output_file, 'w') as f:
        f.write(sql)

    print(f"Generated SQL written to {output_file}", file=sys.stderr)

if __name__ == '__main__':
    main()
