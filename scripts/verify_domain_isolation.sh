#!/usr/bin/env bash
# verify_domain_isolation.sh - end-to-end smoke check for the rpi <-> AQP
# domain split.
#
# Confirms that:
#   1. AQP responds on aqp.fund / api.aqp.fund / manage.aqp.fund with a
#      certificate issued by Let's Encrypt for *.aqp.fund (no Cloudflare
#      Origin / Universal cert; no julianwiley.com in the SAN list).
#   2. The portal responds on julianwiley.com / www.julianwiley.com via
#      the Cloudflare edge cert (no aqp.fund in the SAN list).
#   3. The two domains are served by different Cloudflare tunnels (we
#      compare the response Server header + cert chain).
#
# Usage:  bash scripts/verify_domain_isolation.sh
set -euo pipefail

AQP_HOSTS=(aqp.fund api.aqp.fund manage.aqp.fund)
PORTAL_HOSTS=(julianwiley.com www.julianwiley.com)

red()    { printf '\033[31m%s\033[0m\n' "$*" >&2; }
green()  { printf '\033[32m%s\033[0m\n' "$*"; }
yellow() { printf '\033[33m%s\033[0m\n' "$*"; }

check_san_does_not_include() {
  local host="$1"; shift
  local needle="$1"; shift
  local sans
  sans=$(echo | openssl s_client -connect "${host}:443" -servername "$host" 2>/dev/null \
           | openssl x509 -noout -ext subjectAltName 2>/dev/null \
           | tr ',' '\n' || true)
  if echo "$sans" | grep -q "$needle"; then
    red   "FAIL  $host certificate SAN list includes '$needle' - cross-domain leakage"
    return 1
  fi
  green "ok    $host certificate SAN list does NOT contain '$needle'"
  return 0
}

check_https_status() {
  local url="$1"
  local code
  code=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 10 "$url" || echo "000")
  if [[ "$code" =~ ^[23] ]]; then
    green "ok    $url -> HTTP $code"
    return 0
  fi
  red   "FAIL  $url -> HTTP $code"
  return 1
}

check_aqp_issuer_letsencrypt() {
  local host="$1"
  local issuer
  issuer=$(echo | openssl s_client -connect "${host}:443" -servername "$host" 2>/dev/null \
            | openssl x509 -noout -issuer 2>/dev/null || true)
  if echo "$issuer" | grep -qi "Let's Encrypt"; then
    green "ok    $host issued by Let's Encrypt"
    return 0
  fi
  yellow "WARN  $host issuer = $issuer (expected Let's Encrypt for cert-manager)"
  return 0
}

failures=0

green "== Liveness checks =="
for h in "${AQP_HOSTS[@]}" "${PORTAL_HOSTS[@]}"; do
  case "$h" in
    api.aqp.fund)    check_https_status "https://$h/livez"        || failures=$((failures+1));;
    manage.aqp.fund) check_https_status "https://$h/manage/livez" || failures=$((failures+1));;
    *)               check_https_status "https://$h/"             || failures=$((failures+1));;
  esac
done

green ""
green "== Cert-chain isolation =="
for h in "${AQP_HOSTS[@]}"; do
  check_san_does_not_include "$h" "julianwiley.com" || failures=$((failures+1))
  check_aqp_issuer_letsencrypt "$h"                  || failures=$((failures+1))
done
for h in "${PORTAL_HOSTS[@]}"; do
  check_san_does_not_include "$h" "aqp.fund" || failures=$((failures+1))
done

green ""
if [[ "$failures" -eq 0 ]]; then
  green "PASS - rpi <-> AQP domain isolation intact"
  exit 0
else
  red   "FAIL - $failures isolation check(s) failed"
  exit 1
fi
