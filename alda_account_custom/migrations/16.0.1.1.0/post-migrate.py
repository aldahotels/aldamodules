import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Populate hotel_analytic_account_id and project_analytic_account_id.

    Uses raw SQL to avoid triggering ORM recompute on potentially millions of
    account.move.line records.  The hotel plan is resolved via its XML ID
    (pms.main_pms_analytic_plan); accounts belonging to that plan are mapped
    to hotel_analytic_account_id and the rest to project_analytic_account_id.
    """
    _logger.info(
        "Migrating alda_account_custom 16.0.1.1.0: "
        "populating hotel/project analytic fields"
    )

    # --- account.move.line --------------------------------------------------
    # analytic_distribution is a JSON column with string keys = account IDs.
    cr.execute(
        """
        WITH hotel_plan AS (
            SELECT res_id AS plan_id
            FROM ir_model_data
            WHERE module = 'pms' AND name = 'main_pms_analytic_plan'
            LIMIT 1
        ),
        line_accounts AS (
            SELECT
                aml.id                            AS line_id,
                aa.id                             AS account_id,
                aa.plan_id = hp.plan_id           AS is_hotel
            FROM account_move_line aml
            CROSS JOIN hotel_plan hp
            JOIN LATERAL (
                SELECT key::integer AS account_id
                FROM jsonb_each_text(aml.analytic_distribution::jsonb)
            ) kv ON TRUE
            JOIN account_analytic_account aa ON aa.id = kv.account_id
            WHERE aml.analytic_distribution IS NOT NULL
        ),
        aggregated AS (
            SELECT
                line_id,
                MIN(account_id) FILTER (WHERE is_hotel)      AS hotel_account_id,
                MIN(account_id) FILTER (WHERE NOT is_hotel)  AS project_account_id
            FROM line_accounts
            GROUP BY line_id
        )
        UPDATE account_move_line aml
        SET
            hotel_analytic_account_id   = agg.hotel_account_id,
            project_analytic_account_id = agg.project_account_id
        FROM aggregated agg
        WHERE aml.id = agg.line_id
        """
    )
    _logger.info("account.move.line: %s rows updated", cr.rowcount)

    # --- account.move.budget.line -------------------------------------------
    # Budget lines have a single analytic_account_id (not a distribution).
    cr.execute(
        """
        WITH hotel_plan AS (
            SELECT res_id AS plan_id
            FROM ir_model_data
            WHERE module = 'pms' AND name = 'main_pms_analytic_plan'
            LIMIT 1
        )
        UPDATE account_move_budget_line ambl
        SET
            hotel_analytic_account_id = CASE
                WHEN aa.plan_id = hp.plan_id THEN aa.id
                ELSE NULL
            END,
            project_analytic_account_id = CASE
                WHEN aa.plan_id <> hp.plan_id THEN aa.id
                ELSE NULL
            END
        FROM account_analytic_account aa
        CROSS JOIN hotel_plan hp
        WHERE ambl.analytic_account_id = aa.id
        """
    )
    _logger.info("account.move.budget.line: %s rows updated", cr.rowcount)
