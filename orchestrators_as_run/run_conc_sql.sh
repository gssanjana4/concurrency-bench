#!/bin/bash
# The small real-database SQL test (~$5 cap). Refuses while a concurrency run process is going.
cd "$(dirname "$0")" || exit 1
ALLOW_SQL_BEFORE_FULL_DONE=1 exec bash src_sql/run_sql.sh "$@"
