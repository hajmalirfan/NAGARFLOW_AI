from sqlalchemy import Engine, Float, Numeric, inspect, text


def upgrade_legacy_depot_schema(engine: Engine) -> None:
    """Add Step 6 fields to depots created by the earlier scenario model."""
    inspector = inspect(engine)
    if "depots" not in inspector.get_table_names():
        return

    existing_columns = {column["name"] for column in inspector.get_columns("depots")}
    additions = {
        "code": "VARCHAR(50)",
        "address": "TEXT",
        "latitude": "FLOAT",
        "longitude": "FLOAT",
        "is_active": "BOOLEAN NOT NULL DEFAULT TRUE",
        "created_at": "TIMESTAMP",
        "updated_at": "TIMESTAMP",
    }
    with engine.begin() as connection:
        for column, definition in additions.items():
            if column not in existing_columns:
                connection.execute(
                    text(f"ALTER TABLE depots ADD COLUMN {column} {definition}")
                )
        connection.execute(
            text("UPDATE depots SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL")
        )
        connection.execute(
            text("UPDATE depots SET updated_at = CURRENT_TIMESTAMP WHERE updated_at IS NULL")
        )

    inspector = inspect(engine)
    has_unique_code = any(
        constraint.get("unique")
        and constraint.get("column_names") == ["code"]
        for constraint in inspector.get_unique_constraints("depots")
    ) or any(
        index.get("unique") and index.get("column_names") == ["code"]
        for index in inspector.get_indexes("depots")
    )
    if not has_unique_code:
        with engine.begin() as connection:
            connection.execute(
                text("CREATE UNIQUE INDEX uq_depots_code ON depots (code)")
            )


def upgrade_legacy_vehicle_schema(engine: Engine) -> None:
    """Make vehicles independently managed while retaining legacy records."""
    inspector = inspect(engine)
    if "vehicles" not in inspector.get_table_names():
        return

    columns = {column["name"]: column for column in inspector.get_columns("vehicles")}
    vehicle_columns = {
        "scenario_id",
        "user_id",
        "vehicle_number",
        "vehicle_type",
        "depot_id",
        "status",
        "created_at",
        "updated_at",
    }
    rebuild_sqlite_table = engine.dialect.name == "sqlite" and (
        not vehicle_columns.issubset(columns)
        or (
            "scenario_id" in columns
            and not columns["scenario_id"]["nullable"]
        )
    )
    if rebuild_sqlite_table:
        _rebuild_sqlite_vehicle_table(engine)
    else:
        _add_vehicle_columns(engine)
    _ensure_vehicle_foreign_keys(engine)

    with engine.begin() as connection:
        if "scenarios" in inspect(engine).get_table_names():
            connection.execute(
                text(
                    "UPDATE vehicles SET user_id = "
                    "(SELECT scenarios.user_id FROM scenarios "
                    "WHERE scenarios.id = vehicles.scenario_id) "
                    "WHERE user_id IS NULL AND scenario_id IS NOT NULL"
                )
            )
        connection.execute(
            text(
                "UPDATE vehicles SET status = CASE WHEN is_available "
                "THEN 'available' ELSE 'maintenance' END "
                "WHERE status IS NULL OR status = ''"
            )
        )
        connection.execute(
            text("UPDATE vehicles SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL")
        )
        connection.execute(
            text("UPDATE vehicles SET updated_at = CURRENT_TIMESTAMP WHERE updated_at IS NULL")
        )

    current_columns = {column["name"] for column in inspect(engine).get_columns("vehicles")}
    if "vehicle_number" in current_columns:
        has_unique_number = any(
            constraint.get("unique")
            and constraint.get("column_names") == ["vehicle_number"]
            for constraint in inspect(engine).get_unique_constraints("vehicles")
        ) or any(
            index.get("unique") and index.get("column_names") == ["vehicle_number"]
            for index in inspect(engine).get_indexes("vehicles")
        )
        if not has_unique_number:
            with engine.begin() as connection:
                connection.execute(
                    text("CREATE UNIQUE INDEX uq_vehicles_vehicle_number ON vehicles (vehicle_number)")
                )


