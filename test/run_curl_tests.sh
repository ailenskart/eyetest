#!/bin/bash
# Run curl commands from curl_API.md against preprod API
# Phoropter ID: lkst1782-1

BASE_URL="https://rajasthan-royals.preprod.lenskart.com"
PID="lkst1782-1"
BRAIN_ID="brain_curl_test"
PASS=0
FAIL=0

check() {
  local name="$1"
  local code="$2"
  if [ "$code" = "200" ]; then
    echo "✓ $name: $code PASS"
    ((PASS++))
    return 0
  else
    echo "✗ $name: $code FAIL"
    ((FAIL++))
    return 1
  fi
}

echo "=== Phoropter API Tests (curl_API.md) ==="
echo "Base: $BASE_URL | Phoropter: $PID"
echo ""

# Device Management
check "D1: List devices" "$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/devices")"
check "D2: List devices (all)" "$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/devices?all=true")"
check "D3: Get single device" "$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/devices/$PID")"
check "D4: List active brains" "$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/brains")"
check "D5: Connection events" "$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/events?limit=20")"

# Acquire device (required for phoropter commands)
ACQUIRE_BODY="{\"brain_id\": \"$BRAIN_ID\", \"name\": \"Curl Test Suite\"}"
check "D6: Acquire device" "$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/devices/$PID/acquire" \
  -H "Content-Type: application/json" \
  -d "$ACQUIRE_BODY")"

# Phoropter commands (only work after acquire)
check "P1: Reset" "$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/phoropter/$PID/reset")"
check "P2: Pinhole" "$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/phoropter/$PID/pinhole")"
check "P3: Occluder" "$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/phoropter/$PID/occluder")"
check "P4: Sync state" "$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/phoropter/$PID/sync-state" \
  -H "Content-Type: application/json" \
  -d '{"right_eye":{"sph":-2,"cyl":-1,"axis":90},"left_eye":{"sph":-1.75,"cyl":-1,"axis":180},"aux_lens":"BINO","pd":64}')"

# Run-tests: Power
check "R1: Preload AR/Lenso" "$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/phoropter/$PID/run-tests" \
  -H "Content-Type: application/json" \
  -d '{"test_cases":[{"case_id":1,"aux_lens":"BINO","right_eye":{"sph":-2,"cyl":-1,"axis":90},"left_eye":{"sph":-1.75,"cyl":-1,"axis":180}}]}')"
check "R2: Set power + aux_lens" "$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/phoropter/$PID/run-tests" \
  -H "Content-Type: application/json" \
  -d '{"test_cases":[{"case_id":1,"aux_lens":"AuxLensL","right_eye":{"sph":-2,"cyl":-1,"axis":90},"left_eye":{"sph":-1.75,"cyl":-1,"axis":180}}]}')"
check "R3: Power with prev_state" "$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/phoropter/$PID/run-tests" \
  -H "Content-Type: application/json" \
  -d '{"test_cases":[{"case_id":1,"prev_aux_lens":"BINO","prev_right_eye":{"sph":0,"cyl":0,"axis":180},"prev_left_eye":{"sph":0,"cyl":0,"axis":180},"aux_lens":"AuxLensL","right_eye":{"sph":-2,"cyl":-1,"axis":90},"left_eye":{"sph":-1.75,"cyl":-1,"axis":180}}]}')"

# JCC
check "J1: JCC handle" "$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/phoropter/$PID/run-tests" \
  -H "Content-Type: application/json" -d '{"test_cases":[{"jcc":"handle"}]}')"
check "J2: JCC power_axis_switch" "$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/phoropter/$PID/run-tests" \
  -H "Content-Type: application/json" -d '{"test_cases":[{"jcc":"power_axis_switch"}]}')"
check "J3: JCC increase" "$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/phoropter/$PID/run-tests" \
  -H "Content-Type: application/json" -d '{"test_cases":[{"jcc":"increase"}]}')"
check "J4: JCC decrease" "$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/phoropter/$PID/run-tests" \
  -H "Content-Type: application/json" -d '{"test_cases":[{"jcc":"decrease"}]}')"
check "J5: JCC mode R" "$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/phoropter/$PID/run-tests" \
  -H "Content-Type: application/json" -d '{"test_cases":[{"jcc":"R"}]}')"
