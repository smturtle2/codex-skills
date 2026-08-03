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
  railToggle: document.querySelector("#railToggle"),
  railClose: document.querySelector("#railClose"),
  railScrim: document.querySelector("#railScrim"),
  railTabs: [...document.querySelectorAll(".rail-tab")],
  railPanels: [...document.querySelectorAll(".rail-panel")],
  commandLabel: document.querySelector("#commandLabel"),
  commandContext: document.querySelector("#commandContext"),
  commandMark: document.querySelector("#commandMark"),
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

const LABELS = {
  condition: "상태",
  identity: "정체",
  role: "역할",
  calling: "역할",
  source_discipline: "근원 계통",
  location: "위치",
  pressure: "압박",
  time: "시간",
  summary: "개요",
  description: "설명",
  present: "현장 인물",
  goal: "목표",
  presence: "영향력",
  appearance: "인상착의",
  current_action: "현재 행동",
  effect: "효과",
  worn_by: "착용자",
  nature: "성질",
  restriction: "제약",
  risk: "위험",
  era: "시대",
  crisis: "세계의 위기",
  authority: "통치 세력",
  situation: "상황",
  known: "알려진 정보",
  purpose: "용도",
  scope: "진행 범위",
  motive: "동기",
  knowledge: "알고 있는 것",
  attitude_to_player: "플레이어를 대하는 태도",
  internal_tension: "내부 갈등",
  immediate_pressure: "당면 압력",
  opening_trigger: "시작 계기",
  next_development: "다음 전개",
  next_due: "예정 시점",
  truth: "숨은 진실",
  weakness: "약점",
  adjudication: "판정 기준",
  open_questions: "미정 사항",
  agency_rule: "진행 원칙",
  hidden_access: "숨은 통로",
  environment: "주변 환경",
  state: "현재 상태",
  reason: "이유",
  trigger: "발동 조건",
  consequence: "결과",
  progress: "진행도",
  stakes: "걸린 것",
  relationship: "관계",
  disposition: "태도",
  objective: "목적",
  details: "세부 사항",
  capability: "능력",
  geography: "지리",
  culture: "문화",
  history: "역사",
  politics: "정치",
  practice: "운용 방식",
  world_engine: "세계의 동력",
  knowledge_limit: "지식의 한계",
  authorial_boundary: "전개 경계",
  phase: "단계",
  technology: "기술 수준",
  languages: "언어",
  currency: "화폐",
  tone: "분위기",
  evidence: "증거",
};

const KINDS = {
  player: "플레이어",
  character: "인물",
  scene: "현재 장면",
  place: "장소",
  faction: "세력",
  thread: "진행 중인 사건",
  quest: "과업",
  threat: "위협",
  world: "세계",
  rule: "세계의 법칙",
  item: "소지품",
  culture: "종족과 문화",
};

const PREDICATES = {
  "hunted-by": "추적당함",
  "imprisoned-by": "구금됨",
  "located-in": "머무름",
  "suppresses-source-of": "근원을 억제함",
  "tracks-source-near": "근원의 흔적을 감지함",
  "unfolds-at": "이곳에서 진행됨",
  investigates: "조사함",
  observes: "주시함",
  carries: "소지함",
  wears: "착용함",
  opposes: "대립함",
  controls: "지배함",
  serves: "소속됨",
  knows: "알고 있음",
  "heritage-from": "혈통이 이어짐",
  governs: "통치함",
  regulates: "관리함",
  inhabits: "살아감",
  "can-use": "사용할 수 있음",
  "child-of": "자녀임",
  from: "출신",
  "member-of": "소속됨",
  "based-in": "근거지를 둠",
  awaits: "기다림",
  orchestrates: "배후에서 조종함",
  targets: "노림",
};

function node(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined && text !== null) element.textContent = String(text);
  return element;
}

