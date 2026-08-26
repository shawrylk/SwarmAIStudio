#!/bin/bash
# Qwen Web Chat Oracle Automation
# Interacts with https://chat.qwen.ai using agent-browser persistent session.

set -euo pipefail

SESSION="qwen-oracle"
TARGET_URL="https://chat.qwen.ai"

usage() {
  echo "Usage:"
  echo "  $0 login                     # Open headed browser to log in with Google"
  echo "  $0 ask <model_name> <prompt> # Send question with target model selection"
  echo "  $0 close                     # Close background browser daemon"
  exit 1
}

CMD="${1:-}"
[[ -z "$CMD" ]] && usage
shift

case "$CMD" in
  login)
    echo "Launching browser for one-time login on ${TARGET_URL}..."
    echo "Once logged in, close the browser window or return here."
    npx agent-browser --headed --session-name "$SESSION" open "$TARGET_URL"
    echo "Session saved under '$SESSION'."
    ;;

  close)
    npx agent-browser --session-name "$SESSION" close || true
    echo "Session closed."
    ;;

  ask)
    TARGET_MODEL="${1:-qwen-3.8-max}"
    shift || true
    PROMPT="$*"

    if [[ -z "$PROMPT" ]]; then
      PROMPT="$TARGET_MODEL"
      TARGET_MODEL="qwen-3.8-max"
    fi

    # Ensure page is open
    npx agent-browser --session-name "$SESSION" open "$TARGET_URL" >/dev/null 2>&1 || true
    npx agent-browser --session-name "$SESSION" wait --load networkidle >/dev/null 2>&1 || true

    # Attempt to switch model on chat.qwen.ai if selector is present
    npx agent-browser --session-name "$SESSION" eval --stdin <<EVALMODEL >/dev/null 2>&1 || true
(() => {
  const target = "${TARGET_MODEL}".toLowerCase();
  const buttons = Array.from(document.querySelectorAll('button, div, span'));
  const modelTrigger = buttons.find(b => b.innerText && (b.innerText.includes('Qwen') || b.innerText.includes('Max') || b.innerText.includes('Plus')));
  if (modelTrigger) {
    modelTrigger.click();
    setTimeout(() => {
      const items = Array.from(document.querySelectorAll('div, li, button, span'));
      const match = items.find(i => i.innerText && i.innerText.toLowerCase().includes(target.replace('qwen-', '').replace('-', ' ')));
      if (match) match.click();
    }, 400);
  }
})()
EVALMODEL

    # Find textarea/input and type prompt
    npx agent-browser --session-name "$SESSION" find placeholder "Ask" fill "$PROMPT" 2>/dev/null || \
    npx agent-browser --session-name "$SESSION" find placeholder "Message" fill "$PROMPT" 2>/dev/null || \
    npx agent-browser --session-name "$SESSION" keyboard inserttext "$PROMPT" 2>/dev/null || true

    # Submit
    npx agent-browser --session-name "$SESSION" press Enter >/dev/null 2>&1 || true

    # Wait for answer generation to settle
    sleep 3
    npx agent-browser --session-name "$SESSION" wait --load networkidle >/dev/null 2>&1 || true

    # Extract latest message text
    RESULT=$(npx agent-browser --session-name "$SESSION" eval --stdin <<'EVALEOF'
(() => {
  const messages = document.querySelectorAll('.message-content, .markdown, [class*="assistant"], [class*="bubble"]');
  if (messages.length > 0) {
    return messages[messages.length - 1].innerText;
  }
  return document.body.innerText;
})()
EVALEOF
)
    echo "$RESULT"
    ;;

  *)
    usage
    ;;
esac
