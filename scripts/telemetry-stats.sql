-- Queries behind the telemetry infographic. Run against the homgar-telemetry D1
-- database (id 490d05e8-9fe0-4314-a3c6-007c2c21470d, repo: homgar-telemetry-worker)
-- via the Cloudflare MCP d1_database_query tool, or `wrangler d1 execute`.
--
-- Schema notes that matter when reading the output:
--   * installs.last_seen / first_seen are DATES, never timestamps.
--   * country_counts and model_counts have NO anon_id by design, so a model
--     count is install-MONTHS claiming that model, not distinct users. Do not
--     present it as a user count.

-- 1. Headline install numbers.
SELECT COUNT(*) AS installs,
       SUM(CASE WHEN last_seen  >= date('now','-7 day')  THEN 1 ELSE 0 END) AS active_7d,
       SUM(CASE WHEN last_seen  >= date('now','-30 day') THEN 1 ELSE 0 END) AS active_30d,
       SUM(CASE WHEN first_seen >= date('now','-7 day')  THEN 1 ELSE 0 END) AS new_7d,
       MIN(first_seen) AS first_ping,
       MAX(last_seen)  AS latest_ping
FROM installs;

-- 2. Totals for the hero cards. Count the ROWS for distinct countries/models;
--    counting the unioned result of query 4 by eye gets this wrong.
SELECT
 (SELECT COUNT(*)   FROM country_counts WHERE month=strftime('%Y-%m','now')) AS countries,
 (SELECT SUM(count) FROM country_counts WHERE month=strftime('%Y-%m','now')) AS country_sharers,
 (SELECT COUNT(*)   FROM model_counts   WHERE month=strftime('%Y-%m','now')) AS distinct_models,
 (SELECT SUM(count) FROM model_counts   WHERE month=strftime('%Y-%m','now')) AS model_pairs,
 (SELECT COUNT(*)   FROM model_counts   WHERE month=strftime('%Y-%m','now') AND count<=2) AS models_le2,
 (SELECT COUNT(DISTINCT hass_version) FROM pings WHERE day>=date('now','-7 day')) AS hass_versions;

-- 3. Integration version adoption. Versions overlap because an install that
--    updated mid-window pings under both.
SELECT integration_version, COUNT(DISTINCT anon_id) AS installs
FROM pings WHERE day >= date('now','-3 day')
GROUP BY integration_version ORDER BY installs DESC;

-- 4. Home Assistant version spread.
SELECT hass_version, COUNT(DISTINCT anon_id) AS n
FROM pings WHERE day >= date('now','-7 day')
GROUP BY hass_version ORDER BY n DESC;

-- 5. The two bar charts.
SELECT country, count FROM country_counts
WHERE month = strftime('%Y-%m','now') ORDER BY count DESC;

SELECT model, count FROM model_counts
WHERE month = strftime('%Y-%m','now') ORDER BY count DESC;
