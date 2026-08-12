#!/bin/sh
set -eu
: "${API_UPSTREAM:=api:8000}"
envsubst '${API_UPSTREAM}' < /etc/nginx/templates/default.conf.template \
  > /etc/nginx/conf.d/default.conf
exec nginx -g 'daemon off;'
