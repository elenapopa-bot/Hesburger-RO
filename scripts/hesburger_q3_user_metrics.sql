-- Hesburger RO — Q3 customer counts (distinct eater / user_id on delivered orders)
-- Run in Databricks SQL (Bolt). Paste results into ~/.hesburger_ro_env:
--   export HESBURGER_Q3_ACTIVE_USERS=<active_users_q3>
--   export HESBURGER_Q3_NEW_USERS=<new_to_brand_q3>
-- Then re-run hesburger_ro_update.py

SELECT
  COUNT(DISTINCT user_id) AS active_users_q3,
  COUNT(DISTINCT CASE WHEN is_first_brand_order THEN user_id END) AS new_to_brand_q3,
  COUNT(*) AS delivered_orders_q3
FROM main.ng_delivery.dim_order_delivery
WHERE order_state = 'delivered'
  AND provider_id IN (
    135579, 135580, 135581, 135582, 135583,
    154770, 154778, 155192, 170143, 172927, 173425,
    190389, 802700, 4522627
  )
  AND order_delivered_ts >= TIMESTAMP '2026-07-01'
  AND order_delivered_ts < TIMESTAMP '2026-10-01';

-- Optional: monthly view (each month's uniques — do NOT sum months for quarterly uniques)
SELECT
  DATE_TRUNC('month', order_delivered_ts) AS month,
  COUNT(DISTINCT user_id) AS active_users,
  COUNT(DISTINCT CASE WHEN is_first_brand_order THEN user_id END) AS new_to_brand
FROM main.ng_delivery.dim_order_delivery
WHERE order_state = 'delivered'
  AND provider_id IN (
    135579, 135580, 135581, 135582, 135583,
    154770, 154778, 155192, 170143, 172927, 173425,
    190389, 802700, 4522627
  )
  AND order_delivered_ts >= TIMESTAMP '2026-07-01'
  AND order_delivered_ts < TIMESTAMP '2026-10-01'
GROUP BY 1
ORDER BY 1;