check "J6: JCC mode L" "$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/phoropter/$PID/run-tests" \
  -H "Content-Type: application/json" -d '{"test_cases":[{"jcc":"L"}]}')"
check "J7: JCC mode BINO" "$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/phoropter/$PID/run-tests" \
  -H "Content-Type: application/json" -d '{"test_cases":[{"jcc":"BINO"}]}')"

# Charts
check "C1: Chart1 echart_400" "$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/phoropter/$PID/run-tests" \
  -H "Content-Type: application/json" -d '{"test_cases":[{"chart":{"tab":"Chart1","chart_items":["chart_9"]}}]}')"
check "C2: Chart1 snellen_200_150" "$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/phoropter/$PID/run-tests" \
  -H "Content-Type: application/json" -d '{"test_cases":[{"chart":{"tab":"Chart1","chart_items":["chart_10"]}}]}')"
check "C3: Chart1 snellen_100_80" "$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/phoropter/$PID/run-tests" \
  -H "Content-Type: application/json" -d '{"test_cases":[{"chart":{"tab":"Chart1","chart_items":["chart_11"]}}]}')"
check "C4: Chart1 snellen_70_60_50" "$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/phoropter/$PID/run-tests" \
  -H "Content-Type: application/json" -d '{"test_cases":[{"chart":{"tab":"Chart1","chart_items":["chart_12"]}}]}')"
check "C5: Chart1 snellen_40_30_25" "$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/phoropter/$PID/run-tests" \
  -H "Content-Type: application/json" -d '{"test_cases":[{"chart":{"tab":"Chart1","chart_items":["chart_13"]}}]}')"
check "C6: Chart1 snellen_20_15_10" "$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/phoropter/$PID/run-tests" \
  -H "Content-Type: application/json" -d '{"test_cases":[{"chart":{"tab":"Chart1","chart_items":["chart_14"]}}]}')"
check "C7: Chart1 snellen_20_20_20" "$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/phoropter/$PID/run-tests" \
  -H "Content-Type: application/json" -d '{"test_cases":[{"chart":{"tab":"Chart1","chart_items":["chart_15"]}}]}')"
check "C8: Chart1 snellen_25_20_15" "$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/phoropter/$PID/run-tests" \
  -H "Content-Type: application/json" -d '{"test_cases":[{"chart":{"tab":"Chart1","chart_items":["chart_16"]}}]}')"
check "C9: Chart1 duochrome" "$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/phoropter/$PID/run-tests" \
  -H "Content-Type: application/json" -d '{"test_cases":[{"chart":{"tab":"Chart1","chart_items":["chart_17"]}}]}')"
check "C10: Chart1 jcc_chart" "$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/phoropter/$PID/run-tests" \
  -H "Content-Type: application/json" -d '{"test_cases":[{"chart":{"tab":"Chart1","chart_items":["chart_19"]}}]}')"
check "C11: Chart1 bino_chart" "$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/phoropter/$PID/run-tests" \
  -H "Content-Type: application/json" -d '{"test_cases":[{"chart":{"tab":"Chart1","chart_items":["chart_20"]}}]}')"
check "C12: Chart2 chart_1,2,3" "$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/phoropter/$PID/run-tests" \
  -H "Content-Type: application/json" -d '{"test_cases":[{"chart":{"tab":"Chart2","chart_items":["chart_1","chart_2","chart_3"]}}]}')"
check "C13: Chart5 near vision" "$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/phoropter/$PID/run-tests" \
  -H "Content-Type: application/json" -d '{"test_cases":[{"chart":{"tab":"Chart5","chart_items":["chart_5"]}}]}')"

# Heartbeat
HEARTBEAT_BODY="{\"brain_id\": \"$BRAIN_ID\"}"
check "D7: Heartbeat" "$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/devices/$PID/heartbeat" \
  -H "Content-Type: application/json" -d "$HEARTBEAT_BODY")"

# Release device
RELEASE_BODY="{\"brain_id\": \"$BRAIN_ID\"}"
check "D8: Release device" "$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/devices/$PID/release" \
  -H "Content-Type: application/json" -d "$RELEASE_BODY")"

echo ""
echo "=== Summary ==="
echo "PASS: $PASS | FAIL: $FAIL | Total: $((PASS+FAIL))"
[ $FAIL -eq 0 ] && exit 0 || exit 1
