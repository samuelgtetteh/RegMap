#!/usr/bin/env bash
# Production-grade smoke test against a DEPLOYED RegMap container.
#
# Treats the service as a black box over HTTP — no imports, no reaching into the working tree — so it
# tests what a customer would actually hit. Exercises auth, the ledger, deterministic billing, quotas,
# rate limits, admin gating, and (the one that matters most for SQLite) **ledger durability across a
# container restart**.
#
#   bash scripts/smoke_test.sh                      # builds nothing; uses regmap-engine:0.4-cpu
#   IMAGE=regmap-engine:0.4-cpu PORT=8200 bash scripts/smoke_test.sh
#
# Leaves nothing behind: the container and its volume are removed on exit.
set -uo pipefail

# Git Bash on Windows rewrites POSIX-looking arguments into Windows paths, so a container path such as
# /app/scripts/regmap_admin.py arrives at `docker exec` as C:/Program Files/Git/app/... and the command
# fails. These disable that conversion; both are ignored on Linux and macOS.
export MSYS_NO_PATHCONV=1
export MSYS2_ARG_CONV_EXCL='*'

IMAGE="${IMAGE:-regmap-engine:0.4-cpu}"
PORT="${PORT:-8200}"
NAME="regmap-smoke-$$"
VOL="regmap-smoke-vol-$$"
B="http://localhost:$PORT"

pass=0; fail=0
ok()  { printf '  \033[32mPASS\033[0m  %s\n' "$1"; pass=$((pass+1)); }
bad() { printf '  \033[31mFAIL\033[0m  %s\n' "$1"; fail=$((fail+1)); }
hdr() { printf '\n\033[1m== %s\033[0m\n' "$1"; }
# eq <label> <expected> <actual>
eq()  { [ "$2" = "$3" ] && ok "$1 ($3)" || bad "$1 — expected $2, got $3"; }
code(){ curl -s -o /dev/null -w '%{http_code}' "$@"; }

cleanup() {
  docker rm -f "$NAME" >/dev/null 2>&1
  docker volume rm "$VOL" >/dev/null 2>&1
}
trap cleanup EXIT

hdr "boot $IMAGE with a durable ledger volume"
docker image inspect "$IMAGE" >/dev/null 2>&1 || { echo "  image $IMAGE not found — build it first"; exit 1; }
docker volume create "$VOL" >/dev/null
docker run -d --name "$NAME" -p "$PORT:8000" -v "$VOL:/data" \
  -e REGMAP_REQUIRE_AUTH=true -e REGMAP_RATE_EVAL=4 "$IMAGE" >/dev/null
for _ in $(seq 1 60); do sleep 3; [ "$(code "$B/health")" = "200" ] && break; done
[ "$(code "$B/health")" = "200" ] && ok "container serving on :$PORT" || { bad "container never became healthy"; docker logs "$NAME" | tail -20; exit 1; }

# The ledger ships empty, so accounts are created through the operator CLI inside the container.
hdr "provision an account and keys (operator CLI, in-container)"
ACCT=$(docker exec "$NAME" python /app/scripts/regmap_admin.py account create \
        --email smoke@example.com --plan free 2>/dev/null | head -1 | awk '{print $3}')
[ -n "${ACCT:-}" ] && ok "account created ($ACCT)" || bad "could not create an account"
KEY=$(docker exec "$NAME" python /app/scripts/regmap_admin.py key create --account "$ACCT" \
       --label smoke 2>/dev/null | grep -oE 'rk_[A-Za-z0-9_-]+' | head -1)
AKEY=$(docker exec "$NAME" python /app/scripts/regmap_admin.py key create --account "$ACCT" \
        --label ops --scopes admin 2>/dev/null | grep -oE 'rk_[A-Za-z0-9_-]+' | head -1)
[ -n "${KEY:-}" ] && ok "user key issued" || bad "no user key"
[ -n "${AKEY:-}" ] && ok "admin key issued" || bad "no admin key"

AUTH="Authorization: Bearer $KEY"
AADM="Authorization: Bearer $AKEY"
JSON='content-type: application/json'
MAP='{"source":"nist_80053","source_id":"AC-1","target":"hipaa_security","top_k":5}'

hdr "authentication"
eq "/map with no key is rejected"      401 "$(code -X POST $B/map -H "$JSON" -d "$MAP")"
eq "/map with a bogus key is rejected" 401 "$(code -X POST $B/map -H 'Authorization: Bearer rk_nope' -H "$JSON" -d "$MAP")"
eq "/map with a valid key succeeds"    200 "$(code -X POST $B/map -H "$AUTH" -H "$JSON" -d "$MAP")"
eq "X-API-Key header also accepted"    200 "$(code -X POST $B/map -H "X-API-Key: $KEY" -H "$JSON" -d "$MAP")"