def _add_vehicle_columns(engine: Engine) -> None:
    existing_columns = {column["name"] for column in inspect(engine).get_columns("vehicles")}
    capacity_type = next(
        column["type"]
        for column in inspect(engine).get_columns("vehicles")
        if column["name"] == "capacity_kg"
    )
    additions = {
        "user_id": "INTEGER",
        "vehicle_number": "VARCHAR(30)",
        "vehicle_type": "VARCHAR(50)",
        "depot_id": "INTEGER",
        "status": "VARCHAR(30) DEFAULT 'available'",
        "created_at": "TIMESTAMP",
        "updated_at": "TIMESTAMP",
    }
    if engine.dialect.name == "postgresql":
        with engine.begin() as connection:
            connection.execute(
                text("ALTER TABLE vehicles ALTER COLUMN scenario_id DROP NOT NULL")
            )
            if (
                isinstance(capacity_type, Float)
                or not isinstance(capacity_type, Numeric)
                or capacity_type.precision != 12
                or capacity_type.scale != 2
            ):
                connection.execute(
                    text(
                        "ALTER TABLE vehicles ALTER COLUMN capacity_kg "
                        "TYPE NUMERIC(12, 2) USING capacity_kg::numeric(12, 2)"
                    )
                )
    with engine.begin() as connection:
        for column, definition in additions.items():
            if column not in existing_columns:
                connection.execute(
                    text(f"ALTER TABLE vehicles ADD COLUMN {column} {definition}")
                )


def _ensure_vehicle_foreign_keys(engine: Engine) -> None:
    if engine.dialect.name != "postgresql":
        return
    foreign_keys = inspect(engine).get_foreign_keys("vehicles")
    expected = {
        "user_id": (
            "users",
            "fk_vehicles_user_id_users",
            "FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE",
        ),
        "depot_id": (
            "depots",
            "fk_vehicles_depot_id_depots",
            "FOREIGN KEY (depot_id) REFERENCES depots(id) ON DELETE RESTRICT",
        ),
    }
    with engine.begin() as connection:
        for column, (referred_table, name, definition) in expected.items():
            exists = any(
                foreign_key.get("constrained_columns") == [column]
                and foreign_key.get("referred_table") == referred_table
                for foreign_key in foreign_keys
            )
            if not exists:
                connection.execute(
                    text(f"ALTER TABLE vehicles ADD CONSTRAINT {name} {definition}")
                )
    checks = inspect(engine).get_check_constraints("vehicles")
    if not any(check.get("name") == "positive_capacity" for check in checks):
        with engine.begin() as connection:
            connection.execute(
                text(
                    "ALTER TABLE vehicles ADD CONSTRAINT positive_capacity "
                    "CHECK (capacity_kg > 0) NOT VALID"
                )
            )


def _rebuild_sqlite_vehicle_table(engine: Engine) -> None:
    from app.models.vehicle import Vehicle

    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        connection.exec_driver_sql("PRAGMA legacy_alter_table=ON")
        connection.commit()
        try:
            connection.exec_driver_sql(
                "CREATE TABLE vehicles_legacy_backup AS SELECT * FROM vehicles"
            )
            connection.exec_driver_sql("DROP TABLE vehicles")
            Vehicle.__table__.create(connection)

            old_columns = {
                row[1]
                for row in connection.exec_driver_sql(
                    "PRAGMA table_info(vehicles_legacy_backup)"
                )
            }
            target_columns = [column.name for column in Vehicle.__table__.columns]
            expressions = []
            for column in target_columns:
                if column in old_columns:
                    expressions.append(column)
                elif column == "status":
                    expressions.append(
                        "CASE WHEN is_available THEN 'available' ELSE 'maintenance' END"
                    )
                elif column in {"created_at", "updated_at"}:
                    expressions.append("CURRENT_TIMESTAMP")
                else:
                    expressions.append("NULL")
            column_list = ", ".join(target_columns)
            connection.exec_driver_sql(
                f"INSERT INTO vehicles ({column_list}) "
                f"SELECT {', '.join(expressions)} FROM vehicles_legacy_backup"
            )
            connection.exec_driver_sql("DROP TABLE vehicles_legacy_backup")
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.exec_driver_sql("PRAGMA legacy_alter_table=OFF")
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
            connection.commit()
