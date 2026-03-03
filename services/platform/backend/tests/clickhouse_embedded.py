"""
Embedded ClickHouse engine for integration tests.

Uses chdb (embedded ClickHouse) to provide a real SQL engine without
requiring a running ClickHouse server. This gives us:

- Real ReplacingMergeTree with FINAL semantics
- Real parameterized queries with {name:Type} syntax
- Real AggregatingMergeTree with materialized views
- Real Enum8, DateTime64, Array types
- Actual query execution (not mocked)

The ChdbClient class adapts the chdb session interface to match the
clickhouse_connect.Client interface used by apps.shared.clickhouse.
"""

import json
import re
import tempfile
import shutil

from chdb import session as chs


class ChdbQueryResult:
    """Mimics clickhouse_connect.driver.query.QueryResult."""

    def __init__(self, column_names, result_rows):
        self.column_names = column_names
        self.result_rows = result_rows

    @property
    def row_count(self):
        return len(self.result_rows)


class ChdbClient:
    """
    Adapts chdb.Session to the clickhouse_connect.Client interface.

    The app code calls:
        client.query(sql, parameters={...})
    which returns an object with .column_names and .result_rows.

    chdb uses {name:Type} ClickHouse parameterized syntax natively,
    so we pass queries through with minimal adaptation.
    """

    def __init__(self, session: chs.Session):
        self._session = session

    def query(self, sql, parameters=None, **kwargs):
        """Execute a query and return ChdbQueryResult."""
        # Convert {name:Type} parameters to chdb format
        # chdb Session.query supports params dict directly
        if parameters:
            # chdb expects params as a dict but uses different syntax
            # We need to substitute {name:Type} with actual values
            sql = self._substitute_params(sql, parameters)

        result = self._session.query(sql, "JSON")
        data = json.loads(result.bytes().decode())

        column_names = [col["name"] for col in data.get("meta", [])]
        rows = []
        for row_dict in data.get("data", []):
            row = tuple(row_dict.get(col) for col in column_names)
            rows.append(row)

        return ChdbQueryResult(column_names, rows)

    def _substitute_params(self, sql, parameters):
        """
        Replace {name:Type} placeholders with literal values.

        ClickHouse parameterized queries use {name:Type} syntax.
        Since chdb doesn't support the same parameter binding as
        clickhouse_connect's HTTP interface, we substitute directly.
        """
        def _replace(match):
            name = match.group(1)
            # Type hint is group(2), but we don't need it for substitution
            if name not in parameters:
                return match.group(0)  # Leave unreplaced

            val = parameters[name]
            return self._format_value(val)

        return re.sub(r'\{(\w+):(\w+(?:\([^)]*\))?)\}', _replace, sql)

    def _format_value(self, val):
        """Format a Python value as a ClickHouse SQL literal."""
        if val is None:
            return 'NULL'
        if isinstance(val, str):
            # Escape single quotes
            escaped = val.replace("'", "\\'")
            return f"'{escaped}'"
        if isinstance(val, (int, float)):
            return str(val)
        if isinstance(val, (list, tuple)):
            # Array literal: ['a', 'b'] -> ['a', 'b']
            items = ', '.join(self._format_value(v) for v in val)
            return f'[{items}]'
        return str(val)