function appendFormattedText(element, text) {
  const source = String(text || "");
  const emphasis = /\*\*([\s\S]+?)\*\*|([“"][^”"\n]+[”"]|「[^」\n]+」|『[^』\n]+』)/g;
  let cursor = 0;
  for (const match of source.matchAll(emphasis)) {
    if (match.index > cursor) element.append(document.createTextNode(source.slice(cursor, match.index)));
    element.append(node("strong", "", match[1] || match[2]));
    cursor = match.index + match[0].length;
  }
  if (cursor < source.length) element.append(document.createTextNode(source.slice(cursor)));
}

function valueText(value) {
  if (value === null || value === undefined || value === "") return "";
  if (Array.isArray(value)) return value.map(valueText).filter(Boolean).join(" · ");
  if (typeof value === "object") {
    return Object.entries(value)
      .map(([key, nested]) => {
        const text = valueText(nested);
        return text ? `${LABELS[key] || "정보"}: ${text}` : "";
      })
      .filter(Boolean)
      .join("\n");
  }
  if (typeof value === "boolean") return value ? "예" : "아니요";
  return String(value);
}

function meaningfulEntries(facts, omitted = []) {
  const excluded = new Set(omitted);
  return Object.entries(facts || {})
    .filter(([key, value]) => !excluded.has(key) && valueText(value))
    .map(([key, value]) => ({ label: LABELS[key] || "특징", value: valueText(value) }));
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

function renderHeader() {
  const scene = getScene();
  elements.worldTitle.textContent = model.state?.display_name || "새로운 세계";
  elements.sceneTitle.textContent = scene?.name || (model.state?.mode === "studio" ? "세계를 구성하는 중" : "이야기가 이어지는 중");
  document.title = `${elements.worldTitle.textContent} — World Simulator`;
}

function collectStatus(player) {
  const responseStatus = model.state?.latest_response?.status;
  const entries = [];
  if (Array.isArray(responseStatus)) {
    for (const status of responseStatus) {
      if (!status || typeof status !== "object" || Array.isArray(status)) continue;
      for (const [key, value] of Object.entries(status)) {
        const text = valueText(value);
        if (text) entries.push({ label: LABELS[key] || "현재 상태", value: text });
      }
    }
  }
  if (!entries.length && player?.public?.condition) {
    entries.push({ label: "상태", value: valueText(player.public.condition) });
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
  return (model.state?.entities || []).filter((entity) => {
    if (entity.kind !== "item") return false;
    const wearer = valueText(entity.public?.worn_by).toLowerCase();
    return relatedIds.has(entity.id) || wearer.includes(player.id.toLowerCase()) || wearer.includes(player.name.toLowerCase());
  });
}

function renderCharacter() {
  elements.characterSheet.replaceChildren();
  elements.characterPanel.replaceChildren();
  const player = getPlayer();
  if (!player) {
    elements.characterSheet.append(node("p", "sheet-empty", "세계가 정해지면 이곳에 주인공의 정체와 상태가 자리 잡습니다."));
    elements.characterPanel.append(node("p", "sheet-empty", "주인공의 상세 정보가 이곳에 쌓입니다."));
    return;
  }

  const identity = node("section", "character-identity");
  const sigil = node("div", "character-sigil", Array.from(player.name || "?")[0] || "?");
  const name = node("div", "character-name");
  name.append(node("h2", "", player.name));
  const role = player.public?.role || player.public?.calling || player.public?.identity;
  if (role) name.append(node("p", "", valueText(role)));
  identity.append(sigil, name);
  elements.characterSheet.append(identity);

  const now = node("div", "player-now");
  const statuses = collectStatus(player);
  if (statuses.length) {
    for (const status of statuses.slice(0, 2)) {
      const item = node("div", "now-item");
      item.append(node("span", "", status.label), node("strong", "", status.value));
      now.append(item);
    }
  }
  const scene = getScene();
  if (scene) now.append(node("div", "player-place", scene.name));
  if (now.childElementCount) elements.characterSheet.append(now);

  const traits = node("section", "sheet-section");
  traits.append(node("h3", "", "인물"));
  if (!appendFacts(traits, player.public, ["role", "calling", "condition"], "sheet-facts")) {
    traits.append(node("p", "sheet-empty", "인물의 면모가 아직 정해지지 않았습니다."));
  }
  elements.characterPanel.append(traits);

  const items = playerItems(player);
  if (items.length) {
    const equipment = node("section", "sheet-section");
    equipment.append(node("h3", "", "소지품과 장비"));
    const tags = node("div", "sheet-tags");
    for (const item of items) tags.append(node("span", "sheet-tag", item.name));
    equipment.append(tags);
    elements.characterPanel.append(equipment);
  }

  if (scene) {
    const location = node("section", "sheet-section");
    location.append(node("h3", "", "현재 위치"));
    const summary = node("div", "location-summary");
    summary.append(node("strong", "", scene.name));
    const detail = scene.public?.summary || scene.public?.situation || scene.public?.environment;
    if (detail) summary.append(node("p", "", valueText(detail)));
    location.append(summary);
    elements.characterPanel.append(location);
  }
}

function renderEntity(entity) {
  const entry = node("article", "world-entry");
  entry.append(node("span", "entry-kind", KINDS[entity.kind] || "세계 정보"));
  entry.append(node("h3", "", entity.name));
  appendFacts(entry, entity.public);
  if (entity.gm && Object.keys(entity.gm).length) {
    const secret = node("div", "secret-note");
    secret.append(node("strong", "", "진행 메모"));
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
  summary.append(node("span", "", "관계"), node("span", "world-count", relations.length));
  const body = node("div", "world-section-body");
  for (const relation of relations) {
    const source = entityById(relation.source_id);
    const target = entityById(relation.target_id);
    if (!source || !target) continue;
    const predicate = PREDICATES[relation.predicate] || "연관됨";
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
  const groups = [
    worldSection("현재 장면", scene ? [scene] : [], "scene", true),
    worldSection("등장인물", all.filter((entity) => entity.kind === "character" && entity.id !== player?.id), "characters"),
    worldSection("진행 중", all.filter((entity) => ["thread", "quest", "threat"].includes(entity.kind)), "threads", true),
    worldSection("종족과 문화", all.filter((entity) => entity.kind === "culture"), "cultures"),
    worldSection("장소와 세력", all.filter((entity) => ["place", "faction", "world"].includes(entity.kind)), "places"),
    worldSection("규칙과 물건", all.filter((entity) => ["rule", "item"].includes(entity.kind)), "rules"),
    relationSection(model.state?.relations || []),
  ].filter(Boolean);
  if (!groups.length) {
    elements.worldContent.append(node("p", "world-empty", "플레이를 시작하면 발견한 인물과 장소, 이어지는 사건이 이곳에 쌓입니다."));
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
  const mark = turn.kind === "studio" ? "구상" : "›";
  const visibleInput = turn.kind === "begin" ? "모험을 시작한다." : turn.user_text;
  const intentText = node("p", "intent-text");
  appendFormattedText(intentText, visibleInput);
  intent.append(node("span", "intent-mark", mark), intentText);
  exchange.append(intent);

  if (turn.response) {
    if (turn.response.scene_label) exchange.append(node("div", "scene-label", turn.response.scene_label));
    const narration = node("div", "narration");
    appendFormattedText(narration, turn.response.markdown);
    exchange.append(narration);
    if (Array.isArray(turn.response.visuals) && turn.response.visuals.length) {
      const visuals = node("div", "visual-list");
      for (const visual of turn.response.visuals) {
        if (!visual?.asset_path) continue;
        const figure = node("figure");
        const image = node("img");
        image.src = visualPath(visual.asset_path);
        image.alt = visual.alt || "이야기 장면";
        figure.append(image);
        if (visual.caption) figure.append(node("figcaption", "", visual.caption));
        visuals.append(figure);
      }
      exchange.append(visuals);
    }
  } else if (turn.status === "pending" || turn.status === "processing") {
    exchange.append(node("p", "turn-wait", "세계가 반응하고 있습니다…"));
  } else if (turn.error) {
    exchange.append(node("p", "turn-wait", "이 장면을 이어가지 못했습니다."));
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
  elements.commandLabel.textContent = studio ? "세계 구상" : "행동 또는 대사";
  elements.commandContext.textContent = studio ? "설정을 함께 구체화합니다" : scene?.name || "현재 장면";
  elements.commandMark.textContent = studio ? "+" : "›";
  elements.worldInput.placeholder = studio
    ? "원하는 세계와 주인공을 설명하세요…"
    : "무엇을 하거나 말할지 자유롭게 적으세요…";
  elements.worldInput.disabled = busy;
  elements.sendButton.disabled = busy;
  elements.sendButton.textContent = busy ? "기다리는 중" : "전송";
  elements.beginButton.hidden = !model.state?.can_begin || busy;
}

function render() {
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
elements.beginButton.addEventListener("click", () => submit("/api/begin", "모험을 시작한다."));
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
  elements.emptyState.querySelector("h2").textContent = "세계를 불러오지 못했습니다";
  elements.emptyState.querySelector("p").textContent = "서버가 실행 중인지 확인해주세요.";
});

setInterval(() => {
  if (!model.submitting) refresh().catch((error) => setNotice(error.message));
}, 1200);
