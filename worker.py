"""
worker.py
Background worker process for continuous data deidentification
Monitors source tables and automatically deidentifies new records
"""

import os
import time
import logging
from datetime import datetime
from sqlalchemy import create_engine, text, inspect, MetaData, Table
import threading
import signal

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [WORKER] - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DeidentificationWorker:
    """
    Background worker that:
    1. Discovers tables in source database
    2. Creates deidentified copies
    3. Monitors for new records
    4. Automatically deidentifies and syncs
    """

    def __init__(self, db_url: str, secret_key: str):
        """
        Initialize worker

        Args:
            db_url: Database connection URL
            secret_key: HMAC secret for deidentification
        """
        self.db_url = db_url
        self.secret_key = secret_key
        self.engine = create_engine(db_url, pool_pre_ping=True)
        self.running = True
        self.processed_ids = {}  # Track which records have been deidentified

        import hmac
        import hashlib
        self.hmac = hmac
        self.hashlib = hashlib

    def get_tables(self):
        """Discover all tables in database"""
        inspector = inspect(self.engine)
        return inspector.get_table_names()

    def is_user_table(self, table_name: str):
        """Check if table contains user/member data"""
        # Skip system tables
        if table_name.startswith('_') or table_name.startswith('mysql'):
            return False

        # Tables containing 'member', 'user', 'account', 'profile'
        keywords = ['member', 'user', 'account', 'profile', 'raw']
        return any(keyword in table_name.lower() for keyword in keywords)

    def get_email_column(self, table_name: str):
        """Find email column in table (primary identifier)"""
        inspector = inspect(self.engine)
        columns = [col['name'] for col in inspector.get_columns(table_name)]

        # Look for email, email_address, user_email, etc.
        for col in columns:
            if 'email' in col.lower():
                return col
        return None

    def get_id_column(self, table_name: str):
        """Find primary key column"""
        inspector = inspect(self.engine)
        pk = inspector.get_pk_constraint(table_name)

        if pk and pk.get('constrained_columns'):
            return pk['constrained_columns'][0]

        # Default to 'id' if no PK found
        return 'id'

    def generate_anon_id(self, email: str):
        """Generate anonymous ID from email"""
        return self.hmac.new(
            self.secret_key.encode(),
            email.encode(),
            self.hashlib.sha256
        ).hexdigest()

    def create_deidentified_table(self, source_table: str):
        """
        Create deidentified copy of source table
        Schema: source_table → source_table_deidentified
        """
        deident_table = f"{source_table}_deidentified"

        with self.engine.connect() as conn:
            # Check if already exists
            inspector = inspect(self.engine)
            if deident_table in inspector.get_table_names():
                logger.info(f"✓ Table {deident_table} already exists")
                return deident_table

            # Get source columns
            columns = inspector.get_columns(source_table)

            # Build CREATE TABLE statement
            col_defs = []
            for col in columns:
                col_name = col['name']
                col_type = col['type']

                # Change email columns to anon_id
                if 'email' in col_name.lower():
                    col_defs.append(f"`anon_id` VARCHAR(64) UNIQUE NOT NULL")
                else:
                    col_defs.append(f"`{col_name}` {col_type}")

            # Add tracking columns
            col_defs.append("`source_id` INT")
            col_defs.append("`deidentified_at` DATETIME DEFAULT CURRENT_TIMESTAMP")

            sql = f"CREATE TABLE `{deident_table}` ({', '.join(col_defs)}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"

            try:
                conn.execute(text(sql))
                conn.commit()
                logger.info(f"✓ Created deidentified table: {deident_table}")
                return deident_table
            except Exception as e:
                logger.error(f"Failed to create {deident_table}: {e}")
                return None

    def sync_existing_records(self, source_table: str):
        """
        Sync all existing records from source to deidentified table
        Run once on startup
        """
        deident_table = f"{source_table}_deidentified"
        email_col = self.get_email_column(source_table)
        id_col = self.get_id_column(source_table)

        if not email_col:
            logger.warning(f"No email column found in {source_table}, skipping")
            return

        with self.engine.connect() as conn:
            # Get count of existing records
            result = conn.execute(
                text(f"SELECT COUNT(*) as cnt FROM {deident_table}")
            )
            existing_count = result.scalar()

            if existing_count > 0:
                logger.info(f"✓ {deident_table} already has {existing_count} records")
                return

            # Get all records from source
            result = conn.execute(text(f"SELECT * FROM {source_table}"))
            rows = result.fetchall()

            logger.info(f"Processing {len(rows)} existing records from {source_table}...")

            # Insert into deidentified table
            for row in rows:
                row_dict = dict(row._mapping) if hasattr(row, '_mapping') else dict(row)
                email = row_dict.get(email_col)
                source_id = row_dict.get(id_col)

                if not email:
                    continue

                anon_id = self.generate_anon_id(email)

                # Build INSERT statement
                cols = list(row_dict.keys())
                cols.remove(email_col)  # Remove email
                cols.append('anon_id')
                cols.append('source_id')

                placeholders = ','.join([f":%{col}" for col in cols])
                insert_sql = f"INSERT IGNORE INTO {deident_table} ({','.join(cols)}) VALUES ({placeholders})"

                try:
                    conn.execute(text(insert_sql), {
                        **{k: v for k, v in row_dict.items() if k != email_col},
                        'anon_id': anon_id,
                        'source_id': source_id
                    })
                except Exception as e:
                    logger.debug(f"Could not insert record: {e}")

            conn.commit()
            logger.info(f"✓ Synced {len(rows)} records to {deident_table}")

    def monitor_new_records(self, source_table: str):
        """
        Monitor source table for new records
        Run continuously
        """
        deident_table = f"{source_table}_deidentified"
        email_col = self.get_email_column(source_table)
        id_col = self.get_id_column(source_table)

        if not email_col:
            return

        # Keep track of last synced ID
        last_id = self.processed_ids.get(source_table, 0)

        with self.engine.connect() as conn:
            # Get new records since last sync
            query = f"""
                SELECT * FROM {source_table}
                WHERE {id_col} > {last_id}
                ORDER BY {id_col}
            """

            try:
                result = conn.execute(text(query))
                new_rows = result.fetchall()

                if new_rows:
                    logger.info(f"Found {len(new_rows)} new records in {source_table}")

                    for row in new_rows:
                        row_dict = dict(row._mapping) if hasattr(row, '_mapping') else dict(row)
                        email = row_dict.get(email_col)
                        source_id = row_dict.get(id_col)

                        if not email:
                            continue

                        anon_id = self.generate_anon_id(email)

                        # Insert into deidentified table
                        cols = list(row_dict.keys())
                        cols.remove(email_col)
                        cols.append('anon_id')
                        cols.append('source_id')

                        placeholders = ','.join([f":{col}" for col in cols])
                        insert_sql = f"INSERT IGNORE INTO {deident_table} ({','.join(cols)}) VALUES ({placeholders})"

                        try:
                            conn.execute(text(insert_sql), {
                                **{k: v for k, v in row_dict.items() if k != email_col},
                                'anon_id': anon_id,
                                'source_id': source_id
                            })

                            # Update last processed ID
                            self.processed_ids[source_table] = max(
                                self.processed_ids.get(source_table, 0),
                                source_id
                            )
                        except Exception as e:
                            logger.debug(f"Error inserting record: {e}")

                    conn.commit()
                    logger.info(f"✓ Deidentified {len(new_rows)} new records")

            except Exception as e:
                logger.error(f"Error monitoring {source_table}: {e}")

    def run(self, interval: int = 10):
        """
        Main worker loop

        Args:
            interval: Check for new records every N seconds
        """
        logger.info("=" * 60)
        logger.info("DEIDENTIFICATION WORKER STARTED")
        logger.info("=" * 60)

        try:
            # 1. Discover tables
            tables = self.get_tables()
            user_tables = [t for t in tables if self.is_user_table(t)]

            logger.info(f"Found {len(user_tables)} user/member tables:")
            for t in user_tables:
                logger.info(f"  - {t}")

            # 2. Create deidentified copies
            logger.info("\nCreating deidentified tables...")
            deident_tables = {}
            for table in user_tables:
                deident = self.create_deidentified_table(table)
                if deident:
                    deident_tables[table] = deident

            # 3. Sync existing records
            logger.info("\nSyncing existing records...")
            for table in user_tables:
                self.sync_existing_records(table)

            logger.info("\n" + "=" * 60)
            logger.info("MONITORING MODE - Waiting for new records...")
            logger.info("=" * 60 + "\n")

            # 4. Continuous monitoring
            while self.running:
                for table in user_tables:
                    self.monitor_new_records(table)

                time.sleep(interval)

        except Exception as e:
            logger.error(f"Worker error: {e}")
            raise

    def stop(self):
        """Stop worker gracefully"""
        logger.info("\nShutting down worker...")
        self.running = False


def setup_signal_handlers(worker):
    """Handle shutdown signals"""

    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}")
        worker.stop()

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)


if __name__ == '__main__':
    from urllib.parse import quote_plus

    # Get database credentials
    db_user = os.getenv('DB_USER', 'root')
    db_password = os.getenv('DB_PASSWORD', '')
    db_host = os.getenv('DB_HOST', 'localhost')
    db_port = os.getenv('DB_PORT', '3306')
    db_name = os.getenv('DB_NAME', 'test')
    secret_key = os.getenv('DEIDENTIFICATION_SECRET', 'secret')

    # URL encode password
    encoded_password = quote_plus(db_password)
    db_url = f'mysql+pymysql://{db_user}:{encoded_password}@{db_host}:{db_port}/{db_name}'

    # Create and run worker
    worker = DeidentificationWorker(db_url, secret_key)
    setup_signal_handlers(worker)

    try:
        worker.run(interval=10)  # Check every 10 seconds
    except KeyboardInterrupt:
        logger.info("Worker stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        exit(1)