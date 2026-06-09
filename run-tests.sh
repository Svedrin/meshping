#!/bin/bash
set -e
set -u

woodpecker-cli exec --pipeline-event push --commit-branch master --repo-path "$PWD" .woodpecker/tests.yaml
echo "Result: $?"
