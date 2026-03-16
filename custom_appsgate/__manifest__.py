{
    'name': "Appsgate Custom Module",
    'summary': "Sales, Purchase, Accounting Module Customized",
    'category': 'Custom',
    'version': '18.0.1.0.0',
    'depends': ['sale_management', 'purchase'],
    'installable': True,
    'application': False,
    'data': [
        'security/ir.model.access.csv',
        'security/security.xml',
        'data/data.xml',
        'views/sale_discount_rule_views.xml',
        'views/sale_order_views.xml',
        'views/purchase_order_views.xml',
        'views/wizard_views.xml',
        'report/profitability_report_template.xml',
        'report/report_actions.xml'

    ],
}
