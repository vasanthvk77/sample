import time
import json
from typing import Dict, Any, List, Tuple
from urllib.parse import quote_plus
from datetime import datetime

# --- SQLAlchemy Imports ---
from sqlalchemy import (
    create_engine,
    Table,
    MetaData,
    Column,
    Integer,
    String,
    Date,
    select,
    inspect,
    text,
)
from sqlalchemy.engine import Engine
from sqlalchemy.sql.sqltypes import TypeEngine


TABLE_NAME = "employee"
TRACKING_COLUMNS: List[Tuple[str, TypeEngine]] = [
    ("source_db", String(50)),
    ("source_id", String(50)),
]


def get_sqlalchemy_url(db_key: str, config: Dict[str, Any]) -> str:
    user = quote_plus(config["user"])
    password = quote_plus(config["password"])

    if db_key == "postgresql":
        return f"postgresql+psycopg2://{user}:{password}@{config['host']}:{config['port']}/{config['dbname']}"
    elif db_key == "mysql":
        return f"mysql+mysqlconnector://{user}:{password}@{config['host']}:{config['port']}/{config['dbname']}"
    elif db_key == "sqlserver":
        driver = config["driver"].replace(" ", "+")
        return f"mssql+pyodbc://{user}:{password}@{config['server']}:{config['port']}/{config['dbname']}?driver={driver}"
    elif db_key == "oracle":
        dsn = f"{config['host']}:{config.get('port', 1521)}/{config.get('sid') or config.get('service_name')}"
        return f"oracle+oracledb://{user}:{password}@{dsn}"
    elif db_key == "vertica":
        return f"vertica+vertica_python://{user}:{password}@{config['host']}:{config['port']}/{config['dbname']}"
    else:
        raise ValueError(f"Unknown database key: {db_key}")


def reflect_source_columns(engine: Engine, table_name: str) -> List[Column]:
    inspector = inspect(engine)
    try:
        columns_info = inspector.get_columns(table_name)
    except Exception as e:
        raise RuntimeError(f"Unable to introspect source table '{table_name}': {e}")

    reflected_columns: List[Column] = []
    for col in columns_info:
        name = col["name"]
        col_type = col["type"]

        # Skip the source-side id; we'll store it as source_id in destination
        if name.lower() == "id":
            continue

        # Best effort to keep nullable and length where possible
        nullable = col.get("nullable", True)

        reflected_columns.append(Column(name, col_type, nullable=nullable))

    return reflected_columns


def compile_type_for_dest(col_type: TypeEngine, dest_engine: Engine) -> str:
    # Convert the SQLAlchemy type into a dialect-specific DDL fragment for the destination
    try:
        return col_type.compile(dest_engine.dialect)  # type: ignore[attr-defined]
    except Exception:
        # Fallback to VARCHAR(255)
        return String(255).compile(dest_engine.dialect)


def ensure_column_exists(engine: Engine, table_name: str, column: Column):
    inspector = inspect(engine)
    try:
        table_columns = [c["name"].lower() for c in inspector.get_columns(table_name)]
    except Exception as e:
        # Table might not exist yet
        raise

    if column.name.lower() in table_columns:
        return

    column_type_sql = compile_type_for_dest(column.type, engine)
    dialect_name = engine.dialect.name

    if dialect_name == "mssql":
        alter_command = f"ALTER TABLE {table_name} ADD {column.name} {column_type_sql}"
    elif dialect_name == "oracle":
        alter_command = f"ALTER TABLE {table_name} ADD ({column.name} {column_type_sql})"
    else:
        alter_command = f"ALTER TABLE {table_name} ADD COLUMN {column.name} {column_type_sql}"

    with engine.connect() as connection:
        with connection.begin():
            connection.execute(text(alter_command))


