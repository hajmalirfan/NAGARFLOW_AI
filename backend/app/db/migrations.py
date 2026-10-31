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


def upgrade_legacy_storage_point_schema(engine: Engine) -> None:
    """Make storage points independently managed and retain legacy data."""
    inspector = inspect(engine)
    if "storage_points" not in inspector.get_table_names():
        return

    columns = {column["name"]: column for column in inspector.get_columns("storage_points")}
    required_columns = {
        "user_id",
        "point_code",
        "address",
        "availability_status",
        "description",
        "created_at",
        "updated_at",
    }
    rebuild_sqlite_table = engine.dialect.name == "sqlite" and (
        not required_columns.issubset(columns)
        or (
            "scenario_id" in columns
            and not columns["scenario_id"]["nullable"]
        )
    )
    if rebuild_sqlite_table:
        _rebuild_sqlite_storage_point_table(engine)
    else:
        _add_storage_point_columns(engine, columns)
    _ensure_storage_point_constraints(engine)

    with engine.begin() as connection:
        if "scenarios" in inspect(engine).get_table_names():
            connection.execute(
                text(
                    "UPDATE storage_points SET user_id = "
                    "(SELECT scenarios.user_id FROM scenarios "
                    "WHERE scenarios.id = storage_points.scenario_id) "
                    "WHERE user_id IS NULL AND scenario_id IS NOT NULL"
                )
            )
        connection.execute(
            text(
                "UPDATE storage_points SET point_code = 'LEGACY-SP-' || id "
                "WHERE point_code IS NULL OR point_code = ''"
            )
        )
        connection.execute(
            text(
                "UPDATE storage_points SET availability_status = 'available' "
                "WHERE availability_status IS NULL OR availability_status = ''"
            )
        )
        connection.execute(
            text("UPDATE storage_points SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL")
        )
        connection.execute(
            text("UPDATE storage_points SET updated_at = CURRENT_TIMESTAMP WHERE updated_at IS NULL")
        )

    if engine.dialect.name == "postgresql":
        with engine.begin() as connection:
            connection.execute(
                text("ALTER TABLE storage_points ALTER COLUMN point_code SET NOT NULL")
            )
            connection.execute(
                text(
                    "ALTER TABLE storage_points ALTER COLUMN availability_status "
                    "SET DEFAULT 'available'"
                )
            )
            connection.execute(
                text("ALTER TABLE storage_points ALTER COLUMN availability_status SET NOT NULL")
            )

    indexes = inspect(engine).get_indexes("storage_points")
    constraints = inspect(engine).get_unique_constraints("storage_points")
    has_unique_code = any(
        index.get("unique") and index.get("column_names") == ["point_code"]
        for index in indexes
    ) or any(
        constraint.get("unique") and constraint.get("column_names") == ["point_code"]
        for constraint in constraints
    )
    if not has_unique_code:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "CREATE UNIQUE INDEX uq_storage_points_point_code "
                    "ON storage_points (point_code)"
                )
            )


def _add_storage_point_columns(engine: Engine, columns: dict[str, dict]) -> None:
    existing_columns = set(columns)
    additions = {
        "user_id": "INTEGER",
        "point_code": "VARCHAR(50)",
        "address": "TEXT",
        "availability_status": "VARCHAR(30) DEFAULT 'available'",
        "description": "TEXT",
        "created_at": "TIMESTAMP",
        "updated_at": "TIMESTAMP",
    }
    if engine.dialect.name == "postgresql":
        with engine.begin() as connection:
            connection.execute(
                text("ALTER TABLE storage_points ALTER COLUMN scenario_id DROP NOT NULL")
            )
            waste_type = columns.get("waste_kg", {}).get("type")
            if (
                waste_type is not None
                and (
                    not isinstance(waste_type, Numeric)
                    or waste_type.precision != 12
                    or waste_type.scale != 2
                )
            ):
                connection.execute(
                    text(
                        "ALTER TABLE storage_points ALTER COLUMN waste_kg "
                        "TYPE NUMERIC(12, 2) USING waste_kg::numeric(12, 2)"
                    )
                )
    with engine.begin() as connection:
        for column, definition in additions.items():
            if column not in existing_columns:
                connection.execute(
                    text(f"ALTER TABLE storage_points ADD COLUMN {column} {definition}")
                )


