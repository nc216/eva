const runtimeConfig = window.PARTICIPANT_CHAT_CONFIG || {};
const apiBaseUrl = resolveApiBaseUrl(runtimeConfig.apiBaseUrl);

const chatStream = document.getElementById("chat-stream");
const messageInput = document.getElementById("message-input");
const sendButton = document.getElementById("send-button");
const chatTitle = document.getElementById("chat-title");
const turnStatus = document.getElementById("turn-status");
const botNameEl = document.getElementById("bot-name");
const avatarLabelEl = document.getElementById("avatar-label");

let sessionId = null;
let turnCount = 0;
let maxTurns = 0;
let surveyCodeTimerId = null;
let surveyCodeShown = false;
let sessionRecovery = null;

function storageKey() {
  const participant = queryValue("participant") || "anon";
  const condition = queryValue("condition") || queryValue("cond") || "none";
  return `participant-chat-lab:${participant}:${condition}`;
}

function persistSessionRecovery() {
  if (!sessionRecovery) {
    return;
  }
  window.localStorage.setItem(storageKey(), JSON.stringify(sessionRecovery));
}

function loadSessionRecovery() {
  const raw = window.localStorage.getItem(storageKey());
  if (!raw) {
    return null;
  }
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

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

function resolveReturnUrl() {
  const explicit = queryValue("return_url");
  if (explicit) {
    return explicit;
  }

  if (document.referrer && /qualtrics\.com/i.test(document.referrer)) {
    return document.referrer;
  }

  return null;
}

function autoresizeInput() {
  messageInput.style.height = "auto";
  messageInput.style.height = Math.min(messageInput.scrollHeight, 160) + "px";
}

function addBubble(role, text, imageSource = null, options = {}) {
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

  if (Array.isArray(options.actions) && options.actions.length > 0) {
    const actions = document.createElement("div");
    actions.className = "bubble-actions";

    options.actions.forEach((action) => {
      if (!action || !action.label) {
        return;
      }

      if (action.href) {
        const link = document.createElement("a");
        link.className = action.secondary ? "bubble-link secondary" : "bubble-link";
        link.href = action.href;
        link.textContent = action.label;
        if (action.newTab) {
          link.target = "_blank";
          link.rel = "noopener noreferrer";
        }
        actions.appendChild(link);
        return;
      }

      if (typeof action.onClick === "function") {
        const button = document.createElement("button");
        button.type = "button";
        button.className = action.secondary ? "bubble-button secondary" : "bubble-button";
        button.textContent = action.label;
        button.addEventListener("click", action.onClick);
        actions.appendChild(button);
      }
    });

    if (actions.children.length > 0) {
      wrap.appendChild(actions);
    }
  }

  chatStream.appendChild(wrap);
  chatStream.scrollTop = chatStream.scrollHeight;
}

function renderRecoveryMessages(recovery) {
  const messages = Array.isArray(recovery?.messages) ? recovery.messages : [];
  if (messages.length === 0) {
    addBubble(
      "assistant",
      recovery?.config_snapshot?.welcome_message
        || "Hi, I’m Aster. Ask me anything. And if you want a picture, just ask me to send one.",
    );
    return;
  }

  messages.forEach((message) => {
    const metadata = message.metadata || {};
    addBubble(
      message.role || "assistant",
      message.content || "",
      metadata.image_url || metadata.image_data_url || null,
    );
  });
}

function applyTheme(config) {
  document.documentElement.style.setProperty("--accent", config.accent_color);
  botNameEl.textContent = config.bot_name;
  avatarLabelEl.textContent = config.avatar_label;
}

async function fetchPublicConfig() {
  const response = await fetch(`${apiBaseUrl}/api/config`);
  if (!response.ok) {
    throw new Error("Could not load public configuration");
  }
  return response.json();
}

async function startSession() {
  const cachedRecovery = loadSessionRecovery();
  if (cachedRecovery?.session_id) {
    return {
      session_id: cachedRecovery.session_id,
      bot_name: cachedRecovery.bot_name,
      welcome_message:
        cachedRecovery.config_snapshot?.welcome_message
        || "Hi, I’m Aster. Ask me anything. And if you want a picture, just ask me to send one.",
      max_turns: cachedRecovery.config_snapshot?.max_turns || 30,
      survey_code_delay_seconds: 300,
      recovery: cachedRecovery,
      restored_from_cache: true,
    };
  }

  const studyCondition = queryValue("condition") || queryValue("cond");
  const response = await fetch(`${apiBaseUrl}/api/session`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      participant_id: queryValue("participant"),
      study_condition: studyCondition,
    }),
  });

  if (!response.ok) {
    throw new Error("Could not start session");
  }

  return response.json();
}

async function postChatMessage(payload, attempt = 0) {
  try {
    const response = await fetch(`${apiBaseUrl}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    const data = await response.json();
    if (!response.ok) {
      if ((data.detail === "Session not found" || response.status >= 500) && attempt < 1) {
        await new Promise((resolve) => window.setTimeout(resolve, 800));
        return postChatMessage(payload, attempt + 1);
      }
      throw new Error(data.detail || "Message failed");
    }

    return data;
  } catch (error) {
    if (attempt < 1) {
      await new Promise((resolve) => window.setTimeout(resolve, 800));
      return postChatMessage(payload, attempt + 1);
    }
    throw error;
  }
}

async function fetchSurveyCode() {
  if (!sessionId || surveyCodeShown) {
    return;
  }

  const response = await fetch(`${apiBaseUrl}/api/survey-code`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId }),
  });

  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.detail || "Could not load survey code");
  }

  surveyCodeShown = true;
  if (sessionRecovery) {
    sessionRecovery.survey_code_issued = true;
    persistSessionRecovery();
  }

  const returnUrl = resolveReturnUrl();
  const actions = [];
  if (returnUrl) {
    actions.push({ label: "Return to survey", href: returnUrl });
  }
  actions.push({
    label: "Keep chatting",
    secondary: true,
    onClick: () => {
      messageInput.focus();
    },
  });

  addBubble("assistant", data.reply, null, { actions });
  turnStatus.textContent = `Turn ${turnCount} of ${maxTurns}`;
}

function scheduleSurveyCode(delaySeconds) {
  if (surveyCodeTimerId) {
    window.clearTimeout(surveyCodeTimerId);
  }

  if (!delaySeconds || delaySeconds <= 0) {
    return;
  }

  surveyCodeTimerId = window.setTimeout(async () => {
    try {
      await fetchSurveyCode();
    } catch (error) {
      addBubble("system", error.message);
    }
  }, delaySeconds * 1000);
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
    const data = await postChatMessage({
      session_id: sessionId,
      message,
      recovery: sessionRecovery,
    });

    addBubble("assistant", data.reply, data.image_url || data.image_data_url || null);
    sessionRecovery = data.recovery || sessionRecovery;
    persistSessionRecovery();
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
    sessionRecovery = session.recovery || sessionRecovery;
    persistSessionRecovery();
    surveyCodeShown = Boolean(sessionRecovery?.survey_code_issued);

    chatTitle.textContent = session.bot_name;
    if (session.restored_from_cache) {
      renderRecoveryMessages(sessionRecovery);
      turnCount = Array.isArray(sessionRecovery?.messages)
        ? sessionRecovery.messages.filter((message) => message.role === "user").length
        : 0;
    } else {
      turnCount = 0;
      addBubble("assistant", session.welcome_message);
    }
    turnStatus.textContent = `Turn ${turnCount} of ${maxTurns}`;
    scheduleSurveyCode(session.survey_code_delay_seconds);
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
