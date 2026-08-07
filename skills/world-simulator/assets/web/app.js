const elements = {
  timeline: document.querySelector("#timeline"),
  storyScroll: document.querySelector("#storyScroll"),
  emptyState: document.querySelector("#emptyState"),
  olderButton: document.querySelector("#olderButton"),
  worldTitle: document.querySelector("#worldTitle"),
  sceneTitle: document.querySelector("#sceneTitle"),
  characterSheet: document.querySelector("#characterSheet"),
  characterPanel: document.querySelector("#characterPanel"),
  worldContent: document.querySelector("#worldContent"),
  gameRail: document.querySelector("#gameRail"),
  railTitle: document.querySelector("#railTitle"),
  railToggle: document.querySelector("#railToggle"),
  railClose: document.querySelector("#railClose"),
  railScrim: document.querySelector("#railScrim"),
  railTabs: [...document.querySelectorAll(".rail-tab")],
  railPanels: [...document.querySelectorAll(".rail-panel")],
  commandLabel: document.querySelector("#commandLabel"),
  commandContext: document.querySelector("#commandContext"),
  characterTab: document.querySelector("#characterTab"),
  worldTab: document.querySelector("#worldTab"),
  emptyTitle: document.querySelector("#emptyTitle"),
  emptyBody: document.querySelector("#emptyBody"),
  inputLabel: document.querySelector("#inputLabel"),
  keyboardHint: document.querySelector("#keyboardHint"),
  worldInput: document.querySelector("#worldInput"),
  composer: document.querySelector("#composer"),
  sendButton: document.querySelector("#sendButton"),
  beginButton: document.querySelector("#beginButton"),
  notice: document.querySelector("#notice"),
};

const model = {
  state: null,
  turns: [],
  hasOlder: false,
  loadingOlder: false,
  submitting: false,
  railOpen: false,
  activePanel: localStorage.getItem("worldsim:rail-panel") || "character",
  sectionState: JSON.parse(localStorage.getItem("worldsim:open-sections") || "{}"),
  stateSnapshot: "",
  turnSnapshot: "",
};

function uiText(key, fallback) {
  const value = model.state?.presentation?.ui?.[key];
  return typeof value === "string" && value ? value : fallback;
}

function node(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined && text !== null) element.textContent = String(text);
  return element;
}