hdr "public surface stays public (k8s probes depend on it)"
eq "/health open"    200 "$(code $B/health)"
eq "/pricing open"   200 "$(code $B/pricing)"
eq "/frameworks open" 200 "$(code $B/frameworks)"
body=$(curl -s $B/health)
[ "$body" = '{"status":"ok"}' ] && ok "/health leaks nothing ($body)" \
  || bad "/health exposes internals: $body"

hdr "admin surface is gated"
eq "/health/detail rejects a non-admin key" 403 "$(code $B/health/detail -H "$AUTH")"
eq "/health/detail accepts the admin key"   200 "$(code $B/health/detail -H "$AADM")"
eq "/docs rejects anonymous"                401 "$(code $B/docs)"
eq "/docs accepts the admin key"            200 "$(code $B/docs -H "$AADM")"
eq "/usage rejects a non-admin key"         403 "$(code $B/usage -H "$AUTH")"
eq "/admin/accounts rejects a non-admin"    403 "$(code $B/admin/accounts -H "$AUTH")"
eq "/admin/accounts accepts admin"          200 "$(code $B/admin/accounts -H "$AADM")"

hdr "billing is deterministic (the invoice guarantee)"
cus=""
for _ in 1 2 3; do
  cus="$cus $(curl -s -D - -o /dev/null -X POST $B/map -H "$AUTH" -H "$JSON" -d "$MAP" \
            | grep -i '^x-regmap-compute-units' | tr -d '\r' | awk '{print $2}')"
done
uniq_n=$(echo $cus | tr ' ' '\n' | sort -u | grep -c .)
[ "$uniq_n" = "1" ] && ok "same request billed identically 3x ($(echo $cus | awk '{print $1}') CU)" \
  || bad "charge varied across identical requests:$cus"

small=$(curl -s -D - -o /dev/null -X POST $B/map -H "$AUTH" -H "$JSON" \
        -d '{"text":"x","target":"hipaa_security"}' | grep -i '^x-regmap-compute-units' | tr -d '\r' | awk '{print $2}')
large=$(curl -s -D - -o /dev/null -X POST $B/map -H "$AUTH" -H "$JSON" \
        -d '{"text":"x","target":"nist_80053"}' | grep -i '^x-regmap-compute-units' | tr -d '\r' | awk '{print $2}')
awk -v a="$small" -v b="$large" 'BEGIN{exit !(b>a)}' \
  && ok "charge scales with corpus size (60 ctl $small CU < 1016 ctl $large CU)" \
  || bad "charge did not scale with corpus ($small vs $large)"

acct_hdr=$(curl -s -D - -o /dev/null -X POST $B/map -H "$AUTH" -H "$JSON" -d "$MAP" \
           | grep -i '^x-regmap-account' | tr -d '\r' | awk '{print $2}')
[ "$acct_hdr" = "$ACCT" ] && ok "usage attributed to the account ($acct_hdr)" \
  || bad "wrong account on the charge: $acct_hdr"

hdr "the ledger records it"
before=$(curl -s $B/me -H "$AUTH" | python -c 'import json,sys;print(json.load(sys.stdin)["usage"]["compute_units"])')
curl -s -o /dev/null -X POST $B/map -H "$AUTH" -H "$JSON" -d "$MAP"
after=$(curl -s $B/me -H "$AUTH" | python -c 'import json,sys;print(json.load(sys.stdin)["usage"]["compute_units"])')
awk -v a="$before" -v b="$after" 'BEGIN{exit !(b>a)}' \
  && ok "/me usage increased ($before -> $after CU)" || bad "/me usage did not move ($before -> $after)"
curl -s $B/me -H "$AUTH" | grep -q key_hash && bad "/me leaks key_hash" || ok "/me never exposes key_hash"

hdr "quota is enforced BEFORE the work runs"
docker exec "$NAME" python -c "
import sys; sys.path.insert(0,'/app/regmap_engine')
import billing
from sqlalchemy import update
with billing.engine().begin() as c:
    c.execute(update(billing.usage_periods)
              .where(billing.usage_periods.c.account_id=='$ACCT').values(compute_units=299.9))
