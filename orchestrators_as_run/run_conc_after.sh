#!/bin/bash
# Waits for the concurrency run that is going now, then runs Gemini (Google batch) and the SQL test.
cd "$(dirname "$0")" || exit 1
exec bash src4_batch/run_everything_after.sh "$@"
