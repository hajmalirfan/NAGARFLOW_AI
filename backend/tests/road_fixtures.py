"""Builds tiny GeoPackage files, so road tests need no real dataset."""

import sqlite3
import struct
from pathlib import Path

Coordinates = list[tuple[float, float]]


def encode_line(coordinates: Coordinates) -> bytes:
    """A GeoPackage geometry blob: the header, then a WKB LineString."""
    header = b"GP" + bytes([0, 0x01]) + struct.pack("<i", 4326)
    values = [value for point in coordinates for value in point]
    body = struct.pack("<BII", 1, 2, len(coordinates))
    return header + body + struct.pack(f"<{len(values)}d", *values)


def write_gpkg(
    path: Path, ways: list[tuple[str, Coordinates | bytes | None, str]]
) -> Path:
    """Write ``(highway, geometry, other_tags)`` rows to a ``lines`` table.

    Coordinates are ``(longitude, latitude)``. Passing bytes or ``None``
    in place of coordinates stores them as is, for malformed rows.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE lines (highway TEXT, other_tags TEXT, geom BLOB)")
    connection.executemany(
        "INSERT INTO lines VALUES (?, ?, ?)",
        [
            (highway, tags, encode_line(geometry) if isinstance(geometry, list) else geometry)
            for highway, geometry, tags in ways
        ],
    )
    connection.commit()
    connection.close()
    return path
