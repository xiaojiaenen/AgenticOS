CREATE TABLE IF NOT EXISTS ${database}.${table_name} (
  ${columns}
)
ENGINE=OLAP
UNIQUE KEY(${unique_keys})
PARTITION BY RANGE(${partition_column}) ()
DISTRIBUTED BY HASH(${distribution_columns}) BUCKETS ${bucket_count}
PROPERTIES (
  "replication_num" = "1"
);
