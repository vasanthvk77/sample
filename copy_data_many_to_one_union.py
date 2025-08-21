import time
import json
from typing import Dict, Any, List, Tuple, Set
from urllib.parse import quote_plus
import pandas as pd

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

# Constants
TABLE_NAME = "employee"
TRACKING_COLUMNS: List[Tuple[str, TypeEngine]] = [
    ("source_db", String(50)),
    ("source_id", String(50)),
]


def get_sqlalchemy_url(db_key: str, config: Dict[str, Any]) -> str:
    """Builds the appropriate SQLAlchemy connection URL from the config parts."""
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
    """Introspects the source table and returns a list of columns (excluding 'id')."""
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
    """Convert the SQLAlchemy type into a dialect-specific DDL fragment."""
    try:
        return col_type.compile(dest_engine.dialect)
    except Exception:
        # Fallback to VARCHAR(255)
        return String(255).compile(dest_engine.dialect)


def ensure_column_exists(engine: Engine, table_name: str, column: Column):
    """Checks if a column exists and adds it if missing."""
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
    golden_schema_columns: List[Column],
):
    """Ensures destination table exists with all columns from the golden schema."""
    inspector = inspect(dest_engine)
    has_table = False
    try:
        has_table = inspector.has_table(table_name)
    except Exception:
        # Some dialects do not support has_table on inspector; fallback
        try:
            dest_engine.connect().execute(text(f"SELECT 1 FROM {table_name} WHERE 1=0"))
            has_table = True
        except Exception:
            has_table = False

    if not has_table:
        # Create the destination table with: id PK, golden schema columns, and tracking cols
        dest_metadata = MetaData()
        columns: List[Column] = [Column("id", Integer, primary_key=True, autoincrement=True)]

        # Add all golden schema columns
        for c in golden_schema_columns:
            if c.name.lower() not in {tc[0] for tc in TRACKING_COLUMNS}:
                columns.append(Column(c.name, c.type, nullable=True))  # Make nullable for union strategy

        # Add tracking columns
        for name, _type in TRACKING_COLUMNS:
            columns.append(Column(name, _type))

        Table(table_name, dest_metadata, *columns)
        dest_metadata.create_all(dest_engine, checkfirst=True)
        print(f"✅ Created new destination table with {len(columns)} columns")
        return

    # If table exists, ensure every golden schema column exists; then ensure tracking cols
    print(f"🔧 Ensuring all golden schema columns exist in destination...")
    
    # Ensure golden schema columns
    for c in golden_schema_columns:
        if c.name.lower() in {"id", "source_id", "source_db"}:
            continue
        ensure_column_exists(dest_engine, table_name, c)

    # Ensure tracking columns
    for name, _type in TRACKING_COLUMNS:
        ensure_column_exists(dest_engine, table_name, Column(name, _type))
    
    print(f"✅ Destination table schema synchronized with golden schema")


def build_source_db_label(source_key: str) -> str:
    """Maps database keys to shorter labels for tracking."""
    source_db_map = {
        "sqlserver": "sql",
        "postgresql": "postgre",
        "mysql": "mysql",
        "oracle": "oracle",
        "vertica": "vertica",
    }
    return source_db_map.get(source_key, source_key)


