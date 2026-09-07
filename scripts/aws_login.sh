#!/usr/bin/env bash
# Log in to AWS via SSO and export AWS_PROFILE for the current shell.
#
# Usage:
#   source scripts/aws_login.sh [profile]
#
# Must be sourced (not executed) so AWS_PROFILE persists in your shell.

set -euo pipefail

PROFILE="${1:-PowerUserAccess-341738847855}"

aws sso login --profile "$PROFILE" --use-device-code

export AWS_PROFILE="$PROFILE"
echo "AWS_PROFILE set to $AWS_PROFILE"
