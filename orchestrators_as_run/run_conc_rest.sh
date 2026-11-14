#!/bin/bash
# Resume the concurrency full run (all six models; Sonnet/Fable/Gemini via batch). Resumable.
cd "$(dirname "$0")" || exit 1
exec bash src4_batch/run_rest_next.sh "$@"