def ensure_table_and_columns(
    dest_engine: Engine,
    table_name: str,
    mirrored_columns: List[Column],
):
    inspector = inspect(dest_engine)
    has_table = False
    try:
        has_table = inspector.has_table(table_name)  # type: ignore[attr-defined]
    except Exception:
        # Some dialects do not support has_table on inspector; fallback
        try:
            dest_engine.connect().execute(text(f"SELECT 1 FROM {table_name} WHERE 1=0"))
            has_table = True
        except Exception:
            has_table = False

    if not has_table:
        # Create the destination table with: id PK, mirrored columns, and tracking cols
        dest_metadata = MetaData()
        columns: List[Column] = [Column("id", Integer, primary_key=True, autoincrement=True)]

        # Avoid duplicate column names in case source already has tracking columns
        mirrored_names_lower = {c.name.lower() for c in mirrored_columns}
        for name, _type in TRACKING_COLUMNS:
            if name.lower() in mirrored_names_lower:
                mirrored_names_lower.remove(name.lower())

        for c in mirrored_columns:
            if c.name.lower() not in {tc[0] for tc in TRACKING_COLUMNS}:
                columns.append(Column(c.name, c.type, nullable=getattr(c, "nullable", True)))

        for name, _type in TRACKING_COLUMNS:
            columns.append(Column(name, _type))

        Table(table_name, dest_metadata, *columns)
        dest_metadata.create_all(dest_engine, checkfirst=True)
        return

    # If table exists, ensure every mirrored column exists; then ensure tracking cols
    # Ensure mirrored columns
    for c in mirrored_columns:
        if c.name.lower() in {"id", "source_id", "source_db"}:
            continue
        ensure_column_exists(dest_engine, table_name, c)

    # Ensure tracking columns
    for name, _type in TRACKING_COLUMNS:
        ensure_column_exists(dest_engine, table_name, Column(name, _type))


