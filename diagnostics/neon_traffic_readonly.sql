-- Optional operator diagnostics only. Not executed by this PR or its tests.
-- Returns sizes, not the photo JSON or credentials. No data modifications.
SELECT current_database() AS database_name;
SELECT key, octet_length(value::text) AS json_utf8_bytes,
       CASE WHEN jsonb_typeof(value::jsonb)='array'
            THEN jsonb_array_length(value::jsonb) END AS array_items
FROM public.allegro_state
WHERE key IN ('analysis','prices','komertia_import_log')
ORDER BY key;
