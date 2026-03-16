# -*- coding: utf-8 -*-

from odoo import models, fields, tools
import logging

_logger = logging.getLogger(__name__)


class SaleProfitabilityReport(models.Model):
    """
    SQL-based read-only model that aggregates sales profitability data.
    This is a database view (not a regular table) for efficient querying.
    """
    _name = 'sale.profitability.report'
    _description = 'Sales Profitability Analysis'
    _auto = False
    _rec_name = 'order_name'
    _order = 'order_date desc, order_name'

    # ──────────────────────────────────────────────────────────────
    # FIELDS
    # ──────────────────────────────────────────────────────────────
    order_id = fields.Many2one(
        'sale.order', string='Sale Order', readonly=True,
    )
    order_name = fields.Char(
        string='Order Reference', readonly=True,
    )
    order_date = fields.Date(
        string='Order Date', readonly=True,
    )
    confirmation_date = fields.Datetime(
        string='Confirmation Date', readonly=True,
    )
    state = fields.Selection([
        ('sale', 'Sales Order'),
        ('done', 'Locked'),
    ], string='Status', readonly=True)

    partner_id = fields.Many2one(
        'res.partner', string='Customer', readonly=True,
    )
    partner_name = fields.Char(
        string='Customer Name', readonly=True,
    )

    product_id = fields.Many2one(
        'product.product', string='Product', readonly=True,
    )
    product_tmpl_id = fields.Many2one(
        'product.template', string='Product Template', readonly=True,
    )
    product_name = fields.Char(
        string='Product Name', readonly=True,
    )
    categ_id = fields.Many2one(
        'product.category', string='Product Category', readonly=True,
    )
    category_name = fields.Char(
        string='Category Name', readonly=True,
    )

    quantity = fields.Float(
        string='Quantity Sold', readonly=True,
    )
    unit_price = fields.Float(
        string='Unit Price', readonly=True,
    )
    discount = fields.Float(
        string='Discount %', readonly=True,
    )
    revenue = fields.Float(
        string='Revenue', readonly=True,
    )
    cost = fields.Float(
        string='Cost', readonly=True,
    )
    margin = fields.Float(
        string='Margin', readonly=True,
    )
    margin_percent = fields.Float(
        string='Margin %', readonly=True,
    )

    company_id = fields.Many2one(
        'res.company', string='Company', readonly=True,
    )
    currency_id = fields.Many2one(
        'res.currency', string='Currency', readonly=True,
    )
    user_id = fields.Many2one(
        'res.users', string='Salesperson', readonly=True,
    )
    team_id = fields.Many2one(
        'crm.team', string='Sales Team', readonly=True,
    )

    # ──────────────────────────────────────────────────────────────
    # HELPER: CHECK IF COLUMN EXISTS IN DATABASE
    # ──────────────────────────────────────────────────────────────

    def _column_exists(self, table, column):
        """
        Check if a specific column exists in a database table.
        Returns True if column exists, False otherwise.
        """
        self.env.cr.execute("""
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_name = %s
                  AND column_name = %s
            )
        """, (table, column))
        return self.env.cr.fetchone()[0]

    # ──────────────────────────────────────────────────────────────
    # SQL VIEW DEFINITION
    # ──────────────────────────────────────────────────────────────

    def init(self):
        """
        Create or replace the database view for profitability analysis.

        Dynamically checks whether 'purchase_price' exists on
        sale_order_line (added by sale_margin module) and builds
        the cost calculation SQL accordingly.
        """
        tools.drop_view_if_exists(self.env.cr, self._table)

        # ── Step 1: Check which cost columns actually exist ──

        has_purchase_price = self._column_exists(
            'sale_order_line', 'purchase_price'
        )
        has_standard_price = self._column_exists(
            'product_template', 'standard_price'
        )

        _logger.info(
            "Building profitability SQL view: "
            "sale_order_line.purchase_price exists = %s, "
            "product_template.standard_price exists = %s",
            has_purchase_price, has_standard_price,
        )

        # ── Step 2: Build cost expression dynamically ──

        if has_purchase_price and has_standard_price:
            # Best case: sale_margin installed + standard_price available
            cost_expr = """
                CASE
                    WHEN COALESCE(sol.purchase_price, 0) > 0
                        THEN sol.product_uom_qty * sol.purchase_price
                    WHEN COALESCE(pt.standard_price, 0) > 0
                        THEN sol.product_uom_qty * pt.standard_price
                    ELSE 0.0
                END
            """
        elif has_purchase_price:
            # sale_margin installed but no standard_price column
            cost_expr = """
                CASE
                    WHEN COALESCE(sol.purchase_price, 0) > 0
                        THEN sol.product_uom_qty * sol.purchase_price
                    ELSE 0.0
                END
            """
        elif has_standard_price:
            # No sale_margin, use standard_price only
            cost_expr = """
                CASE
                    WHEN COALESCE(pt.standard_price, 0) > 0
                        THEN sol.product_uom_qty * pt.standard_price
                    ELSE 0.0
                END
            """
        else:
            # No cost data available at all
            cost_expr = "0.0"
            _logger.warning(
                "No cost column found! Neither 'purchase_price' on "
                "sale_order_line nor 'standard_price' on product_template. "
                "All costs will show as 0."
            )

        # ── Step 3: Build product name expression ──
        # Handle Odoo's translated name field
        # In Odoo 18, product_template.name can be JSONB or varchar
        # depending on configuration

        has_jsonb_name = False
        try:
            self.env.cr.execute("""
                SELECT data_type
                FROM information_schema.columns
                WHERE table_name = 'product_template'
                  AND column_name = 'name'
            """)
            result = self.env.cr.fetchone()
            if result and result[0] in ('jsonb', 'json'):
                has_jsonb_name = True
        except Exception:
            pass

        if has_jsonb_name:
            product_name_expr = "COALESCE(pt.name->>'en_US', pt.name->>'', sol.name)"
        else:
            product_name_expr = "COALESCE(pt.name, sol.name)"

        # ── Step 4: Check if team_id exists on sale_order ──
        has_team_id = self._column_exists('sale_order', 'team_id')
        team_select = "so.team_id AS team_id," if has_team_id else "NULL::integer AS team_id,"

        # ── Step 5: Build and execute the full SQL ──

        query = """
            CREATE OR REPLACE VIEW %(table)s AS (
                SELECT
                    -- Row ID
                    sol.id AS id,

                    -- Order Information
                    so.id                       AS order_id,
                    so.name                     AS order_name,
                    so.date_order::date         AS order_date,
                    so.date_order               AS confirmation_date,
                    so.state                    AS state,
                    so.company_id               AS company_id,
                    so.currency_id              AS currency_id,
                    so.user_id                  AS user_id,
                    %(team_select)s

                    -- Customer Information
                    so.partner_id               AS partner_id,
                    rp.name                     AS partner_name,

                    -- Product Information
                    sol.product_id              AS product_id,
                    pp.product_tmpl_id          AS product_tmpl_id,
                    %(product_name_expr)s       AS product_name,
                    pt.categ_id                 AS categ_id,
                    pc.complete_name            AS category_name,

                    -- Quantity & Pricing
                    sol.product_uom_qty         AS quantity,
                    sol.price_unit              AS unit_price,
                    COALESCE(sol.discount, 0)   AS discount,

                    -- Revenue (untaxed subtotal)
                    sol.price_subtotal          AS revenue,

                    -- Cost (dynamically built)
                    (%(cost_expr)s)             AS cost,

                    -- Margin
                    sol.price_subtotal - (%(cost_expr)s) AS margin,

                    -- Margin Percentage
                    CASE
                        WHEN sol.price_subtotal > 0 THEN
                            ROUND(
                                (
                                    (sol.price_subtotal - (%(cost_expr)s))
                                    / sol.price_subtotal
                                ) * 100,
                            2)
                        ELSE 0.0
                    END AS margin_percent

                FROM sale_order_line sol

                    INNER JOIN sale_order so
                        ON sol.order_id = so.id

                    INNER JOIN res_partner rp
                        ON so.partner_id = rp.id

                    LEFT JOIN product_product pp
                        ON sol.product_id = pp.id

                    LEFT JOIN product_template pt
                        ON pp.product_tmpl_id = pt.id

                    LEFT JOIN product_category pc
                        ON pt.categ_id = pc.id

                WHERE
                    so.state IN ('sale', 'done')
                    AND sol.product_id IS NOT NULL
                    AND sol.product_uom_qty > 0
            )
        """ % {
            'table': self._table,
            'cost_expr': cost_expr,
            'product_name_expr': product_name_expr,
            'team_select': team_select,
        }

        self.env.cr.execute(query)

        _logger.info(
            "SQL view '%s' created successfully.", self._table
        )

        # ── Step 6: Verify the view works ──
        try:
            self.env.cr.execute(
                "SELECT COUNT(*) FROM %s" % self._table
            )
            count = self.env.cr.fetchone()[0]
            _logger.info(
                "SQL view '%s' verification: %d records found.",
                self._table, count,
            )
        except Exception as e:
            _logger.error(
                "SQL view '%s' verification FAILED: %s",
                self._table, str(e),
            )