def normalize_row_for_insert(row_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Normalizes row data for cross-database compatibility."""
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
                    normalized[key] = pd.to_datetime(value).date()
                except Exception:
                    normalized[key] = None
            else:
                normalized[key] = value
            continue

        # Convert other fields to string for cross-DB compatibility
        normalized[key] = str(value) if value is not None else None

    return normalized


def create_union_dataframe(source_dataframes: List[Tuple[str, pd.DataFrame]], golden_schema_columns: List[str]) -> pd.DataFrame:
    """
    Creates a unified DataFrame that preserves all columns from all sources.
    Rows from sources missing certain columns will have NULL values for those columns.
    """
    print(f"\n--- Creating Union DataFrame with Golden Schema ---")
    print(f"Golden schema columns: {golden_schema_columns}")
    
    union_dfs = []
    
    for source_key, source_df in source_dataframes:
        print(f"Processing {source_key.upper()} with {len(source_df)} rows...")
        
        # Create a copy of the source DataFrame
        processed_df = source_df.copy()
        
        # Add source_db and source_id columns
        processed_df["source_db"] = build_source_db_label(source_key)
        processed_df["source_id"] = processed_df["id"] if "id" in processed_df.columns else None
        
        # Remove the 'id' column as it will be auto-generated in destination
        if "id" in processed_df.columns:
            processed_df = processed_df.drop(columns=["id"])
        
        # Ensure all golden schema columns exist (add NULL columns for missing ones)
        for col in golden_schema_columns:
            if col not in processed_df.columns:
                print(f"   ... Adding missing column '{col}' with NULL values for {source_key.upper()}")
                processed_df[col] = None
        
        # Reorder columns to match golden schema + tracking columns
        final_columns = golden_schema_columns + ["source_db", "source_id"]
        processed_df = processed_df.reindex(columns=final_columns)
        
        print(f"   ... Final columns for {source_key.upper()}: {list(processed_df.columns)}")
        union_dfs.append(processed_df)
    
    # Combine all DataFrames
    if union_dfs:
        union_df = pd.concat(union_dfs, ignore_index=True)
        print(f"✅ Union DataFrame created with {len(union_df)} total rows")
        print(f"✅ Union DataFrame columns: {list(union_df.columns)}")
        return union_df
    else:
        return pd.DataFrame()


def copy_from_many_to_one_union(
    source_keys: List[str],
    all_configs: Dict,
    dest_key: str,
    dest_config: Dict,
    table_name: str = TABLE_NAME,
):
    """
    Copies data from multiple source databases using a UNION schema strategy.
    Creates a "golden schema" that includes ALL columns from ALL sources.
    """
    print(f"\n{'='*15} Starting Union Schema Many-to-One Data Aggregation {'='*15}")

    # --- Step 1: Discover Golden Schema from All Sources ---
    print("\n--- Step 1: Discovering Golden Schema from All Sources ---")
    
    golden_schema_columns: Set[str] = set()
    source_dataframes: List[Tuple[str, pd.DataFrame]] = []
    
    for source_key in source_keys:
        print(f"Connecting to source: {source_key.upper()}...")
        try:
            source_config = all_configs[source_key]
            source_engine = create_engine(get_sqlalchemy_url(source_key, source_config))

            # Introspect the source table schema
            mirrored_columns = reflect_source_columns(source_engine, table_name)
            source_column_names = [col.name for col in mirrored_columns]
            
            # Add all columns to golden schema (UNION strategy)
            golden_schema_columns.update(source_column_names)
            
            print(f"   ... Found {len(mirrored_columns)} columns in {source_key.upper()}")
            print(f"   ... Columns: {source_column_names}")

            with source_engine.connect() as conn:
                source_df = pd.read_sql_table(table_name, conn)
                print(f"   ... Extracted {len(source_df)} rows from {source_key.upper()}.")
                
                # Store the DataFrame with its source key for later processing
                source_dataframes.append((source_key, source_df))

        except Exception as e:
            print(f"❌ Could not extract data from {source_key}. Error: {e}")
            continue

    if not source_dataframes:
        print("No data was extracted from any source. Aborting.")
        return

    # Convert set to sorted list for consistent ordering
    golden_schema_columns = sorted(list(golden_schema_columns))
    
    print(f"\n--- Step 2: Golden Schema Analysis ---")
    print(f"Golden Schema (Union of all source columns): {golden_schema_columns}")
    print(f"Total unique columns across all sources: {len(golden_schema_columns)}")
    print(f"Sources processed: {len(source_dataframes)}")

    # --- Step 3: Prepare Destination Schema with Golden Schema ---
    print(f"\n--- Step 3: Preparing Destination Schema: {dest_key.upper()} ---")
    try:
        dest_engine = create_engine(get_sqlalchemy_url(dest_key, dest_config))

        # Create representative columns from the golden schema
        representative_columns = []
        for col_name in golden_schema_columns:
            # Find the first occurrence of this column to get its type
            for source_key, _ in source_dataframes:
                try:
                    source_config = all_configs[source_key]
                    source_engine = create_engine(get_sqlalchemy_url(source_key, source_config))
                    source_cols = reflect_source_columns(source_engine, table_name)
                    for col in source_cols:
                        if col.name == col_name:
                            representative_columns.append(col)
                            break
                    else:
                        continue
                    break
                except Exception:
                    continue
            else:
                # If we can't find the column type, use String(255) as fallback
                representative_columns.append(Column(col_name, String(255), nullable=True))

        if dest_key == "vertica":
            print("🔧 Special handling for Vertica database...")
            # Create table if not exists with minimal shape
            dest_metadata = MetaData()
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

                # Ensure all golden schema columns
                for col in representative_columns:
                    if col.name.lower() in {"id", "source_id", "source_db"}:
                        continue
                    if not vertica_has_column(col.name):
                        vertica_add_column(col.name, col.type)

                # Ensure tracking columns
                for name, _type in TRACKING_COLUMNS:
                    if not vertica_has_column(name):
                        vertica_add_column(name, _type)

                # Get current row count to show we're preserving data
                result = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
                count = result.fetchone()[0]
                print(f"✅ Existing table preserved. Current row count: {count}")

        else:
            ensure_table_and_columns(dest_engine, table_name, representative_columns)

        # --- Step 4: Create Union DataFrame ---
        print(f"\n--- Step 4: Creating Union DataFrame ---")
        union_df = create_union_dataframe(source_dataframes, golden_schema_columns)
        
        if union_df.empty:
            print("No data to insert. Aborting.")
            return

        # --- Step 5: Process and Clean Data ---
        print(f"\n--- Step 5: Processing and Cleaning Data ---")
        
        # Convert DataFrame to list of dictionaries for SQLAlchemy insert
        print("🔧 Converting DataFrame to list of dictionaries...")
        data_to_insert = union_df.to_dict(orient="records")
        print(f"✅ Conversion complete. Data type: {type(data_to_insert)}")

        # Clean and validate the data
        print("🔧 Cleaning and validating data...")
        cleaned_data = []
        for i, record in enumerate(data_to_insert):
            if i < 3:  # Debug first 3 records
                print(f"Processing record {i+1}: {record}")

            cleaned_record = normalize_row_for_insert(record)
            cleaned_data.append(cleaned_record)

            if i < 3:  # Debug first 3 records
                print(f"Cleaned record {i+1}: {cleaned_record}")

        data_to_insert = cleaned_data
        print(f"✅ Data cleaned and validated.")

        # --- Step 6: Load Data into Destination ---
        print(f"\n--- Step 6: Loading Data into Destination: {dest_key.upper()} ---")
        start_time = time.monotonic()

        # Reflect destination table for inserting rows
        dest_metadata = MetaData()
        dest_table = Table(table_name, dest_metadata, autoload_with=dest_engine)

        with dest_engine.connect() as connection:
            print(f"🚀 [SQLAlchemy]: Executing bulk INSERT for {len(data_to_insert)} records")
            try:
                with connection.begin() as transaction:
                    print(f"About to execute insert with {len(data_to_insert)} records")
                    print(f"Table columns: {[col.name for col in dest_table.columns]}")
                    print(f"Data columns: {list(data_to_insert[0].keys()) if data_to_insert else 'No data'}")

                    # Execute the insert
                    connection.execute(dest_table.insert(), data_to_insert)
                    print("✅ [SQLAlchemy]: Bulk insert complete.")

            except Exception as insert_error:
                print(f"❌ Insert error details: {insert_error}")
                print(f"Error type: {type(insert_error)}")
                print(f"Error message: {str(insert_error)}")

                # Check if this is the specific error we're looking for
                if "dictionary update sequence element" in str(insert_error):
                    print("🔍 This appears to be the dictionary update sequence error!")
                    print("Let's try row-by-row insert...")

                    try:
                        print("Trying row-by-row insert...")
                        for i, record in enumerate(data_to_insert[:5]):  # Try first 5 records
                            print(f"Inserting record {i+1}: {record}")
                            connection.execute(dest_table.insert(), [record])
                        print("✅ Row-by-row insert successful for first 5 records")
                    except Exception as row_error:
                        print(f"❌ Row-by-row insert also failed: {row_error}")

                raise insert_error

        duration = time.monotonic() - start_time
        print(f"\n✅ Data load complete.")
        print(f"⏱️   Total Load Time: {duration:.4f} seconds")

    except Exception as e:
        print(f"❌ An error occurred during the load process: {e}")

    print(f"{'='*15} Job Finished {'='*15}\n")


# --- Main execution block ---
def load_config(file_path: str = "config.json") -> Dict[str, Any]:
    try:
        with open(file_path, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Error: Config file '{file_path}' not found.")
        return {}


if __name__ == "__main__":
    configs = load_config()
    if not configs:
        raise SystemExit(1)

    db_keys = {"1": "postgresql", "2": "mysql", "3": "sqlserver", "4": "vertica", "5": "oracle"}

    # --- Logic to select multiple source databases ---
    source_choices = []
    print("\nPlease select one or more SOURCE databases (where to copy FROM).")
    print("Enter numbers separated by commas (e.g., 1,2,4) or type 'all'.")
    for key, name in db_keys.items():
        print(f"{key}. {name.title()}")

    user_input = input("Enter your choice(s): ").lower()

    if user_input == "all":
        source_choices = list(db_keys.values())
    else:
        # Split the input string by the comma to get individual choices
        chosen_keys = [key.strip() for key in user_input.split(",")]
        for key in chosen_keys:
            if key in db_keys:
                source_choices.append(db_keys[key])
            else:
                print(f"Warning: Invalid choice '{key}' ignored.")

    if not source_choices:
        print("No valid sources selected. Aborting.")
        raise SystemExit(1)

    print(f"\nYou have selected the following sources: {', '.join(s.upper() for s in source_choices)}")

    # --- Logic to select a single destination database ---
    dest_db_key = ""
    while True:
        print("\nPlease select the single DESTINATION database (where to copy TO).")
        # Display only the databases that were NOT selected as a source
        available_destinations = {k: v for k, v in db_keys.items() if v not in source_choices}

        if not available_destinations:
            print("No available destinations left. Aborting.")
            raise SystemExit(1)

        for key, name in available_destinations.items():
            print(f"{key}. {name.title()}")

        choice = input("Enter your choice: ")
        if choice in available_destinations:
            dest_db_key = available_destinations[choice]
            break
        else:
            print("Invalid choice. Please select a database that is not a source.")

    print(f"You have selected the following destination: {dest_db_key.upper()}")

    # --- Prepare configurations and call the main function ---
    dest_config = configs.get(dest_db_key)

    if not dest_config:
        print(f"Error: Configuration for destination '{dest_db_key}' not found in config.json.")
        raise SystemExit(1)

    # Call the main data aggregation function with the collected choices
    copy_from_many_to_one_union(source_choices, configs, dest_db_key, dest_config)