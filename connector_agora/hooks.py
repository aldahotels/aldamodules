# © 2026 Alexandra Suarez <saya.alex20@gmail.com> (Aldamodules)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).


def pre_init_hook(cr):
    """Create the stored computed columns of account.move before install.

    If the columns already exist, Odoo does not recompute them for every
    existing move (all of them would be empty anyway: no Agora bindings yet).
    """
    cr.execute(
        """
        ALTER TABLE account_move
            ADD COLUMN IF NOT EXISTS agora_invoice_ref varchar,
            ADD COLUMN IF NOT EXISTS agora_origin varchar
        """
    )
