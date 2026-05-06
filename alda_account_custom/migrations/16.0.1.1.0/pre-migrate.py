import logging

from psycopg2 import sql

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Create hotel/project analytic columns before ORM processes the module.

    By creating the columns here (pre-migration), Odoo finds them already
    existing during the schema update and skips the stored-field recompute.
    Values are then filled efficiently via raw SQL in post-migrate.py.

    Only integer columns are created; Odoo will add FK constraints and indexes
    during its normal schema update step.
    """
    for table, col in (
        ("account_move_line", "hotel_analytic_account_id"),
        ("account_move_line", "project_analytic_account_id"),
        ("account_move_budget_line", "hotel_analytic_account_id"),
        ("account_move_budget_line", "project_analytic_account_id"),
    ):
        cr.execute(
            sql.SQL(
                "ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} integer"
            ).format(
                table=sql.Identifier(table),
                col=sql.Identifier(col),
            )
        )
        _logger.info("Ensured column %s.%s exists", table, col)
