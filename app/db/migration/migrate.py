import logging
import os

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import SQLAlchemyError

from app.db.model.base import Base
from app.utils.log import setup_custom_logger

logger = setup_custom_logger(__name__)

def get_alembic_config(alembic_ini_path):
    if not os.path.exists(alembic_ini_path):
        raise FileNotFoundError(f"Alembic configuration file not found: {alembic_ini_path}")

    alembic_cfg = Config(alembic_ini_path)
    script_location = alembic_cfg.get_main_option("script_location")
    if not script_location:
        raise ValueError("script_location not set in alembic.ini")

    if not os.path.isabs(script_location):
        script_location = os.path.join(os.path.dirname(alembic_ini_path), script_location)

    if not os.path.exists(script_location):
        raise FileNotFoundError(f"Migration script directory not found: {script_location}")

    alembic_cfg.set_main_option("script_location", script_location)
    return alembic_cfg


def get_current_revision(engine):
    with engine.connect() as conn:
        context = MigrationContext.configure(conn)
        return context.get_current_revision()


def get_head_revision(alembic_cfg):
    script = ScriptDirectory.from_config(alembic_cfg)
    head_revision = script.get_current_head()
    if head_revision is None:
        logger.warning(
            "No migration scripts found. Ensure you have run 'alembic revision -m \"initial\"' to create your first migration.")
    return head_revision


def create_initial_revision(alembic_cfg):
    try:
        command.revision(alembic_cfg, message="Initial revision", autogenerate=True)
        logger.info("Created initial revision")
        return get_head_revision(alembic_cfg)
    except Exception as e:
        logger.error(f"Error creating initial revision: {str(e)}")
        return None


def check_model_changes(engine, metadata):
    with engine.connect() as connection:
        context = MigrationContext.configure(connection)
        diff = compare_metadata(context, metadata)
        return bool(diff)

def safe_upgrade(engine, alembic_cfg):
    current_rev = get_current_revision(engine)
    head_rev = get_head_revision(alembic_cfg)

    if head_rev is None:
        logger.info("No migration scripts found. Creating initial revision.")
        head_rev = create_initial_revision(alembic_cfg)
        if head_rev is None:
            logger.error("Failed to create initial revision. Cannot proceed with upgrade.")
            return

    if current_rev is None:
        logger.info("No current revision found. Initializing with head revision.")
        with engine.begin() as conn:
            conn.execute(text(f"INSERT INTO alembic_version (version_num) VALUES ('{head_rev}')"))
        current_rev = head_rev

    # Check for model changes
    if check_model_changes(engine, Base.metadata):
        logger.info("Detected changes in the Base model. Creating a new revision.")
        try:
            with engine.begin() as connection:
                alembic_cfg.attributes['connection'] = connection
                revision = command.revision(alembic_cfg, message="Model changes", autogenerate=True)
            logger.info(f"Created new revision: {revision}")
            head_rev = get_head_revision(alembic_cfg)  # Update head revision
        except Exception as e:
            logger.error(f"Error creating revision for model changes: {str(e)}")
            return

    if current_rev == head_rev:
        logger.info("Database is up to date")
        return

    try:
        command.upgrade(alembic_cfg, "head")
        logger.info("Successfully upgraded database to latest version")
    except SQLAlchemyError as e:
        logger.error(f"Error during migration: {str(e)}")
        logger.info("Attempting to roll back to previous version")
        try:
            command.downgrade(alembic_cfg, f"{current_rev}")
            logger.info("Successfully rolled back to previous version")
        except SQLAlchemyError as rollback_error:
            logger.error(f"Error during rollback: {str(rollback_error)}")
            logger.critical("Database is in an inconsistent state. Manual intervention required.")


def run_migrations(db_url, alembic_ini_path):
    engine = create_engine(db_url)

    try:
        alembic_cfg = get_alembic_config(alembic_ini_path)
        alembic_cfg.set_main_option("sqlalchemy.url", db_url)

        with engine.begin() as connection:
            alembic_cfg.attributes['connection'] = connection
            safe_upgrade(engine, alembic_cfg)
    except Exception as e:
        logger.error(f"Unexpected error during migration: {str(e)}")
    finally:
        engine.dispose()