function escapePattern(text) {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function appendFormattedText(element, text, emphasizedPhrases = []) {
  const source = String(text || "");
  const phrases = emphasizedPhrases
    .filter((phrase) => typeof phrase === "string" && phrase)
    .map(escapePattern)
    .sort((left, right) => right.length - left.length);
  const alternatives = [
    "\\*\\*([\\s\\S]+?)\\*\\*",
    "([“\"][^”\"\\n]+[”\"]|「[^」\\n]+」|『[^』\\n]+』)",
    phrases.length ? `(${phrases.join("|")})` : "",
  ].filter(Boolean);
  const emphasis = new RegExp(alternatives.join("|"), "g");
  let cursor = 0;
  for (const match of source.matchAll(emphasis)) {
    if (match.index > cursor) element.append(document.createTextNode(source.slice(cursor, match.index)));
    element.append(node("strong", "", match[1] || match[2] || match[3]));
    cursor = match.index + match[0].length;
  }
  if (cursor < source.length) element.append(document.createTextNode(source.slice(cursor)));
}

function valueText(value) {
  if (value === null || value === undefined || value === "") return "";
  if (Array.isArray(value)) return value.map(valueText).filter(Boolean).join(" · ");
  if (typeof value === "object") {
    if ("value" in value && "label" in value) return valueText(value.value);
    return Object.entries(value)
      .map(([key, nested]) => {
        const text = valueText(nested);
        const label = nested && typeof nested === "object" && nested.label ? nested.label : key;
        return text ? `${label}: ${text}` : "";
      })
      .filter(Boolean)
      .join("\n");
  }
  if (typeof value === "boolean") {
    return value ? uiText("boolean_true", "true") : uiText("boolean_false", "false");
  }
  return String(value);
}

function factValue(facts, key) {
  return valueText(facts?.[key]);
}

function meaningfulEntries(facts, omitted = []) {
  const excluded = new Set(omitted);
  return Object.entries(facts || {})
    .filter(([key, value]) => !excluded.has(key) && valueText(value))
    .map(([key, value]) => ({
      label: value && typeof value === "object" && value.label ? value.label : key,
      value: valueText(value),
    }));
}

function appendFacts(parent, facts, omitted = [], className = "entry-facts") {
  const entries = meaningfulEntries(facts, omitted);
  if (!entries.length) return false;
  const list = node("dl", className);
  for (const fact of entries) {
    const row = node("div", className === "sheet-facts" ? "sheet-fact" : "entry-fact");
    row.append(node("dt", "", fact.label), node("dd", "", fact.value));
    list.append(row);
  }
  parent.append(list);
  return true;
}

function entityById(id) {
  return model.state?.entities?.find((entity) => entity.id === id) || null;
}

function getPlayer() {
  return entityById(model.state?.player_id) || model.state?.entities?.find((entity) => entity.kind === "player") || null;
}

function getScene() {
  return entityById(model.state?.scene_id) || model.state?.entities?.find((entity) => entity.kind === "scene") || null;
}

function renderChrome() {
  document.documentElement.lang = model.state?.language || "ko";
  elements.railTitle.textContent = uiText("rail_title", "모험 기록");
  elements.railToggle.textContent = uiText("rail_title", "모험 기록");
  elements.railClose.setAttribute("aria-label", uiText("close_rail", "모험 기록 닫기"));
  elements.railScrim.setAttribute("aria-label", uiText("close_rail", "모험 기록 닫기"));
  elements.characterTab.textContent = uiText("character_tab", "인물");
  elements.worldTab.textContent = uiText("world_tab", "세계");
  elements.olderButton.textContent = uiText("older_turns", "이전 이야기 불러오기");
  elements.emptyTitle.textContent = uiText("empty_title", "어떤 세계에서 시작할까요?");
  elements.emptyBody.textContent = uiText(
    "empty_body",
    "배경과 주인공, 원하는 분위기를 자유롭게 적어주세요."
  );
  elements.inputLabel.textContent = uiText("input_label", "세계 설정 또는 행동 입력");
  elements.keyboardHint.textContent = uiText("keyboard_hint", "Enter 전송 · Shift+Enter 줄바꿈");
  elements.beginButton.textContent = uiText("begin_button", "모험 시작");
}

function renderHeader() {
  const scene = getScene();
  elements.worldTitle.textContent = model.state?.display_name || uiText("untitled_world", "새로운 세계");
  elements.sceneTitle.textContent = scene?.name || (model.state?.mode === "studio"
    ? uiText("studio_scene", "세계를 구성하는 중")
    : uiText("play_scene", "이야기가 이어지는 중"));
  document.title = `${elements.worldTitle.textContent} — ${uiText("app_name", "World Simulator")}`;
}

function collectStatus(player) {
  const responseStatus = model.state?.latest_response?.status;
  const entries = [];
  if (Array.isArray(responseStatus)) {
    for (const status of responseStatus) {
      if (!status || typeof status !== "object" || Array.isArray(status)) continue;
      const label = valueText(status.label);
      const value = valueText(status.value);
      if (label && value) {
        entries.push({ label, value });
        continue;
      }
      for (const [legacyLabel, legacyValue] of Object.entries(status)) {
        const legacyText = valueText(legacyValue);
        if (legacyText) entries.push({ label: legacyLabel, value: legacyText });
      }
    }
  }
  if (!entries.length && player?.public?.condition) {
    const condition = player.public.condition;
    entries.push({
      label: condition?.label || uiText("status_label", "상태"),
      value: valueText(condition),
    });
  }
  return entries;
}

function playerItems(player) {
  if (!player) return [];
  const relations = model.state?.relations || [];
  const relatedIds = new Set();
  for (const relation of relations) {
    if (relation.source_id === player.id) relatedIds.add(relation.target_id);
    if (relation.target_id === player.id) relatedIds.add(relation.source_id);
  }
  return (model.state?.entities || []).filter(
    (entity) => entity.kind === "item" && relatedIds.has(entity.id)
  );
}

function renderCharacter() {
  elements.characterSheet.replaceChildren();
  elements.characterPanel.replaceChildren();
  const player = getPlayer();
  if (!player) {
    elements.characterSheet.append(node("p", "sheet-empty", uiText(
      "character_empty",
      "세계가 정해지면 이곳에 주인공의 정체와 상태가 자리 잡습니다."
    )));
    elements.characterPanel.append(node("p", "sheet-empty", uiText(
      "character_detail_empty",
      "주인공의 상세 정보가 이곳에 쌓입니다."
    )));
    return;
  }

  const identity = node("section", "character-identity");
  const sigil = node("div", "character-sigil", Array.from(player.name || "?")[0] || "?");
  const name = node("div", "character-name");
  name.append(node("h2", "", player.name));
  const role = factValue(player.public, "role")
    || factValue(player.public, "calling")
    || factValue(player.public, "identity");
  if (role) name.append(node("p", "", role));
  identity.append(sigil, name);
  elements.characterSheet.append(identity);

  const now = node("div", "player-now");
  const statuses = collectStatus(player);
  if (statuses.length) {
    for (const status of statuses) {
      const item = node("div", "now-item");
      item.append(node("span", "", status.label), node("strong", "", status.value));
      now.append(item);
    }
  }
  const scene = getScene();
  if (scene) {
    const place = node("div", "player-place", scene.name);
    place.dataset.label = uiText("location_label", "위치");
    now.append(place);
  }
  if (now.childElementCount) elements.characterSheet.append(now);

  const traits = node("section", "sheet-section");
  traits.append(node("h3", "", uiText("character_section", "인물")));
  if (!appendFacts(traits, player.public, ["role", "calling", "condition"], "sheet-facts")) {
    traits.append(node("p", "sheet-empty", uiText(
      "character_facts_empty",
      "인물의 면모가 아직 정해지지 않았습니다."
    )));
  }
  elements.characterPanel.append(traits);

  const items = playerItems(player);
  if (items.length) {
    const equipment = node("section", "sheet-section");
    equipment.append(node("h3", "", uiText("inventory_section", "소지품과 장비")));
    const tags = node("div", "sheet-tags");
    for (const item of items) tags.append(node("span", "sheet-tag", item.name));
    equipment.append(tags);
    elements.characterPanel.append(equipment);
  }

  if (scene) {
    const location = node("section", "sheet-section");
    location.append(node("h3", "", uiText("location_section", "현재 위치")));
    const summary = node("div", "location-summary");
    summary.append(node("strong", "", scene.name));
    const detail = factValue(scene.public, "summary")
      || factValue(scene.public, "situation")
      || factValue(scene.public, "environment");
    if (detail) summary.append(node("p", "", detail));
    location.append(summary);
    elements.characterPanel.append(location);
  }
}

function renderEntity(entity) {
  const entry = node("article", "world-entry");
  entry.append(node("span", "entry-kind", entity.kind_label || entity.kind));
  entry.append(node("h3", "", entity.name));
  appendFacts(entry, entity.public);
  if (entity.gm && Object.keys(entity.gm).length) {
    const secret = node("div", "secret-note");
    secret.append(node("strong", "", uiText("gm_note", "진행 메모")));
    appendFacts(secret, entity.gm);
    entry.append(secret);
  }
  return entry;
}

function rememberSection(section, key, defaultOpen = false) {
  section.dataset.section = key;
  section.open = key in model.sectionState ? model.sectionState[key] : defaultOpen;
  section.addEventListener("toggle", () => {
    model.sectionState[key] = section.open;
    localStorage.setItem("worldsim:open-sections", JSON.stringify(model.sectionState));
  });
}

function worldSection(title, entities, key, defaultOpen = false) {
  if (!entities.length) return null;
  const section = node("details", "world-section");
  rememberSection(section, key, defaultOpen);
  const summary = node("summary");
  summary.append(node("span", "", title), node("span", "world-count", entities.length));
  const body = node("div", "world-section-body");
  for (const entity of entities) body.append(renderEntity(entity));
  section.append(summary, body);
  return section;
}

function relationSection(relations) {
  if (!relations.length) return null;
  const section = node("details", "world-section");
  rememberSection(section, "relations");
  const summary = node("summary");
  summary.append(
    node("span", "", uiText("relations_section", "관계")),
    node("span", "world-count", relations.length)
  );
  const body = node("div", "world-section-body");
  for (const relation of relations) {
    const source = entityById(relation.source_id);
    const target = entityById(relation.target_id);
    if (!source || !target) continue;
    const predicate = relation.predicate_label || relation.predicate;
    const line = node("div", "relation-line", `${source.name} · ${predicate} · ${target.name}`);
    const detail = valueText(relation.public);
    if (detail) line.append(node("div", "", detail));
    body.append(line);
  }
  if (!body.childElementCount) return null;
  section.append(summary, body);
  return section;
}

function renderWorld() {
  const scrollTop = elements.worldContent.scrollTop;
  elements.worldContent.replaceChildren();
  const all = model.state?.entities || [];
  const player = getPlayer();
  const scene = getScene();
  const grouped = new Map();
  for (const entity of all) {
    if (entity.id === player?.id || entity.id === scene?.id) continue;
    const group = grouped.get(entity.kind) || {
      title: entity.kind_label || entity.kind,
      entities: [],
    };
    group.entities.push(entity);
    grouped.set(entity.kind, group);
  }
  const entityGroups = [...grouped.entries()]
    .sort((left, right) => left[1].title.localeCompare(right[1].title))
    .map(([kind, group]) => worldSection(group.title, group.entities, `kind:${kind}`));
  const groups = [
    worldSection(uiText("scene_section", "현재 장면"), scene ? [scene] : [], "scene", true),
    ...entityGroups,
    relationSection(model.state?.relations || []),
  ].filter(Boolean);
  if (!groups.length) {
    elements.worldContent.append(node("p", "world-empty", uiText(
      "world_empty",
      "플레이를 시작하면 발견한 인물과 장소, 이어지는 사건이 이곳에 쌓입니다."
    )));
    return;
  }
  elements.worldContent.append(...groups);
  elements.worldContent.scrollTop = scrollTop;
}

function visualPath(path) {
  return `/session-assets/${String(path).replace(/^\/?assets\//, "")}`;
}

function renderTurn(turn) {
  const exchange = node("article", "exchange");
  exchange.dataset.turnId = turn.id;
  const intent = node("div", `player-intent${turn.kind === "studio" ? " concept" : ""}`);
  const mark = turn.kind === "studio" ? uiText("concept_mark", "구상") : "›";
  const visibleInput = turn.user_text;
  const intentText = node("p", "intent-text");
  appendFormattedText(intentText, visibleInput);
  intent.append(node("span", "intent-mark", mark), intentText);
  exchange.append(intent);

  if (turn.response) {
    if (turn.response.scene_label) exchange.append(node("div", "scene-label", turn.response.scene_label));
    const narration = node("div", "narration");
    appendFormattedText(narration, turn.response.markdown, turn.response.emphasis);
    exchange.append(narration);
    if (Array.isArray(turn.response.visuals) && turn.response.visuals.length) {
      const visuals = node("div", "visual-list");
      for (const visual of turn.response.visuals) {
        if (!visual?.asset_path) continue;
        const figure = node("figure");
        const image = node("img");
        image.src = visualPath(visual.asset_path);
        image.alt = visual.alt || uiText("visual_alt", "이야기 장면");
        figure.append(image);
        if (visual.caption) figure.append(node("figcaption", "", visual.caption));
        visuals.append(figure);
      }
      exchange.append(visuals);
    }
  } else if (turn.status === "pending" || turn.status === "processing") {
    exchange.append(node("p", "turn-wait", uiText("processing_turn", "세계가 반응하고 있습니다…")));
  } else if (turn.error) {
    exchange.append(node("p", "turn-wait", uiText("turn_error", "이 장면을 이어가지 못했습니다.")));
  }
  return exchange;
}

function renderTimeline() {
  elements.timeline.replaceChildren(...model.turns.map(renderTurn));
  elements.emptyState.hidden = model.turns.length > 0;
  elements.olderButton.hidden = !model.hasOlder;
}

function renderCommand() {
  const studio = model.state?.mode !== "play";
  const busy = Boolean(model.state?.processing) || model.submitting;
  const scene = getScene();
  elements.commandLabel.textContent = studio
    ? uiText("studio_input_title", "세계 구상")
    : uiText("play_input_title", "행동 또는 대사");
  elements.commandContext.textContent = studio
    ? uiText("studio_input_context", "설정을 함께 구체화합니다")
    : scene?.name || uiText("current_scene", "현재 장면");
  elements.worldInput.placeholder = studio
    ? uiText("studio_placeholder", "원하는 세계와 주인공을 설명하세요…")
    : uiText("play_placeholder", "무엇을 하거나 말할지 자유롭게 적으세요…");
  elements.worldInput.disabled = busy;
  elements.sendButton.disabled = busy;
  elements.sendButton.textContent = busy
    ? uiText("waiting", "기다리는 중")
    : uiText("send", "전송");
  elements.beginButton.hidden = !model.state?.can_begin || busy;
}

function render() {
  renderChrome();
  renderHeader();
  renderCharacter();
  renderWorld();
  renderTimeline();
  renderCommand();
}

function setNotice(message = "") {
  elements.notice.textContent = message;
}

function setActivePanel(panel) {
  model.activePanel = panel;
  localStorage.setItem("worldsim:rail-panel", panel);
  for (const tab of elements.railTabs) {
    const active = tab.dataset.panel === panel;
    tab.classList.toggle("active", active);
    tab.setAttribute("aria-selected", String(active));
  }
  for (const content of elements.railPanels) {
    content.classList.toggle("active", content.id === `${panel}Panel` || (panel === "world" && content.id === "worldContent"));
  }
}

function setRailOpen(open) {
  model.railOpen = open;
  elements.gameRail.classList.toggle("open", open);
  elements.railScrim.classList.toggle("open", open);
  elements.railToggle.setAttribute("aria-expanded", String(open));
}

function nearBottom() {
  const element = elements.storyScroll;
  return element.scrollHeight - element.scrollTop - element.clientHeight < 140;
}

function scrollToBottom() {
  elements.storyScroll.scrollTop = elements.storyScroll.scrollHeight;
}

async function request(path, options) {
  const response = await fetch(path, options);
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || "요청을 처리하지 못했습니다.");
  return payload;
}

