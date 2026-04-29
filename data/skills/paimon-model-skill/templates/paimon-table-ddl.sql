CREATE TABLE IF NOT EXISTS ${catalog}.${database}.${table_name} (
  ${columns}
)
PARTITIONED BY (${partition_columns})
WITH (
  'bucket' = '${bucket_count}',
  'merge-engine' = '${merge_engine}'
);
