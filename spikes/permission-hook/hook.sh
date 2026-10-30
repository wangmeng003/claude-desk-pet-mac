#!/bin/bash
LOG=/tmp/desk-pet-spike/hook.log
NOW=$(date +%s.%N)
echo "START t=$NOW pid=$$ ppid=$PPID" >> "$LOG"
cat > /tmp/desk-pet-spike/stdin.$$.json
{
  echo "--- stdin:"; cat /tmp/desk-pet-spike/stdin.$$.json
  echo "--- env: SHELL=$SHELL PATH=$PATH HOME=$HOME PWD=$(pwd)"
} >> "$LOG" 2>&1
mode=$(cat /tmp/desk-pet-spike/mode 2>/dev/null || echo none)
out='{}'
case "$mode" in
  allow) out='{"hookSpecificOutput":{"hookEventName":"PermissionRequest","decision":{"behavior":"allow"}}}' ;;
  deny) out='{"hookSpecificOutput":{"hookEventName":"PermissionRequest","decision":{"behavior":"deny","message":"spike-deny-message"}}}' ;;
  malformed) out='this is {{{ not json' ;;
  crash) echo "END t=$(date +%s.%N) pid=$$ (exit 1)" >> "$LOG"; exit 1 ;;
  block2) echo "spike-blocking-feedback" >&2; echo "END t=$(date +%s.%N) pid=$$ (exit 2)" >> "$LOG"; exit 2 ;;
  sleep) sleep "${SPIKE_SLEEP:-30}"; out='{"hookSpecificOutput":{"hookEventName":"PermissionRequest","decision":{"behavior":"allow"}}}' ;;
esac
echo "$out"
rm -f /tmp/desk-pet-spike/stdin.$$.json
echo "END t=$(date +%s.%N) pid=$$" >> "$LOG"