def _ensure_storage_point_constraints(engine: Engine) -> None:
    if engine.dialect.name != "postgresql":
        return
    foreign_keys = inspect(engine).get_foreign_keys("storage_points")
    with engine.begin() as connection:
        for foreign_key in foreign_keys:
            if foreign_key.get("constrained_columns") == ["scenario_id"]:
                if foreign_key.get("options", {}).get("ondelete", "").upper() != "SET NULL":
                    constraint_name = foreign_key.get("name")
                    if constraint_name:
                        connection.execute(
                            text(
                                f"ALTER TABLE storage_points DROP CONSTRAINT {constraint_name}"
                            )
                        )
                else:
                    break
        current_foreign_keys = inspect(engine).get_foreign_keys("storage_points")
        has_scenario_fk = any(
            key.get("constrained_columns") == ["scenario_id"]
            and key.get("options", {}).get("ondelete", "").upper() == "SET NULL"
            for key in current_foreign_keys
        )
        has_user_fk = any(
            key.get("constrained_columns") == ["user_id"]
            and key.get("referred_table") == "users"
            for key in current_foreign_keys
        )
        if not has_scenario_fk:
            connection.execute(
                text(
                    "ALTER TABLE storage_points ADD CONSTRAINT "
                    "fk_storage_points_scenario_id_scenarios "
                    "FOREIGN KEY (scenario_id) REFERENCES scenarios(id) ON DELETE SET NULL"
                )
            )
        if not has_user_fk:
            connection.execute(
                text(
                    "ALTER TABLE storage_points ADD CONSTRAINT "
                    "fk_storage_points_user_id_users "
                    "FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE"
                )
            )
        checks = inspect(engine).get_check_constraints("storage_points")
        expected_checks = {
            "valid_waste_quantity": "waste_kg >= 0",
            "valid_latitude": "latitude BETWEEN -90 AND 90",
            "valid_longitude": "longitude BETWEEN -180 AND 180",
        }
        for name, expression in expected_checks.items():
            if not any(check.get("name") == name for check in checks):
                connection.execute(
                    text(
                        f"ALTER TABLE storage_points ADD CONSTRAINT {name} "
                        f"CHECK ({expression}) NOT VALID"
                    )
                )


def _rebuild_sqlite_storage_point_table(engine: Engine) -> None:
    from app.models.storage_point import StoragePoint

    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        connection.exec_driver_sql("PRAGMA legacy_alter_table=ON")
        connection.commit()
        try:
            connection.exec_driver_sql(
                "CREATE TABLE storage_points_legacy_backup AS SELECT * FROM storage_points"
            )
            connection.exec_driver_sql("DROP TABLE storage_points")
            StoragePoint.__table__.create(connection)

            old_columns = {
                row[1]
                for row in connection.exec_driver_sql(
                    "PRAGMA table_info(storage_points_legacy_backup)"
                )
            }
            target_columns = [column.name for column in StoragePoint.__table__.columns]
            expressions = []
            for column in target_columns:
                if column == "user_id":
                    if "user_id" in old_columns:
                        expressions.append(
                            "COALESCE(user_id, "
                            "(SELECT user_id FROM scenarios WHERE scenarios.id = scenario_id))"
                        )
                    else:
                        expressions.append(
                            "(SELECT user_id FROM scenarios WHERE scenarios.id = scenario_id)"
                        )
                elif column == "point_code":
                    if "point_code" in old_columns:
                        expressions.append(
                            "COALESCE(NULLIF(point_code, ''), 'LEGACY-SP-' || id)"
                        )
                    else:
                        expressions.append("'LEGACY-SP-' || id")
                elif column == "availability_status":
                    if column in old_columns:
                        expressions.append("COALESCE(availability_status, 'available')")
                    else:
                        expressions.append("'available'")
                elif column in {"created_at", "updated_at"}:
                    if column in old_columns:
                        expressions.append(f"COALESCE({column}, CURRENT_TIMESTAMP)")
                    else:
                        expressions.append("CURRENT_TIMESTAMP")
                elif column in old_columns:
                    expressions.append(column)
                else:
                    expressions.append("NULL")
            column_list = ", ".join(target_columns)
            connection.exec_driver_sql(
                f"INSERT INTO storage_points ({column_list}) "
                f"SELECT {', '.join(expressions)} FROM storage_points_legacy_backup"
            )
            connection.exec_driver_sql("DROP TABLE storage_points_legacy_backup")
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.exec_driver_sql("PRAGMA legacy_alter_table=OFF")
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
            connection.commit()
