from markupsafe import Markup

from odoo import _, models, fields, api
from odoo.exceptions import UserError, ValidationError


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    state = fields.Selection(
        selection_add=[
            ('to_approve', 'To Approve'),
            ('approved_level1', 'Approved Level 1'),
            ('approved_level2', 'Approved Level 2'),
            ('refuse', 'Refused')
        ],
        ondelete={
            'to_approve': 'cascade',
            'approved_level1': 'cascade',
            'approved_level2': 'cascade',
        }
    )

    approval_level = fields.Integer(
        string='Required Approval Level',
        compute='_compute_approval_level',
        store=True,
    )

    @api.depends('amount_total')
    def _compute_approval_level(self):
        """
        Compute the Level Approval Required Based on the State
        """
        for order in self:
            if order.amount_total <= 5000:
                order.approval_level = 0
            elif order.amount_total <= 20000:
                order.approval_level = 1
            else:
                order.approval_level = 2

    def button_confirm(self):
        """
        Button Fucntion modifying to sent to approve based on level of amount.
        """
        for order in self:
            if order.approval_level == 0:
                print("dsfsdfsdf")
                return super().button_confirm()
            elif order.state == 'approved_level2':
                self.button_approve()
            elif order.approval_level == 1:
                order.write({
                    'state': 'to_approve'
                })
                msg = Markup(_(
                    'Purchase Order Sumbited for <b>Level 1</b> Approval, For the Amount %.2f.')) % (order.amount_total)
                order.message_post(body=msg)
            else:
                order.write({
                    'state': 'to_approve'
                })
                msg = Markup(_(
                    'Purchase Order Sumbited for <b>Level 1 + Level 2</b> Approvals Required, For the Amount %.2f.')) % (order.amount_total)
                order.message_post(body=msg)
        return True

    def action_approve_level1(self):
        """
        Level 1 approval 
        """

        if not self.env.user.has_group('custom_appsgate.group_purchase_approver_level1'):
            raise UserError(_("The User not have Access for Approver Level 1"))
        if self.approval_level == 1:
            self.write({'state': 'approved_level1'})
            self._notify_users('level1')
            super().button_confirm()
            msg = _(
                'Level 1 Approval Completed by %s.') % (self.env.user.name)
            self.message_post(body=msg)
        else:
            self.write({'state': 'approved_level1'})
            self._notify_users('level1')
            msg = _(
                'Level 1 Approval Completed by %s., Send to Level 2 Approval.') % (self.env.user.name)
            self.message_post(body=msg)

    def action_approve_level2(self):
        """
        Level 2 approval 
        """

        if not self.env.user.has_group('custom_appsgate.group_purchase_approver_level2'):
            raise UserError(_("The User not have Access for Approver Level 2"))
        self.write({'state': 'approved_level2'})
        self._notify_users('level2')
        super().button_confirm()
        msg = _(
            'Level 2 Approval Completed by %s.') % (self.env.user.name)
        self.message_post(body=msg)

    def action_refuse(self):
        """
        Refuse Option for the Purchase Order
        """
        self.ensure_one()
        self.write({'state': 'refuse'})
        msg = _(
            'Refused by the user %s.') % (self.env.user.name)
        self.message_post(body=msg)

    def _notify_users(self, level):
        """
        Send Email for the users to notify
        """
        group_map = {
            'level1': ('custom_appsgate.group_purchase_approver_level1'),
            'level2': ('custom_appsgate.group_purchase_approver_level2')
        }
        template_map = {
            'level1': ('custom_appsgate.po_mail_level1'),
            'level2': ('custom_appsgate.po_mail_level2')
        }

        # Get Approvar Group
        group = self.env.ref(group_map.get(level), False)
        if not group or not group.users:
            return

        # Get Email Address
        approver_emails = group.users.filtered(
            lambda u: u.email).mapped('email')

        if not approver_emails:
            return

        # Get Mail Template
        mail_template = self.env.ref(template_map.get(level), False)
        if mail_template:
            email_values = {
                'email_to': ','.join(approver_emails)
            }
            mail_template.send_mail(
                self.id, force_send=True, email_values=email_values)
