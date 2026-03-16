# Appsgate
# Odoo Technical Assessment Module

**Odoo Version:** 17.0 / 18.0

## Overview
This custom Odoo module implements four key business customizations covering
Sales, Purchase, Accounting, and Reporting functionalities as part of a
technical assessment.

---

## Features

### 1. Dynamic Sales Discount Rules Engine (Sales Customization)
- New model `sale.discount.rule` with fields:
  - `min_amount`, `max_amount`, `discount_percent`, `customer_group`,
    `valid_from`, `valid_to`
- Automatically applies the most relevant discount on `sale.order` creation
- "Reapply Discount" button to recalculate if order lines change
- If multiple rules match, the **highest discount** is applied

### 2. Three-Level Purchase Approval Workflow (Purchase Customization)
- Extended `purchase.order` with additional states:
  - `draft` → `to_approve` → `approved_level1` → `approved_level2` → `purchase`
- Approval levels based on order amount:
  | Amount Range     | Approval Level   |
  |------------------|------------------|
  | ≤ 5,000          | Auto-approved    |
  | 5,001 – 20,000   | Level 1 Approval |
  | > 20,000          | Level 2 Approval |
- Group-based access control for each approval level
- Email notifications sent at each approval stage

### 3. Custom Accounting Entries for Advance Payments (Accounting Extension)
- New `advance_payment` field on `sale.order`
- On order confirmation, a **manual journal entry** is auto-generated:
  - **Debit:** Customer Receivable
  - **Credit:** Advance Received
- Journal entry is linked to the sale order
- Activity logged in the chatter

### 4. Sales Profitability Report (Custom Reporting)
- Wizard-based report showing:
  - Order-wise **Revenue**, **Cost**, and **Profit Margin**
- Filters available:
  - Date range
  - Product category
  - Customer
- **Export to Excel** and **Print via QWeb PDF**

---