" >/dev/null 2>&1
eq "over-quota request rejected with 402" 402 "$(code -X POST $B/map -H "$AUTH" -H "$JSON" -d "$MAP")"
used=$(docker exec "$NAME" python -c "
import sys; sys.path.insert(0,'/app/regmap_engine')
import billing; print(billing.period_usage('$ACCT')['compute_units'])" 2>/dev/null | tr -d '\r')
[ "$used" = "299.9" ] && ok "the rejected request consumed nothing (still $used CU)" \
  || bad "a rejected request was still billed (now $used CU)"

hdr "rate limiting"
docker exec "$NAME" python -c "
import sys; sys.path.insert(0,'/app/regmap_engine')
import billing
from sqlalchemy import update
with billing.engine().begin() as c:
    c.execute(update(billing.usage_periods)
              .where(billing.usage_periods.c.account_id=='$ACCT').values(compute_units=0.0))
" >/dev/null 2>&1
last=""
for _ in 1 2 3 4 5 6; do
  last=$(code -X POST $B/eval -H "$AADM" -H "$JSON" -d '{"source":"nist_csf2","target":"nist_ssdf"}')
done
eq "/eval limited after 4 calls/min" 429 "$last"
ra=$(curl -s -D - -o /dev/null -X POST $B/eval -H "$AADM" -H "$JSON" \
     -d '{"source":"nist_csf2","target":"nist_ssdf"}' | grep -i '^retry-after' | tr -d '\r' | awk '{print $2}')
[ -n "${ra:-}" ] && ok "429 carries Retry-After ($ra s)" || bad "429 without Retry-After"

hdr "DURABILITY — does the ledger survive a restart? (the SQLite question)"
pre=$(docker exec "$NAME" python -c "
import sys; sys.path.insert(0,'/app/regmap_engine')
import billing; u=billing.period_usage('$ACCT'); print(f\"{u['compute_units']}|{u['requests']}\")" 2>/dev/null | tr -d '\r')
docker restart "$NAME" >/dev/null
for _ in $(seq 1 60); do sleep 3; [ "$(code "$B/health")" = "200" ] && break; done
post=$(docker exec "$NAME" python -c "
import sys; sys.path.insert(0,'/app/regmap_engine')
import billing; u=billing.period_usage('$ACCT'); print(f\"{u['compute_units']}|{u['requests']}\")" 2>/dev/null | tr -d '\r')
[ "$pre" = "$post" ] && ok "ledger survived the restart ($post cu|requests)" \
  || bad "LEDGER LOST DATA across restart: before=$pre after=$post"
eq "the key still authenticates after restart" 200 "$(code -X POST $B/map -H "$AUTH" -H "$JSON" -d "$MAP")"

hdr "reconciliation — events are the source of truth"
docker exec "$NAME" python -c "
import sys; sys.path.insert(0,'/app/regmap_engine')
import billing
from sqlalchemy import update
with billing.engine().begin() as c:
    c.execute(update(billing.usage_periods)
              .where(billing.usage_periods.c.account_id=='$ACCT').values(compute_units=99999.0))
" >/dev/null 2>&1
rec=$(docker exec "$NAME" python /app/scripts/regmap_admin.py reconcile --account "$ACCT" \
      --period "$(date -u +%Y-%m)" 2>/dev/null | tr -d '\r')
echo "$rec" | grep -q "drifted" && ok "corrupted counter rebuilt from the event log" \
  || bad "reconciliation did not detect the drift"
echo "$rec" | sed 's|^|      |'

hdr "product surfaces respond"
for p in / /crosswalk.html /gaps.html /learn.html /frameworks.html /deploy.html; do
  eq "page $p" 200 "$(code "$B$p")"
done
eq "graded exercise can be set"  200 "$(code -X POST $B/exercise -H "$AUTH" -H "$JSON" \
  -d '{"source":"nist_80053","target":"hipaa_security"}')"
eq "bulk gap analysis runs"      200 "$(code -X POST $B/map/bulk -H "$AUTH" -H "$JSON" \
  -d '{"source":"hipaa_security","target":"nist_80053"}')"

hdr "revocation"
KID=$(docker exec "$NAME" python -c "
import sys; sys.path.insert(0,'/app/regmap_engine')
import billing
from sqlalchemy import select
with billing.engine().begin() as c:
    r=c.execute(select(billing.api_keys.c.id)
                .where(billing.api_keys.c.key_hash==billing._hash('$KEY'))).first()
print(r[0])" 2>/dev/null | tr -d '\r')
docker exec "$NAME" python /app/scripts/regmap_admin.py key revoke --key "$KID" >/dev/null 2>&1
eq "a revoked key is refused" 401 "$(code -X POST $B/map -H "$AUTH" -H "$JSON" -d "$MAP")"

printf '\n\033[1m== %s passed, %s failed\033[0m\n' "$pass" "$fail"
echo "   Not covered: Postgres, GPU, payment capture, multi-replica behaviour."
exit $(( fail > 0 ))