function mergeTurns(turns) {
  const byId = new Map(model.turns.map((turn) => [turn.id, turn]));
  for (const turn of turns) byId.set(turn.id, turn);
  model.turns = [...byId.values()].sort((left, right) => left.id - right.id);
}

async function loadInitial() {
  const [state, turns] = await Promise.all([request("/api/state"), request("/api/turns?limit=30")]);
  model.state = state;
  model.turns = turns.items;
  model.hasOlder = turns.has_more;
  model.stateSnapshot = JSON.stringify(state);
  model.turnSnapshot = JSON.stringify(turns.items);
  render();
  setActivePanel(model.activePanel);
  requestAnimationFrame(scrollToBottom);
}

async function refresh() {
  const shouldFollow = nearBottom();
  const [state, turns] = await Promise.all([request("/api/state"), request("/api/turns?limit=30")]);
  const stateSnapshot = JSON.stringify(state);
  const turnSnapshot = JSON.stringify(turns.items);
  const stateChanged = stateSnapshot !== model.stateSnapshot;
  const turnsChanged = turnSnapshot !== model.turnSnapshot;
  model.state = state;
  mergeTurns(turns.items);
  model.stateSnapshot = stateSnapshot;
  model.turnSnapshot = turnSnapshot;
  if (stateChanged) {
    renderChrome();
    renderHeader();
    renderCharacter();
    renderWorld();
    renderCommand();
  }
  if (turnsChanged) renderTimeline();
  if (turnsChanged && shouldFollow) requestAnimationFrame(scrollToBottom);
}

