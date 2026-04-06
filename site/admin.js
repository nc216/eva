const runtimeConfig = window.PARTICIPANT_CHAT_CONFIG || {};
const apiBaseUrl = resolveApiBaseUrl(runtimeConfig.apiBaseUrl);

const tokenInput = document.getElementById("admin-token");
const loadButton = document.getElementById("load-config");
const form = document.getElementById("config-form");
const statusEl = document.getElementById("admin-status");

const fieldNames = [
  "bot_name",
  "avatar_label",
  "accent_color",
  "temperature",
  "headline",
  "subheadline",
  "welcome_message",
  "research_note",
  "starter_prompts",
  "system_prompt",
  "system_prompt_a",
  "system_prompt_b",
  "image_style_prompt",
  "image_style_prompt_a",
  "image_style_prompt_b",
  "max_turns",
  "image_generation_enabled",
];

function resolveApiBaseUrl(configuredBaseUrl) {
  const override = new URLSearchParams(window.location.search).get("api");
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

function getToken() {
  return tokenInput.value.trim();
}

function setStatus(text) {
  statusEl.textContent = text;
}

function field(name) {
  return form.elements.namedItem(name);
}

function fillForm(config) {
  field("bot_name").value = config.bot_name;
  field("avatar_label").value = config.avatar_label;
  field("accent_color").value = config.accent_color;
  field("temperature").value = config.temperature;
  field("headline").value = config.headline;
  field("subheadline").value = config.subheadline;
  field("welcome_message").value = config.welcome_message;
  field("research_note").value = config.research_note;
  field("starter_prompts").value = (config.starter_prompts || []).join("\n");
  field("system_prompt").value = config.system_prompt;
  field("system_prompt_a").value = config.system_prompt_a || config.system_prompt;
  field("system_prompt_b").value = config.system_prompt_b || config.system_prompt;
  field("image_style_prompt").value = config.image_style_prompt;
  field("image_style_prompt_a").value = config.image_style_prompt_a || config.image_style_prompt;
  field("image_style_prompt_b").value = config.image_style_prompt_b || config.image_style_prompt;
  field("max_turns").value = config.max_turns;
  field("image_generation_enabled").checked = Boolean(config.image_generation_enabled);
}

function readForm() {
  return {
    bot_name: field("bot_name").value.trim(),
    avatar_label: field("avatar_label").value.trim(),
    accent_color: field("accent_color").value.trim(),
    temperature: Number(field("temperature").value),
    headline: field("headline").value.trim(),
    subheadline: field("subheadline").value.trim(),
    welcome_message: field("welcome_message").value.trim(),
    research_note: field("research_note").value.trim(),
    starter_prompts: field("starter_prompts")
      .value
      .split("\n")
      .map((value) => value.trim())
      .filter(Boolean),
    system_prompt: field("system_prompt").value.trim(),
    system_prompt_a: field("system_prompt_a").value.trim(),
    system_prompt_b: field("system_prompt_b").value.trim(),
    image_style_prompt: field("image_style_prompt").value.trim(),
    image_style_prompt_a: field("image_style_prompt_a").value.trim(),
    image_style_prompt_b: field("image_style_prompt_b").value.trim(),
    max_turns: Number(field("max_turns").value),
    image_generation_enabled: field("image_generation_enabled").checked,
  };
}

async function loadConfig() {
  const token = getToken();
  if (!token) {
    setStatus("Enter the admin token first.");
    return;
  }

  setStatus("Loading configuration…");

  try {
    const response = await fetch(`${apiBaseUrl}/api/admin/config`, {
      headers: { "x-admin-token": token },
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || "Could not load configuration");
    }
    fillForm(data);
    window.localStorage.setItem("participant-chat-admin-token", token);
    setStatus("Configuration loaded.");
  } catch (error) {
    setStatus(error.message);
  }
}

async function saveConfig(event) {
  event.preventDefault();

  const token = getToken();
  if (!token) {
    setStatus("Enter the admin token first.");
    return;
  }

  const payload = readForm();
  setStatus("Saving configuration…");

  try {
    const response = await fetch(`${apiBaseUrl}/api/admin/config`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "x-admin-token": token,
      },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || "Could not save configuration");
    }
    fillForm(data);
    setStatus("Configuration saved. New participant sessions will use it immediately.");
  } catch (error) {
    setStatus(error.message);
  }
}

loadButton.addEventListener("click", loadConfig);
form.addEventListener("submit", saveConfig);

const savedToken = window.localStorage.getItem("participant-chat-admin-token");
if (savedToken) {
  tokenInput.value = savedToken;
}