class EmbeddedClickHouse:
    """
    Manages an embedded ClickHouse instance for integration tests.

    Usage:
        ch = EmbeddedClickHouse()
        ch.setup()                   # Create schema
        ch.seed_incidents([...])     # Insert test data
        client = ch.get_client()     # Get a clickhouse_connect-compatible client
        ch.teardown()                # Clean up
    """

    SCHEMA_DIR = '/sessions/sweet-bold-hamilton/mnt/SequoIA/infrastructure/clickhouse/init'

    def __init__(self):
        self._tmpdir = None
        self._session = None
        self._client = None

    def setup(self):
        """Create temp directory, init chdb session, apply schema."""
        self._tmpdir = tempfile.mkdtemp(prefix='chdb_test_')
        self._session = chs.Session(self._tmpdir)
        self._apply_schema()
        self._client = ChdbClient(self._session)

    def teardown(self):
        """Clean up temp directory."""
        if self._tmpdir:
            shutil.rmtree(self._tmpdir, ignore_errors=True)
            self._tmpdir = None
            self._session = None
            self._client = None

    def get_client(self):
        """Return a clickhouse_connect-compatible client."""
        return self._client

    def execute(self, sql):
        """Execute raw SQL (for seeding data)."""
        self._session.query(sql)

    def query_json(self, sql):
        """Execute a query and return parsed JSON result."""
        result = self._session.query(sql, "JSON")
        return json.loads(result.bytes().decode())

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _apply_schema(self):
        """Apply 01_schema.sql and 02_sampling_tables.sql."""
        self._exec_sql_file(f'{self.SCHEMA_DIR}/01_schema.sql')
        self._exec_sql_file(f'{self.SCHEMA_DIR}/02_sampling_tables.sql')

    def _exec_sql_file(self, filepath):
        """Execute a SQL file, splitting on semicolons."""
        with open(filepath) as f:
            content = f.read()

        # Remove comments
        content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
        content = re.sub(r'--[^\n]*', '', content)

        for stmt in content.split(';'):
            stmt = stmt.strip()
            if not stmt or stmt.upper().startswith('SELECT'):
                continue
            self._session.query(stmt)

    # ------------------------------------------------------------------
    # Data seeding helpers
    # ------------------------------------------------------------------

    def seed_fiber_cables(self, cables):
        """
        Insert fiber cable records.

        Args:
            cables: List of dicts with keys: fiber_id, fiber_name,
                    channel_coordinates (list of (lat, lng) tuples).
        """
        for cable in cables:
            fid = cable['fiber_id']
            fname = cable.get('fiber_name', fid.title())
            coords = cable.get('channel_coordinates', [])
            color = cable.get('color', '#3B82F6')

            # Build coordinate array literal
            coord_strs = []
            for lat, lng in coords:
                lat_s = str(lat) if lat is not None else 'NULL'
                lng_s = str(lng) if lng is not None else 'NULL'
                coord_strs.append(f'({lat_s}, {lng_s})')
            coords_literal = f'[{", ".join(coord_strs)}]'

            self._session.query(f"""
                INSERT INTO sequoia.fiber_cables (fiber_id, fiber_name, channel_coordinates, color)
                VALUES ('{fid}', '{fname}', {coords_literal}, '{color}')
            """)

    def seed_incidents(self, incidents):
        """
        Insert incident records.

        Args:
            incidents: List of dicts with keys matching fiber_incidents columns.
                Required: incident_id, fiber_id, timestamp_ns, channel_start,
                          channel_end, incident_type, severity, status
                Optional: confidence, speed_drop_percent, duration_seconds
        """
        for inc in incidents:
            confidence = inc.get('confidence', 0.9)
            speed_drop = inc.get('speed_drop_percent', 20.0)
            duration = inc.get('duration_seconds', 60)

            self._session.query(f"""
                INSERT INTO sequoia.fiber_incidents (
                    incident_id, fiber_id, timestamp_ns,
                    channel_start, channel_end,
                    incident_type, severity, confidence,
                    speed_drop_percent, duration_seconds, status
                ) VALUES (
                    '{inc["incident_id"]}',
                    '{inc["fiber_id"]}',
                    {inc["timestamp_ns"]},
                    {inc["channel_start"]},
                    {inc["channel_end"]},
                    '{inc["incident_type"]}',
                    '{inc["severity"]}',
                    {confidence},
                    {speed_drop},
                    {duration},
                    '{inc["status"]}'
                )
            """)

    def seed_speed_hires(self, records):
        """
        Insert high-res speed records.

        Args:
            records: List of dicts with keys: fiber_id, ts (ISO string or epoch),
                     ch, speed. Optional: lng, lat.
        """
        for rec in records:
            ts = rec['ts']
            lng = rec.get('lng', 'NULL')
            lat = rec.get('lat', 'NULL')
            if isinstance(lng, (int, float)):
                lng = str(lng)
            if isinstance(lat, (int, float)):
                lat = str(lat)

            self._session.query(f"""
                INSERT INTO sequoia.speed_hires (fiber_id, ts, ch, speed, lng, lat)
                VALUES (
                    '{rec["fiber_id"]}',
                    '{ts}',
                    {rec["ch"]},
                    {rec["speed"]},
                    {lng},
                    {lat}
                )
            """)

    def seed_count_hires(self, records):
        """
        Insert high-res vehicle count records.

        Args:
            records: List of dicts with keys: fiber_id, ts, ch_start, ch_end, count.
        """
        for rec in records:
            self._session.query(f"""
                INSERT INTO sequoia.count_hires (fiber_id, ts, ch_start, ch_end, count)
                VALUES (
                    '{rec["fiber_id"]}',
                    '{rec["ts"]}',
                    {rec["ch_start"]},
                    {rec["ch_end"]},
                    {rec["count"]}
                )
            """)

    def truncate_all(self):
        """Truncate all data tables (keep schema)."""
        tables = [
            'fiber_incidents', 'fiber_cables', 'fiber_danger_zones',
            'speed_hires', 'count_hires',
            'speed_1m', 'speed_1h', 'count_1m', 'count_1h',
        ]
        for t in tables:
            try:
                self._session.query(f'TRUNCATE TABLE sequoia.{t}')
            except Exception:
                pass  # Table might not exist or be a view