async function loadOlder() {
  if (model.loadingOlder || !model.turns.length) return;
  model.loadingOlder = true;
  elements.olderButton.disabled = true;
  const oldHeight = elements.storyScroll.scrollHeight;
  try {
    const result = await request(`/api/turns?before=${model.turns[0].id}&limit=30`);
    mergeTurns(result.items);
    model.hasOlder = result.has_more;
    renderTimeline();
    elements.storyScroll.scrollTop += elements.storyScroll.scrollHeight - oldHeight;
  } catch (error) {
    setNotice(error.message);
  } finally {
    model.loadingOlder = false;
    elements.olderButton.disabled = false;
  }
}

function resizeInput() {
  elements.worldInput.style.height = "auto";
  elements.worldInput.style.height = `${Math.min(elements.worldInput.scrollHeight, 144)}px`;
}

async function submit(path, text) {
  if (model.submitting) return;
  model.submitting = true;
  setNotice();
  renderCommand();
  try {
    await request(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    elements.worldInput.value = "";
    resizeInput();
    await refresh();
    requestAnimationFrame(scrollToBottom);
  } catch (error) {
    setNotice(error.message);
  } finally {
    model.submitting = false;
    renderCommand();
    elements.worldInput.focus();
  }
}

elements.composer.addEventListener("submit", (event) => {
  event.preventDefault();
  const text = elements.worldInput.value.trim();
  if (text) submit("/api/input", text);
});

elements.worldInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    elements.composer.requestSubmit();
  }
});
elements.worldInput.addEventListener("input", resizeInput);
elements.beginButton.addEventListener("click", () => submit(
  "/api/begin",
  uiText("begin_input", "모험을 시작한다.")
));
elements.olderButton.addEventListener("click", loadOlder);
for (const tab of elements.railTabs) tab.addEventListener("click", () => setActivePanel(tab.dataset.panel));
elements.railToggle.addEventListener("click", () => setRailOpen(true));
elements.railClose.addEventListener("click", () => setRailOpen(false));
elements.railScrim.addEventListener("click", () => setRailOpen(false));
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && model.railOpen) setRailOpen(false);
});

loadInitial().catch((error) => {
  setNotice(error.message);
  elements.emptyTitle.textContent = uiText("load_error_title", "세계를 불러오지 못했습니다");
  elements.emptyBody.textContent = uiText("load_error_body", "서버가 실행 중인지 확인해주세요.");
});

setInterval(() => {
  if (!model.submitting) refresh().catch((error) => setNotice(error.message));
}, 1200);
