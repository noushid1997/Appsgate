from logging import Logger

from markupsafe import Markup
from odoo import models, fields, api, _
from datetime import date
from odoo.exceptions import ValidationError, UserError
import logging
_logger = logging.getLogger(__name__)



class SaleOrder(models.Model):
    _inherit = 'sale.order'

    applied_discount_rule_id = fields.Many2one(
        'sale.discount.rule', 'Applied Discount Rule', readonly=True)

    advance_payment = fields.Monetary(
        string='Advance Payment',
        currency_field='currency_id',
        default=0.0,
        tracking=True,
        help="Amount to be recorded as advance payment upon order confirmation. "
             "A journal entry will be created: Debit Receivable, Credit Advance Received."
    )

    advance_move_id = fields.Many2one(
        comodel_name='account.move',
        string='Advance Journal Entry',
        readonly=True,
        copy=False,
        help="The journal entry generated for the advance payment."
    )

    advance_payment_state = fields.Selection(
        selection=[
            ('none', 'No Advance'),
            ('posted', 'Entry Posted'),
            ('reversed', 'Entry Reversed'),
        ],
        string='Advance Payment Status',
        default='none',
        readonly=True,
        copy=False,
        tracking=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        """ supering for create automaticaly apply discount rule
        """
        orders = super().create(vals_list)
        for order in orders:
            order._apply_discount_rule()
        return orders

    def _apply_discount_rule(self):
        for order in self:
            rule = order._get_matching_discount_rule()
            if rule:
                for line in order.order_line:
                    print(line, line.display_type, "dsfsdfds")
                    if not line.display_type:
                        line.discount = rule.discount_percent
                order.applied_discount_rule_id = rule.id
                order.message_post(
                    body=_('Discount rule %s applied, The Discount Percentage is %.2f') % (rule.name, rule.discount_percent)
                )
            else:
                order.applied_discount_rule_id = False
                for line in order.order_line:
                    if not line.display_type:
                        line.discount = 0

    def _get_matching_discount_rule(self):
        """
        In this function it will check matching rule based on the order and returns
        """
        self.ensure_one()
        today = date.today()
        order_amount = self.amount_untaxed
        print(order_amount, "dsfsdfsdf")
        partner_tag_ids = self.partner_id.category_id.ids

        domain = [
            ('valid_from', '<=', today),
            ('valid_to', '>=', today),
            ('min_amount', '<=', order_amount),
            ('max_amount', '>=', order_amount),
            ('active', '=', True),
            ('company_id', '=', self.company_id.id)
        ]

        rules = self.env['sale.discount.rule'].search(domain)
        print(rules, "dsfsdfsdf")
        # Filter by customer group
        matching_rules = rules.filtered(lambda r: not r.customer_group
                                        or bool(set(r.customer_group.ids) & set(partner_tag_ids)))

        # Return highest matching one
        return matching_rules[:1] if matching_rules else False

    def action_reapply_discount(self):
        """
        Button function reapply discount based on the condition of sale order
        """
        self.ensure_one()
        self._apply_discount_rule()

    @api.constrains('advance_payment')
    def _check_advance_payment_amount(self):
        """Ensure advance payment is not negative and does not exceed order total."""
        for order in self:
            if order.advance_payment < 0:
                raise ValidationError(
                    _("Advance payment amount cannot be negative.")
                )
            if order.advance_payment > order.amount_total and order.amount_total > 0:
                raise ValidationError(
                    _("Advance payment (%(advance)s) cannot exceed "
                      "the order total (%(total)s).",
                      advance=order.advance_payment,
                      total=order.amount_total)
                )

    def _get_advance_journal(self):
        """
        Return the journal to use for advance payment entries.
        Searches for a journal with code 'ADV', falls back to the
        first miscellaneous journal of the company.
        """
        self.ensure_one()
        journal = self.env['account.journal'].search([
            ('code', '=', 'ADV'),
            ('company_id', '=', self.company_id.id),
        ], limit=1)

        if not journal:
            journal = self.env['account.journal'].search([
                ('type', '=', 'general'),
                ('company_id', '=', self.company_id.id),
            ], limit=1)

        if not journal:
            raise UserError(
                _("No miscellaneous journal found for company %s. "
                  "Please create a journal with code 'ADV' or a general journal.",
                  self.company_id.name)
            )
        return journal

    def _get_advance_receivable_account(self):
        """
        Return the receivable account from the customer's property.
        Falls back to account.property_account_receivable_id.
        """
        self.ensure_one()
        partner = self.partner_id.commercial_partner_id
        account = partner.property_account_receivable_id

        if not account:
            raise UserError(
                _("No receivable account configured for partner '%s'. "
                  "Please set the Accounts Receivable on the partner form.",
                  partner.name)
            )
        return account

    def _get_advance_received_account(self):
        """
        Return the advance received (liability) account.
        Uses the XML-ID defined in this module's data, with fallback
        to searching by code 'ADV_RCV'.
        """
        self.ensure_one()

        # ── Attempt 1: Load via XML-ID ──
        account = self.env.ref(
            'sale_advance_payment.account_advance_received',
            raise_if_not_found=False
        )

        # ── Validate the XML-ID account belongs to this company ──
        if account and self.company_id not in account.company_ids:
            # Account exists but is not linked to the current company
            _logger.info(
                "Advance account from XML-ID (id=%s) is not linked to "
                "company '%s'. Searching by code instead.",
                account.id, self.company_id.name
            )
            account = False

        # ── Attempt 2: Fallback search by code within the company ──
        if not account:
            account = self.env['account.account'].search([
                ('code', '=', 'ADV_RCV'),
                ('company_ids', 'in', self.company_id.ids),
            ], limit=1)

        # ── Attempt 3: Broader search - code starts with 'ADV' ──
        if not account:
            account = self.env['account.account'].search([
                ('code', '=like', 'ADV%'),
                ('account_type', '=', 'liability_current'),
                ('company_ids', 'in', self.company_id.ids),
            ], limit=1)

        if not account:
            raise UserError(
                _("No 'Advance Received' account found. "
                  "Please create an account with code 'ADV_RCV' "
                  "(type: Current Liabilities) for company %s.",
                  self.company_id.name)
            )
        return account
    
    # ──────────────────────────────────────────────────────────────
    # JOURNAL ENTRY CREATION
    # ──────────────────────────────────────────────────────────────

    def _prepare_advance_payment_move_vals(self):
        """
        Prepare the vals dict for creating the advance payment journal entry.

        Returns a dict ready for account.move.create().

        Accounting logic:
            Debit  →  Accounts Receivable (Customer)
            Credit →  Advance Received (Liability)
        """
        self.ensure_one()

        journal = self._get_advance_journal()
        receivable_account = self._get_advance_receivable_account()
        advance_account = self._get_advance_received_account()
        partner = self.partner_id.commercial_partner_id

        move_vals = {
            'move_type': 'entry',
            'journal_id': journal.id,
            'date': fields.Date.context_today(self),
            'ref': _('Advance Payment - %s', self.name),
            'company_id': self.company_id.id,
            'partner_id': partner.id,
            'currency_id': self.currency_id.id,
            'line_ids': [
                # Debit line: Customer Receivable
                (0, 0, {
                    'name': _('Advance Receivable - %s', self.name),
                    'partner_id': partner.id,
                    'account_id': receivable_account.id,
                    'debit': self.advance_payment,
                    'credit': 0.0,
                    'currency_id': self.currency_id.id,
                    'amount_currency': self.advance_payment,
                }),
                # Credit line: Advance Received (Liability)
                (0, 0, {
                    'name': _('Advance Received - %s', self.name),
                    'partner_id': partner.id,
                    'account_id': advance_account.id,
                    'debit': 0.0,
                    'credit': self.advance_payment,
                    'currency_id': self.currency_id.id,
                    'amount_currency': -self.advance_payment,
                }),
            ],
        }
        return move_vals

    def _create_advance_payment_entry(self):
        """
        Create and post the advance payment journal entry.
        Link it to the sale order and log in chatter.
        """
        self.ensure_one()

        if self.advance_payment <= 0:
            _logger.info(
                "Sale order %s: No advance payment to record (amount: %s).",
                self.name, self.advance_payment
            )
            return False

        if self.advance_move_id:
            _logger.warning(
                "Sale order %s: Advance journal entry already exists (%s). Skipping.",
                self.name, self.advance_move_id.name
            )
            return self.advance_move_id

        # 1. Prepare and create the journal entry
        move_vals = self._prepare_advance_payment_move_vals()
        move = self.env['account.move'].sudo().create(move_vals)

        # 2. Post the journal entry
        move.action_post()

        # 3. Link the entry to the sale order
        self.write({
            'advance_move_id': move.id,
            'advance_payment_state': 'posted',
        })

        # 4. Log in chatter with a rich message
        currency_symbol = self.currency_id.symbol or ''
        body = Markup(_(
            '<div class="o_mail_notification">'
            '<strong>Advance Payment Journal Entry Created</strong><br/>'
            '<ul>'
            '<li><b>Entry:</b> <a href="#" data-oe-model="account.move" '
            'data-oe-id="%(move_id)s">%(move_name)s</a></li>'
            '<li><b>Amount:</b> %(currency)s %(amount).2f</li>'
            '<li><b>Date:</b> %(date)s</li>'
            '<li><b>Debit Account:</b> %(debit_account)s (Receivable)</li>'
            '<li><b>Credit Account:</b> %(credit_account)s (Advance Received)</li>'
            '</ul>'
            '</div>',
            move_id=move.id,
            move_name=move.name,
            currency=currency_symbol,
            amount=self.advance_payment,
            date=move.date,
            debit_account=self._get_advance_receivable_account().display_name,
            credit_account=self._get_advance_received_account().display_name,
        ))
        self.message_post(
            body=body,
            message_type='notification',
            subtype_xmlid='mail.mt_note',
        )

        _logger.info(
            "Sale order %s: Advance payment entry %s posted for amount %s %s.",
            self.name, move.name, currency_symbol, self.advance_payment
        )
        return move
    
    # ──────────────────────────────────────────────────────────────
    # OVERRIDE: SALE ORDER CONFIRMATION
    # ──────────────────────────────────────────────────────────────

    def action_confirm(self):
        """
        Override the standard confirmation to create advance payment
        journal entries for orders that have an advance_payment > 0.
        """
        result = super().action_confirm()

        for order in self:
            if order.advance_payment > 0:
                try:
                    order._create_advance_payment_entry()
                except UserError as e:
                    # Re-raise with order context
                    raise UserError(
                        _("Error creating advance payment entry for order %s:\n%s",
                          order.name, str(e))
                    ) from e

        return result

    # ──────────────────────────────────────────────────────────────
    # ACTION: VIEW JOURNAL ENTRY
    # ──────────────────────────────────────────────────────────────

    def action_view_advance_entry(self):
        """
        Open the advance payment journal entry in form view.
        """
        self.ensure_one()
        if not self.advance_move_id:
            raise UserError(
                _("No advance payment journal entry found for this order."))

        return {
            'type': 'ir.actions.act_window',
            'name': _('Advance Payment Entry'),
            'res_model': 'account.move',
            'res_id': self.advance_move_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
    # ──────────────────────────────────────────────────────────────
    # ACTION: REVERSE ADVANCE ENTRY
    # ──────────────────────────────────────────────────────────────

    def action_reverse_advance_entry(self):
        """
        Reverse the advance payment journal entry (e.g., on order cancellation).
        """
        self.ensure_one()
        if not self.advance_move_id:
            raise UserError(_("No advance payment journal entry to reverse."))

        if self.advance_payment_state == 'reversed':
            raise UserError(
                _("The advance payment entry has already been reversed."))

        # Create reversal
        reversal_wizard = self.env['account.move.reversal'].with_context(
            active_model='account.move',
            active_ids=self.advance_move_id.ids,
        ).create({
            'reason': _('Reversal of advance payment for %s', self.name),
            'refund_method': 'cancel',
            'journal_id': self.advance_move_id.journal_id.id,
        })
        reversal_wizard.reverse_moves()

        self.write({'advance_payment_state': 'reversed'})

        self.message_post(
            body=_('<strong>Advance Payment Entry Reversed</strong><br/>'
                   'The journal entry %s has been reversed.',
                   self.advance_move_id.name),
            message_type='notification',
            subtype_xmlid='mail.mt_note',
        )

        return True

    def action_cancel(self):
        """Override cancel to reverse advance payment entries."""
        for order in self:
            if order.advance_move_id and order.advance_payment_state == 'posted':
                order.action_reverse_advance_entry()
        return super().action_cancel()