def load_config(file_path: str = "config.json") -> Dict[str, Any]:
    try:
        with open(file_path, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Error: Config file '{file_path}' not found.")
        return {}


def build_source_db_label(source_key: str) -> str:
    source_db_map = {
        "sqlserver": "sql",
        "postgresql": "postgre",
        "mysql": "mysql",
        "oracle": "oracle",
        "vertica": "vertica",
    }
    return source_db_map.get(source_key, source_key)


def normalize_row_for_insert(row_dict: Dict[str, Any]) -> Dict[str, Any]:
    normalized: Dict[str, Any] = {}
    for key, value in row_dict.items():
        if key.lower() == "id":
            normalized["source_id"] = value
            continue

        if value is None:
            normalized[key] = None
            continue

        if key.lower() in ["dob", "join_date"]:
            if isinstance(value, str):
                try:
                    normalized[key] = datetime.strptime(value, "%Y-%m-%d").date()
                except Exception:
                    normalized[key] = None
            else:
                normalized[key] = value
            continue

        # Convert other fields to string for cross-DB compatibility
        normalized[key] = str(value) if value is not None else None

    return normalized


def copy_data(
    source_key: str,
    source_config: Dict[str, Any],
    dest_key: str,
    dest_config: Dict[str, Any],
    table_name: str = TABLE_NAME,
    chunk_size: int = 5000,
):
    print(
        f"\n{'=' * 15} Starting Dynamic Data Copy: {source_key.upper()} -> {dest_key.upper()} {'=' * 15}"
    )

    source_engine = create_engine(get_sqlalchemy_url(source_key, source_config))
    dest_engine = create_engine(get_sqlalchemy_url(dest_key, dest_config))

    try:
        print("--- Step 1: Introspecting Source Schema ---")
        mirrored_columns = reflect_source_columns(source_engine, table_name)
        print(f"Found {len(mirrored_columns)} source columns to mirror (excluding 'id').")

        print("--- Step 2: Preparing Destination Schema ---")
        if dest_key == "vertica":
            # Create table if not exists with minimal shape; then add columns as needed via catalog
            dest_metadata = MetaData()
            # Try to create table with only id to ensure existence
            Table(
                table_name,
                dest_metadata,
                Column("id", Integer, primary_key=True, autoincrement=True),
            )
            dest_metadata.create_all(dest_engine, checkfirst=True)

            with dest_engine.connect() as conn:
                # Helper to check/add column in Vertica
                def vertica_has_column(col_name: str) -> bool:
                    q = text(
                        """
                        SELECT 1
                        FROM v_catalog.columns
                        WHERE table_name = :tname AND column_name = :cname
                        """
                    )
                    res = conn.execute(q, {"tname": table_name, "cname": col_name})
                    return res.fetchone() is not None

                def vertica_add_column(col_name: str, col_type: TypeEngine):
                    ddl_type = compile_type_for_dest(col_type, dest_engine)
                    conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {col_name} {ddl_type}"))

                # Ensure mirrored columns
                for col in mirrored_columns:
                    if col.name.lower() in {"id", "source_id", "source_db"}:
                        continue
                    if not vertica_has_column(col.name):
                        vertica_add_column(col.name, col.type)

                # Ensure tracking columns
                for name, _type in TRACKING_COLUMNS:
                    if not vertica_has_column(name):
                        vertica_add_column(name, _type)

        else:
            ensure_table_and_columns(dest_engine, table_name, mirrored_columns)

        print("\n--- Step 3: Transferring Data via Bulk Insert ---")
        total_rows_copied = 0
        start_time = time.monotonic()

        # Reflect source table for selecting rows
        source_metadata = MetaData()
        source_table = Table(table_name, source_metadata, autoload_with=source_engine)

        # Reflect destination table for inserting rows
        dest_metadata = MetaData()
        dest_table = Table(table_name, dest_metadata, autoload_with=dest_engine)

        with source_engine.connect() as source_conn, dest_engine.connect() as dest_conn:
            with dest_conn.begin():
                cursor = source_conn.execute(select(source_table))

                source_db_label = build_source_db_label(source_key)

                while True:
                    chunk = cursor.fetchmany(chunk_size)
                    if not chunk:
                        break

                    data_to_insert: List[Dict[str, Any]] = []
                    for row in chunk:
                        row_dict = dict(row._mapping)
                        cleaned_record = normalize_row_for_insert(row_dict)
                        cleaned_record["source_db"] = source_db_label

                        data_to_insert.append(cleaned_record)

                    if not data_to_insert:
                        continue

                    if total_rows_copied == 0:
                        print(f"Sample columns: {list(data_to_insert[0].keys())}")
                        print(f"Sample values: {list(data_to_insert[0].values())}")
                        print(f"Chunk size: {len(data_to_insert)}")

                    try:
                        dest_conn.execute(dest_table.insert(), data_to_insert)
                        total_rows_copied += len(chunk)
                        print(f"  ... Copied {total_rows_copied} rows")
                    except Exception as insert_error:
                        print(f"Insert error: {insert_error}")
                        if "dictionary update sequence element" in str(insert_error):
                            try:
                                for i, record in enumerate(data_to_insert[:5]):
                                    dest_conn.execute(dest_table.insert(), [record])
                                total_rows_copied += min(5, len(data_to_insert))
                                print("Row-by-row insert succeeded for first few records")
                            except Exception as row_error:
                                print(f"Row-by-row insert also failed: {row_error}")
                                raise insert_error
                        else:
                            raise insert_error

        duration = time.monotonic() - start_time
        print(f"\nData copy complete. Total rows copied: {total_rows_copied}")
        print(f"Total Job Time: {duration:.4f} seconds")

    except Exception as e:
        print(f"Error: {e}")

    print(f"{'=' * 15} Job Finished {'=' * 15}\n")


def select_database(prompt: str, db_keys: Dict[str, str]) -> str:
    while True:
        print(f"\n{prompt}")
        for key, name in db_keys.items():
            print(f"{key}. {name.title()}")
        choice = input("Enter your choice: ")
        if choice in db_keys:
            return db_keys[choice]
        else:
            print("Invalid choice, please try again.")


if __name__ == "__main__":
    configs = load_config()
    if not configs:
        raise SystemExit(1)

    db_keys = {"1": "postgresql", "2": "mysql", "3": "sqlserver", "4": "vertica", "5": "oracle"}

    source_db_key = select_database("Select SOURCE database (copy FROM):", db_keys)
    dest_db_key = select_database("Select DESTINATION database (copy TO):", db_keys)

    if source_db_key == dest_db_key:
        print("\nSource and Destination cannot be the same. Aborting.")
        raise SystemExit(1)

    source_config = configs.get(source_db_key)
    dest_config = configs.get(dest_db_key)

    if not source_config or not dest_config:
        print("Error: Configuration for selected databases not found.")
        raise SystemExit(1)

    copy_data(source_db_key, source_config, dest_db_key, dest_config)

