# Agent Work Plan - Retail Sales Analytics

## Business Context

**Project:** Retail Sales Analytics DW - Phase 1  
**Domain:** Retail Sales & E-commerce  
**Purpose:** Build dimensional warehouse for sales performance tracking, customer behavior analysis, and product profitability insights

**Primary Objective:** Enable data-driven sales decisions and improve revenue forecasting

**Key Business Questions:**
- Daily/weekly/monthly sales performance vs targets
- Customer segmentation and loyalty tier progression
- Product category performance and profitability
- Regional sales trends and resource allocation

## Target Metrics

**Business KPIs:**
- Total Sales Revenue: `SUM(total_amount)` by time period
- Average Transaction Value: `SUM(total_amount) / COUNT(transaction_id)`
- Customer Lifetime Value by Loyalty Tier: `SUM(total_amount)` per customer grouped by loyalty_tier
- Product Profitability: `(unit_price - unit_cost) * quantity` by category

**Data Quality Requirements:**
- Zero nulls in PK/FK fields (transaction_id, customer_id, product_id)
- All keys must be unique and present
- 100% source coverage and target column mapping

## Source Systems

**Location:** `data/sources/` (CSV files)

Agents will discover and analyze all available source files in this directory.

## Business Grain and Scope

**Business Process:** Retail sales transactions  
**Fact Grain:** One row per transaction (transaction_id level)

**In-Scope Dimensions:**
- `dim_customer` - demographics, loyalty tier
- `dim_product` - attributes, category, pricing
- `dim_calendar` - date attributes for time-series analysis
- `dim_store` - store identifier, region (optional/degenerate)
- `dim_payment_method` - payment type (optional/degenerate)

**Out of Scope (Phase 1):**
- Inventory snapshots, returns/refunds, promotions, employee attribution, real-time streaming

## Governance and Compliance

**Critical Fields:** transaction_id (PK), customer_id (FK), product_id (FK), date, total_amount  
**PII Fields:** customer_name, email (mask/encrypt for production)  
**Retention:** 7 years (regulatory compliance)  
**Naming Standards:** `fact_*` and `dim_*`  
**Auditability:** Document all transformations and business logic in mapping JSON

## Assumptions and Constraints

**Technical:** ANSI SQL DDL for SQL Server or PostgreSQL  
**Data Limitations:** 
- Sample dataset (7 transactions); production will scale to millions
- SCD Type 0 (no historical tracking)
- Store dimension needs enrichment (only store_id and region available)
- Product unit_cost may be incomplete in production sources