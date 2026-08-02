#!/usr/bin/env bash
# Re-download every raw framework source RegMap can legally obtain.
# See data/raw/SOURCES.md for licences and for the frameworks that CANNOT be downloaded
# (ISO 27001, PCI DSS, SOC 2, CIS, HITRUST, COBIT — these need purchase or a licence).
#
#   bash scripts/fetch_frameworks.sh
#
# Idempotent: re-running overwrites with fresh copies. Run from the repo root.
set -euo pipefail

OUT="data/raw/oscal"
OSCAL="https://raw.githubusercontent.com/usnistgov/oscal-content/main/nist.gov"
mkdir -p "$OUT"

get() {  # get <url> <destination>
  printf '  %-38s ' "$(basename "$2")"
  if curl -fsSL --max-time 300 -o "$2" "$1"; then
    printf '%7.2f MB\n' "$(awk -v b="$(wc -c < "$2")" 'BEGIN{print b/1048576}')"
  else
    printf 'FAILED (%s)\n' "$1" >&2; return 1
  fi
}

echo "NIST OSCAL control catalogues (public domain)"
get "$OSCAL/SP800-53/rev5/json/NIST_SP-800-53_rev5_catalog-min.json"   "$OUT/nist_80053_rev5.json"
get "$OSCAL/CSF/v2.0/json/NIST_CSF_v2.0_catalog-min.json"              "$OUT/nist_csf2.json"
get "$OSCAL/SP800-171/rev3/json/NIST_SP800-171_rev3_catalog-min.json"  "$OUT/nist_80171_rev3.json"
get "$OSCAL/SP800-172/rev3/json/NIST_SP800-172_rev3_catalog-min.json"  "$OUT/nist_80172_rev3.json"
get "$OSCAL/SP800-218/ver1/json/NIST_SP800-218_ver1_catalog-min.json"  "$OUT/nist_ssdf.json"

echo "800-53 Rev 5 baselines (OSCAL profiles)"
for lvl in LOW MODERATE HIGH PRIVACY; do
  get "$OSCAL/SP800-53/rev5/json/NIST_SP-800-53_rev5_${lvl}-baseline_profile.json" \
      "$OUT/nist_80053_baseline_$(echo "$lvl" | tr '[:upper:]' '[:lower:]').json"
done

echo "Crosswalks"
# NOTE: this URL says "json" but serves an XLSX workbook.
get "https://csrc.nist.gov/extensions/nudp/services/json/csf/download?olirids=all" \
    "$OUT/csf_olir_all.xlsx"
get "https://csrc.nist.gov/files/pubs/sp/800/53/r5/upd1/final/docs/csf-pf-to-sp800-53r5-mappings.xlsx" \
    "$OUT/csf_pf_to_80053r5.xlsx"

echo
echo "Done. The 800-53 <-> HIPAA OLIR export already lives in data/raw/ and is not re-fetched."
echo "Cannot be downloaded (licence/purchase): ISO 27001, PCI DSS, SOC 2, CIS, HITRUST, COBIT."
echo "See data/raw/SOURCES.md."
