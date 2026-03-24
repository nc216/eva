const runtimeConfig = window.PARTICIPANT_CHAT_CONFIG || {};
const apiBaseUrl = resolveApiBaseUrl(runtimeConfig.apiBaseUrl);

const chatStream = document.getElementById("chat-stream");
const messageInput = document.getElementById("message-input");
const sendButton = document.getElementById("send-button");
const chatTitle = document.getElementById("chat-title");
const turnStatus = document.getElementById("turn-status");
const botNameEl = document.getElementById("bot-name");
const avatarLabelEl = document.getElementById("avatar-label");
const welcomeCopyEl = document.getElementById("welcome-copy");

let sessionId = null;
let turnCount = 0;
let maxTurns = 0;
function queryValue(name) {
  return new URLSearchParams(window.location.search).get(name);
}

function resolveApiBaseUrl(configuredBaseUrl) {
  const override = queryValue("api");
  if (override) {
    return override.replace(/\/$/, "");
  }

  const hostname = window.location.hostname;
  const localHost = hostname === "127.0.0.1" || hostname === "localhost";
  const placeholderMissing =
    !configuredBaseUrl || configuredBaseUrl.includes("__API_BASE_URL__");

  if (localHost) {
    return "http://127.0.0.1:8000";
  }

  if (placeholderMissing) {
    return "";
  }

  return configuredBaseUrl.replace(/\/$/, "");
}

function setComposerEnabled(enabled) {
  messageInput.disabled = !enabled;
  sendButton.disabled = !enabled;
}

function autoresizeInput() {
  messageInput.style.height = "auto";
  messageInput.style.height = Math.min(messageInput.scrollHeight, 160) + "px";
}

function addBubble(role, text, imageSource = null) {
  const wrap = document.createElement("article");
  wrap.className = `bubble ${role}`;

  const copy = document.createElement("p");
  copy.textContent = text;
  wrap.appendChild(copy);

  if (imageSource) {
    const image = document.createElement("img");
    image.alt = "Generated image";
    image.className = "generated-image";
    image.loading = "eager";
    image.decoding = "async";
    image.addEventListener("error", () => {
      const errorNote = document.createElement("p");
      errorNote.className = "image-error-note";
      errorNote.textContent = "The browser could not render this image inline. Open it in a new tab or try Chrome.";
      wrap.appendChild(errorNote);
    });

    const openLink = document.createElement("a");
    openLink.className = "image-open-link";
    openLink.target = "_blank";
    openLink.rel = "noopener noreferrer";
    openLink.textContent = "Open image";

    const resolvedImageUrl = imageSource.startsWith("http")
      ? imageSource
      : `${apiBaseUrl}${imageSource}`;
    image.src = resolvedImageUrl;
    openLink.href = resolvedImageUrl;

    wrap.appendChild(image);
    wrap.appendChild(openLink);
  }

  chatStream.appendChild(wrap);
  chatStream.scrollTop = chatStream.scrollHeight;
}

function applyTheme(config) {
  document.documentElement.style.setProperty("--accent", config.accent_color);
  botNameEl.textContent = config.bot_name;
  avatarLabelEl.textContent = config.avatar_label;
  welcomeCopyEl.textContent = config.welcome_message;
}

async function fetchPublicConfig() {
  const response = await fetch(`${apiBaseUrl}/api/config`);
  if (!response.ok) {
    throw new Error("Could not load public configuration");
  }
  return response.json();
}

async function startSession() {
  const response = await fetch(`${apiBaseUrl}/api/session`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      participant_id: queryValue("participant"),
      study_condition: queryValue("condition"),
    }),
  });

  if (!response.ok) {
    throw new Error("Could not start session");
  }

  return response.json();
}

async function sendMessage() {
  const message = messageInput.value.trim();
  if (!message || !sessionId || turnCount >= maxTurns) {
    return;
  }

  addBubble("user", message);
  messageInput.value = "";
  autoresizeInput();
  setComposerEnabled(false);
  turnStatus.textContent = "Thinking…";

  try {
    const response = await fetch(`${apiBaseUrl}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, message }),
    });

    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || "Message failed");
    }

    addBubble("assistant", data.reply, data.image_url || data.image_data_url || null);
    turnCount = data.turn_number;
    turnStatus.textContent = `Turn ${turnCount} of ${maxTurns}`;

    if (turnCount >= maxTurns) {
      setComposerEnabled(false);
      addBubble("system", "This session has reached its turn limit.");
      return;
    }

    setComposerEnabled(true);
    messageInput.focus();
  } catch (error) {
    addBubble("system", error.message);
    turnStatus.textContent = "Connection issue";
    setComposerEnabled(true);
  }
}

async function init() {
  try {
    const config = await fetchPublicConfig();
    applyTheme(config);

    const session = await startSession();
    sessionId = session.session_id;
    maxTurns = session.max_turns;

    chatTitle.textContent = session.bot_name;
    turnStatus.textContent = `Turn 0 of ${maxTurns}`;
    setComposerEnabled(true);
    messageInput.focus();
  } catch (error) {
    chatTitle.textContent = "Offline";
    turnStatus.textContent = "Setup needed";
    addBubble("system", `${error.message}. Check site/config.js and backend deployment.`);
  }
}

sendButton.addEventListener("click", sendMessage);
messageInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    sendMessage();
  }
});
messageInput.addEventListener("input", autoresizeInput);

autoresizeInput();
init();
