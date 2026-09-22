const $ = (id) => document.getElementById(id);
let currentPetId = null;
let currentProductId = null;
let weightChart = null;
let productPriceChart = null;

async function api(path, options) {
  const res = await fetch(path, options);
  const data = await res.json().catch(() => ({}));
  if (!res.ok || data.ok === false) throw new Error(data.error || `請求失敗(${res.status})`);
  return data;
}

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

const SPECIES_EMOJI = { dog: "🐶", cat: "🐱" };

// 依生日算歲數(幾歲幾個月), 生日是未來日期或格式不對時回傳null, 呼叫端自己決定要不要顯示
function formatAge(birthday) {
  if (!birthday) return null;
  const born = new Date(birthday);
  if (Number.isNaN(born.getTime())) return null;
  const now = new Date();
  let months = (now.getFullYear() - born.getFullYear()) * 12 + (now.getMonth() - born.getMonth());
  if (now.getDate() < born.getDate()) months -= 1;
  if (months < 0) return null;
  const years = Math.floor(months / 12);
  const remMonths = months % 12;
  if (years === 0) return `${remMonths}個月`;
  if (remMonths === 0) return `${years}歲`;
  return `${years}歲${remMonths}個月`;
}

// 品種輸入框的建議清單(datalist), 只是常見選項方便快速選, 使用者仍可自己打任何字(混種/罕見品種等)
const BREED_SUGGESTIONS = {
  dog: ["米克斯(混種)", "柴犬", "貴賓犬(泰迪)", "法國鬥牛犬", "黃金獵犬", "拉布拉多", "吉娃娃", "雪納瑞",
        "博美", "臘腸犬", "邊境牧羊犬", "哈士奇", "比熊犬", "馬爾濟斯", "巴哥犬", "約克夏", "秋田犬",
        "西施犬", "米格魯", "大麥町", "德國牧羊犬"],
  cat: ["米克斯(混種)", "中華田園貓", "三花貓", "英國短毛貓", "美國短毛貓", "布偶貓", "波斯貓",
        "蘇格蘭摺耳貓", "暹羅貓", "緬因貓", "孟加拉貓", "俄羅斯藍貓", "挪威森林貓", "異國短毛貓",
        "埃及貓", "曼赤肯貓"],
};

function updateBreedOptions(species) {
  const list = $("breedOptions");
  list.innerHTML = "";
  for (const breed of BREED_SUGGESTIONS[species] || []) {
    const opt = document.createElement("option");
    opt.value = breed;
    list.appendChild(opt);
  }
}

// ======================= 頂層導覽 (我的寵物 / 每月花費 / 寵物狀態 / 用品價格) =======================
const TOP_VIEW_SECTIONS = {
  pets: ["petListView", "petDashboard"],
  expenses: ["expensesView"],
  status: ["statusView"],
  products: ["productListView", "productDashboard"],
};
const ALL_TOP_SECTIONS = Object.values(TOP_VIEW_SECTIONS).flat();

document.querySelectorAll(".top-tabs .top-tab-btn").forEach((btn) => {
  btn.addEventListener("click", () => switchTopView(btn.dataset.view));
});

function switchTopView(view) {
  document.querySelectorAll(".top-tabs .top-tab-btn").forEach((b) => b.classList.toggle("active", b.dataset.view === view));
  for (const id of ALL_TOP_SECTIONS) $(id).style.display = "none";
  const [primaryId] = TOP_VIEW_SECTIONS[view];
  $(primaryId).style.display = "block";
  if (view === "pets") loadPets();
  else if (view === "expenses") loadExpensesView();
  else if (view === "status") loadPetStatus();
  else if (view === "products") { loadPlatformStatus(); loadProducts(); }
}

// ======================= 寵物列表 =======================
async function loadPets() {
  const pets = await api("/api/pets");
  const container = $("petCards");
  const summary = $("petSummary");
  container.innerHTML = "";
  if (pets.length === 0) {
    summary.innerHTML = "";
    container.innerHTML = `<div class="empty-hint">🐾 還沒有寵物資料，點右上「+ 新增寵物」開始記錄第一隻的健康日誌吧！</div>`;
    return;
  }
  const dogCount = pets.filter((p) => p.species === "dog").length;
  const catCount = pets.filter((p) => p.species === "cat").length;
  summary.innerHTML = `
    <div class="card stat-card"><div class="stat-label">🐶 狗</div><div class="stat-value">${dogCount}</div></div>
    <div class="card stat-card"><div class="stat-label">🐱 貓</div><div class="stat-value">${catCount}</div></div>
  `;
  for (const pet of pets) {
    const card = document.createElement("div");
    card.className = `pet-card species-${pet.species}`;
    const age = formatAge(pet.birthday);
    card.innerHTML = `<div class="emoji">${SPECIES_EMOJI[pet.species] || "🐾"}</div><h3>${escapeHtml(pet.name)}</h3><p>${escapeHtml(pet.breed || "")}</p>${age ? `<p class="pet-card-age">🎂 ${age}</p>` : ""}`;
    card.addEventListener("click", () => openDashboard(pet.id));
    container.appendChild(card);
  }
}

$("addPetBtn").addEventListener("click", () => openPetForm());

function openPetForm(pet) {
  $("petFormTitle").textContent = pet ? "編輯寵物" : "新增寵物";
  const form = $("petForm");
  form.reset();
  updateBreedOptions(pet ? pet.species : form.species.value);
  if (pet) {
    form.name.value = pet.name;
    form.species.value = pet.species;
    form.breed.value = pet.breed || "";
    form.birthday.value = pet.birthday || "";
    form.sex.value = pet.sex || "unknown";
    form.neutered.checked = !!pet.neutered;
    form.microchip_id.value = pet.microchip_id || "";
    form.weight_goal_kg.value = pet.weight_goal_kg ?? "";
  }
  form.dataset.editingId = pet ? pet.id : "";
  $("petFormModal").style.display = "flex";
}
$("petFormCancel").addEventListener("click", () => { $("petFormModal").style.display = "none"; });
$("petForm").species.addEventListener("change", (e) => updateBreedOptions(e.target.value));

$("petForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.target;
  const body = {
    name: form.name.value.trim(),
    species: form.species.value,
    breed: form.breed.value.trim(),
    birthday: form.birthday.value || null,
    sex: form.sex.value,
    neutered: form.neutered.checked,
    microchip_id: form.microchip_id.value.trim() || null,
    weight_goal_kg: form.weight_goal_kg.value ? Number(form.weight_goal_kg.value) : null,
  };
  const editingId = form.dataset.editingId;
  try {
    if (editingId) {
      await api(`/api/pets/${editingId}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    } else {
      await api("/api/pets", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    }
    $("petFormModal").style.display = "none";
    await loadPets();
    if (editingId) await openDashboard(Number(editingId));
  } catch (err) {
    alert(err.message);
  }
});

// ======================= 儀表板 =======================
async function openDashboard(petId) {
  currentPetId = petId;
  const pets = await api("/api/pets");
  const pet = pets.find((p) => p.id === petId);
  if (!pet) return;
  $("petListView").style.display = "none";
  $("petDashboard").style.display = "block";
  $("dashPetName").textContent = `${SPECIES_EMOJI[pet.species] || "🐾"} ${pet.name}`;
  const dashAge = formatAge(pet.birthday);
  $("dashPetMeta").textContent = [pet.breed, pet.birthday ? `生日 ${pet.birthday}${dashAge ? `(${dashAge})` : ""}` : "", pet.neutered ? "已絕育" : "未絕育", pet.microchip_id ? `晶片 ${pet.microchip_id}` : ""].filter(Boolean).join(" · ");
  $("editPetBtn").onclick = () => openPetForm(pet);
  $("deletePetBtn").onclick = async () => {
    if (!confirm(`確定要刪除「${pet.name}」及其所有紀錄嗎？`)) return;
    await api(`/api/pets/${petId}`, { method: "DELETE" });
    await backToList();
  };
  switchTab("overview");

  await Promise.all([
    loadWeightLogs(),
    loadRecords("bcs_logs", "bcsList", (r) => `${r.recorded_at} — ${r.score}/9 ${r.notes ? "(" + r.notes + ")" : ""}`),
    loadRecords("vet_visits", "vetList", (r) => `${r.visit_date} — ${r.reason || ""} ${r.notes ? "(" + r.notes + ")" : ""}`),
    loadRecords("vaccine_records", "vaccineList", (r) => `${r.item_name} — 施打:${r.given_date}${r.next_due_date ? " 下次到期:" + r.next_due_date : ""}`),
    loadRecords("deworming_records", "dewormingList", (r) => `${r.item_name} — 施打:${r.given_date}${r.next_due_date ? " 下次到期:" + r.next_due_date : ""}`),
    loadRecords("lab_results", "labList", (r) => `${r.test_date} — ${r.item_name}: ${r.value ?? ""}${r.unit || ""} ${r.ref_range ? "(參考:" + r.ref_range + ")" : ""}`),
    loadRecords("diet_entries", "dietEntryList", (r) => `${r.entry_date} — ${r.food_name} ${r.amount_grams ? r.amount_grams + "g" : ""}`),
    loadRecords("custom_reminders", "reminderList", (r) => `${r.due_date} — [${CATEGORY_LABELS[r.category] || r.category}] ${r.title} (提前${r.remind_days_before}天${r.repeat_days ? "，每" + r.repeat_days + "天重複" : ""})`),
    loadFoodPresets(pet.species),
    loadTimeline(),
    loadReminderHistory(),
  ]);
  loadOverviewStats(pet);
  $("dietResult").innerHTML = "";
}

$("backBtn").addEventListener("click", backToList);
async function backToList() {
  currentPetId = null;
  $("petDashboard").style.display = "none";
  $("petListView").style.display = "block";
  await loadPets();
}

// ---- 分頁籤 ----
document.querySelectorAll(".tabs .tab-btn").forEach((btn) => {
  btn.addEventListener("click", () => switchTab(btn.dataset.tab));
});
function switchTab(tab) {
  document.querySelectorAll(".tabs .tab-btn").forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
  document.querySelectorAll(".tab-panel").forEach((p) => p.classList.toggle("active", p.id === `tab-${tab}`));
}

// ---- 總覽統計 ----
async function loadOverviewStats(pet) {
  const [weights, bcsRows] = await Promise.all([
    api(`/api/pets/${currentPetId}/weight_logs`),
    api(`/api/pets/${currentPetId}/bcs_logs`),
  ]);
  const latestWeight = weights[0]; // 已依recorded_at DESC排序
  const latestBcs = bcsRows[0];
  $("statWeight").textContent = latestWeight ? `${latestWeight.weight_kg} kg` : "尚無紀錄";
  $("statBcs").textContent = latestBcs ? `${latestBcs.score} / 9` : "尚無紀錄";

  const goalEl = $("statWeightGoal");
  const goalCard = $("weightGoalCard");
  if (pet.weight_goal_kg && latestWeight) {
    const delta = Math.round((pet.weight_goal_kg - latestWeight.weight_kg) * 100) / 100;
    if (Math.abs(delta) < 0.05) {
      goalEl.textContent = `已達成 ${pet.weight_goal_kg}kg`;
      goalEl.classList.add("goal-hit");
    } else {
      goalEl.textContent = `${pet.weight_goal_kg}kg (還差${delta > 0 ? "+" : ""}${delta}kg)`;
      goalEl.classList.remove("goal-hit");
    }
    goalCard.style.display = "";
  } else if (pet.weight_goal_kg) {
    goalEl.textContent = `${pet.weight_goal_kg}kg (尚無體重紀錄)`;
    goalCard.style.display = "";
  } else {
    goalCard.style.display = "none";
  }
}

// ---- 病史時間線 ----
const TIMELINE_ICON = { weight: "⚖️", vet_visit: "🏥", vaccine: "💉", deworming: "🐛", bcs: "📏", lab: "🧪" };
async function loadTimeline() {
  const events = await api(`/api/pets/${currentPetId}/timeline`);
  const renderList = (ul, items) => {
    ul.innerHTML = "";
    if (items.length === 0) {
      ul.innerHTML = `<li class="empty-hint">📭 尚無紀錄</li>`;
      return;
    }
    for (const e of items) {
      const li = document.createElement("li");
      li.innerHTML = `<span><span class="type-tag">${TIMELINE_ICON[e.type] || ""}</span>${e.date} — ${escapeHtml(e.summary)}</span>`;
      ul.appendChild(li);
    }
  };
  renderList($("timelinePreview"), events.slice(0, 5));
  renderList($("timelineFull"), events);
}

// ---- 提醒歷史紀錄 ----
async function loadReminderHistory() {
  const rows = await api("/api/reminders/history");
  const mine = rows.filter((r) => r.pet_id === currentPetId);
  const ul = $("reminderHistoryList");
  ul.innerHTML = "";
  if (mine.length === 0) {
    ul.innerHTML = `<li class="empty-hint">🔕 尚無推播紀錄</li>`;
    return;
  }
  for (const r of mine) {
    const li = document.createElement("li");
    li.innerHTML = `<span>${r.notified_at} — ${escapeHtml(r.title)} (到期日 ${r.due_date})</span>`;
    ul.appendChild(li);
  }
}

// ---- 通用子紀錄清單 + 刪除 ----
async function loadRecords(table, listId, formatFn) {
  const rows = await api(`/api/pets/${currentPetId}/${table}`);
  const ul = $(listId);
  ul.innerHTML = "";
  for (const r of rows) {
    const li = document.createElement("li");
    const span = document.createElement("span");
    span.textContent = formatFn(r);
    const delBtn = document.createElement("button");
    delBtn.textContent = "刪除";
    delBtn.className = "del-btn";
    delBtn.addEventListener("click", async () => {
      await api(`/api/records/${table}/${r.id}`, { method: "DELETE" });
      await loadRecords(table, listId, formatFn);
      if (table === "weight_logs") await loadWeightLogs();
      if (["weight_logs", "vet_visits", "vaccine_records", "deworming_records", "bcs_logs", "lab_results"].includes(table)) await loadTimeline();
    });
    li.appendChild(span);
    li.appendChild(delBtn);
    ul.appendChild(li);
  }
}

function bindSimpleForm(formId, table, listId, formatFn, extraTransform) {
  $(formId).addEventListener("submit", async (e) => {
    e.preventDefault();
    const form = e.target;
    const body = Object.fromEntries(new FormData(form).entries());
    if (extraTransform) extraTransform(body);
    Object.keys(body).forEach((k) => { if (body[k] === "") delete body[k]; });
    try {
      await api(`/api/pets/${currentPetId}/${table}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      form.reset();
      await loadRecords(table, listId, formatFn);
      if (["weight_logs", "vet_visits", "vaccine_records", "deworming_records", "bcs_logs", "lab_results"].includes(table)) await loadTimeline();
    } catch (err) {
      alert(err.message);
    }
  });
}

const CATEGORY_LABELS = { other: "其他", 洗牙: "洗牙", 美容洗澡: "美容洗澡", 趾甲修剪: "趾甲修剪", 心絲蟲預防: "心絲蟲預防", 除蚤: "除蚤", 回診: "回診" };

bindSimpleForm("vetForm", "vet_visits", "vetList", (r) => `${r.visit_date} — ${r.reason || ""} ${r.notes ? "(" + r.notes + ")" : ""}`);
bindSimpleForm("vaccineForm", "vaccine_records", "vaccineList", (r) => `${r.item_name} — 施打:${r.given_date}${r.next_due_date ? " 下次到期:" + r.next_due_date : ""}`);
bindSimpleForm("dewormingForm", "deworming_records", "dewormingList", (r) => `${r.item_name} — 施打:${r.given_date}${r.next_due_date ? " 下次到期:" + r.next_due_date : ""}`);
bindSimpleForm("dietEntryForm", "diet_entries", "dietEntryList", (r) => `${r.entry_date} — ${r.food_name} ${r.amount_grams ? r.amount_grams + "g" : ""}`);
bindSimpleForm("labForm", "lab_results", "labList", (r) => `${r.test_date} — ${r.item_name}: ${r.value ?? ""}${r.unit || ""} ${r.ref_range ? "(參考:" + r.ref_range + ")" : ""}`);
bindSimpleForm("bcsForm", "bcs_logs", "bcsList", (r) => `${r.recorded_at} — ${r.score}/9 ${r.notes ? "(" + r.notes + ")" : ""}`, (body) => {
  body.score = Number(body.score);
});
bindSimpleForm("reminderForm", "custom_reminders", "reminderList",
  (r) => `${r.due_date} — [${CATEGORY_LABELS[r.category] || r.category}] ${r.title} (提前${r.remind_days_before}天${r.repeat_days ? "，每" + r.repeat_days + "天重複" : ""})`,
  (body) => {
    body.remind_days_before = body.remind_days_before ? Number(body.remind_days_before) : 3;
    body.repeat_days = body.repeat_days ? Number(body.repeat_days) : null;
    if (body.repeat_days === null) delete body.repeat_days;
  });

// ---- 體重紀錄 + 圖表 ----
$("weightForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.target;
  const body = { weight_kg: Number(form.weight_kg.value), recorded_at: form.recorded_at.value };
  try {
    await api(`/api/pets/${currentPetId}/weight_logs`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    form.reset();
    await loadWeightLogs();
    await loadTimeline();
  } catch (err) {
    alert(err.message);
  }
});

async function loadWeightLogs() {
  const rows = await api(`/api/pets/${currentPetId}/weight_logs`);
  const sorted = [...rows].sort((a, b) => a.recorded_at.localeCompare(b.recorded_at));
  const ctx = $("weightChart").getContext("2d");
  if (weightChart) weightChart.destroy();
  weightChart = new Chart(ctx, {
    type: "line",
    data: {
      labels: sorted.map((r) => r.recorded_at),
      datasets: [{ label: "體重(kg)", data: sorted.map((r) => r.weight_kg), borderColor: "#e08a3e", backgroundColor: "#e08a3e33", tension: .2 }],
    },
    options: { responsive: true, plugins: { legend: { display: false } } },
  });
  await loadRecords("weight_logs", "weightList", (r) => `${r.recorded_at} — ${r.weight_kg}kg`);
}

// ---- 飲食熱量計算 ----
async function loadFoodPresets(species) {
  const presets = await api(`/api/food_presets?species=${species}`);
  const select = $("foodPresetSelect");
  select.innerHTML = `<option value="">常見飼料快速帶入(選填)</option>`;
  for (const p of presets) {
    const opt = document.createElement("option");
    opt.value = p.kcal_per_100g;
    opt.textContent = `${p.brand} ${p.product_name} (${p.kcal_per_100g} kcal/100g)`;
    select.appendChild(opt);
  }
}

$("foodPresetSelect").addEventListener("change", (e) => {
  if (e.target.value) $("dietForm").food_kcal_per_100g.value = e.target.value;
});

$("dietForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.target;
  const body = {};
  if (form.weight_kg.value) body.weight_kg = Number(form.weight_kg.value);
  if (form.food_kcal_per_100g.value) body.food_kcal_per_100g = Number(form.food_kcal_per_100g.value);
  if (form.meals_per_day.value) body.meals_per_day = Number(form.meals_per_day.value);
  try {
    const result = await api(`/api/pets/${currentPetId}/diet_calc`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    let html = `體重 ${result.weight_kg}kg → RER ${result.rer_kcal} kcal/day，建議每日總熱量(MER) <b>${result.mer_kcal} kcal/day</b>（生活型態係數 ${result.factor}）`;
    if (result.feeding_grams_per_day) html += `<br>建議每日餵食量 <b>${result.feeding_grams_per_day} g</b>`;
    if (result.meals_grams) html += `<br>分${result.meals_grams.length}餐：${result.meals_grams.map((g) => g + "g").join(" + ")}`;
    if (result.weight_goal_kg) html += `<br>體重目標 ${result.weight_goal_kg}kg（${result.weight_goal_delta_kg > 0 ? "還需增重" : result.weight_goal_delta_kg < 0 ? "還需減重" : "已達標"} ${Math.abs(result.weight_goal_delta_kg)}kg）`;
    html += `<br><small>此為通用公式估算起點，實際餵食量請搭配體態評分持續調整，非精確醫囑。</small>`;
    $("dietResult").innerHTML = html;
  } catch (err) {
    $("dietResult").textContent = err.message;
  }
});

// ======================= 每月花費 =======================
const EXPENSE_CATEGORIES = ["飼料", "零食", "看診", "疫苗驅蟲", "美容", "保健品", "用品", "其他"];
let currentExpenseMonth = null; // "YYYY-MM"
let expenseTrendChart = null;

function monthKey(d) { return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`; }
function monthLabel(key) { const [y, m] = key.split("-"); return `${y}年${Number(m)}月`; }

async function loadExpensesView() {
  if (!currentExpenseMonth) currentExpenseMonth = monthKey(new Date());
  if ($("expenseForm").category.options.length <= 1) {
    for (const c of EXPENSE_CATEGORIES) {
      const opt = document.createElement("option");
      opt.value = c; opt.textContent = c;
      $("expenseForm").category.appendChild(opt);
    }
  }
  const pets = await api("/api/pets");
  const petSelect = $("expenseForm").pet_id;
  petSelect.innerHTML = `<option value="">不歸屬特定寵物</option>`;
  for (const pet of pets) {
    const opt = document.createElement("option");
    opt.value = pet.id; opt.textContent = pet.name;
    petSelect.appendChild(opt);
  }
  await Promise.all([loadExpensesForMonth(), loadExpenseTrendChart()]);
}

$("expensePrevMonth").addEventListener("click", () => {
  const [y, m] = currentExpenseMonth.split("-").map(Number);
  const d = new Date(y, m - 2, 1); // m是1-based, 減2再+1個月效果等於往前一個月
  currentExpenseMonth = monthKey(d);
  loadExpensesForMonth();
});
$("expenseNextMonth").addEventListener("click", () => {
  const [y, m] = currentExpenseMonth.split("-").map(Number);
  const d = new Date(y, m, 1); // m是1-based, 這裡剛好是下個月(0-based的話會是同月, +1後變下月)
  currentExpenseMonth = monthKey(d);
  loadExpensesForMonth();
});

async function loadExpensesForMonth() {
  $("expenseMonthLabel").textContent = monthLabel(currentExpenseMonth);
  const rows = await api(`/api/expenses?month=${currentExpenseMonth}`);
  const total = rows.reduce((sum, r) => sum + r.amount, 0);
  $("expenseMonthTotal").textContent = `NT$${Math.round(total).toLocaleString()}`;

  const byCategory = new Map();
  for (const r of rows) byCategory.set(r.category, (byCategory.get(r.category) || 0) + r.amount);
  const catUl = $("expenseCategoryList");
  catUl.innerHTML = "";
  if (byCategory.size === 0) {
    catUl.innerHTML = `<li class="empty-hint">📭 這個月還沒有花費紀錄</li>`;
  } else {
    for (const [cat, amt] of [...byCategory.entries()].sort((a, b) => b[1] - a[1])) {
      const li = document.createElement("li");
      li.innerHTML = `<span><span class="category-tag cat-${cat}">${cat}</span></span><b>NT$${Math.round(amt).toLocaleString()}</b>`;
      catUl.appendChild(li);
    }
  }

  const listUl = $("expenseList");
  listUl.innerHTML = "";
  if (rows.length === 0) {
    listUl.innerHTML = `<li class="empty-hint">🧾 這個月還沒有任何一筆紀錄</li>`;
    return;
  }
  for (const r of rows) {
    const li = document.createElement("li");
    const span = document.createElement("span");
    span.innerHTML = `<span class="category-tag cat-${r.category}">${r.category}</span>${r.expense_date}${r.pet_name ? " · " + escapeHtml(r.pet_name) : ""}${r.notes ? " · " + escapeHtml(r.notes) : ""}`;
    const right = document.createElement("span");
    right.innerHTML = `<b>NT$${Math.round(r.amount).toLocaleString()}</b> `;
    const delBtn = document.createElement("button");
    delBtn.textContent = "刪除"; delBtn.className = "del-btn";
    delBtn.addEventListener("click", async () => { await api(`/api/expenses/${r.id}`, { method: "DELETE" }); await loadExpensesForMonth(); await loadExpenseTrendChart(); });
    right.appendChild(delBtn);
    li.appendChild(span); li.appendChild(right);
    listUl.appendChild(li);
  }
}

async function loadExpenseTrendChart() {
  const rows = await api("/api/expenses/summary?months=6");
  const ctx = $("expenseTrendChart").getContext("2d");
  if (expenseTrendChart) expenseTrendChart.destroy();
  expenseTrendChart = new Chart(ctx, {
    type: "bar",
    data: {
      labels: rows.map((r) => monthLabel(r.month)),
      datasets: [{ label: "花費", data: rows.map((r) => r.total), backgroundColor: "#e08a3e99", borderRadius: 4 }],
    },
    options: { responsive: true, plugins: { legend: { display: false } }, scales: { y: { title: { display: true, text: "TWD" } } } },
  });
}

$("expenseForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.target;
  const body = {
    category: form.category.value,
    amount: Number(form.amount.value),
    expense_date: form.expense_date.value,
    pet_id: form.pet_id.value ? Number(form.pet_id.value) : null,
    notes: form.notes.value.trim() || null,
  };
  try {
    await api("/api/expenses", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    form.reset();
    currentExpenseMonth = body.expense_date.slice(0, 7);
    await loadExpensesForMonth();
    await loadExpenseTrendChart();
  } catch (err) {
    alert(err.message);
  }
});

// ======================= 寵物狀態總覽 =======================
async function loadPetStatus() {
  const pets = await api("/api/pets/status");
  const container = $("statusCards");
  container.innerHTML = "";
  if (pets.length === 0) {
    container.innerHTML = `<div class="empty-hint">📋 還沒有寵物資料，先到「我的寵物」新增一隻吧！</div>`;
    return;
  }
  for (const pet of pets) {
    const card = document.createElement("div");
    card.className = `pet-card status-card species-${pet.species}`;
    const age = formatAge(pet.birthday);
    card.innerHTML = `
      ${pet.due_reminders > 0 ? `<span class="status-badge">${pet.due_reminders}</span>` : ""}
      <div class="emoji">${SPECIES_EMOJI[pet.species] || "🐾"}</div>
      <h3>${escapeHtml(pet.name)}</h3>
      <p>${escapeHtml(pet.breed || "")}${age ? " · " + age : ""}</p>
      <div class="status-row">
        <span>⚖️ ${pet.latest_weight ? pet.latest_weight.weight_kg + "kg" : "—"}</span>
        <span>📏 ${pet.latest_bcs ? pet.latest_bcs.score + "/9" : "—"}</span>
      </div>
    `;
    card.addEventListener("click", () => { switchTopView("pets"); openDashboard(pet.id); });
    container.appendChild(card);
  }
}

// ======================= 用品比價 =======================
const PLATFORM_LABELS = { pchome: "PChome" };
const CATEGORY_EMOJI = { 零食: "🍖", 飼料: "🥣", 保健品: "💊", 用品: "🧸" };

async function loadPlatformStatus() {
  const platforms = await api("/api/platforms");
  const container = $("platformStatus");
  container.innerHTML = "";
  for (const p of platforms) {
    const span = document.createElement("span");
    span.className = `badge ${p.supported ? "ok" : "no"}`;
    span.textContent = `${PLATFORM_LABELS[p.platform] || p.platform}: ${p.supported ? "可用" : "尚未支援"}`;
    container.appendChild(span);
  }
}

async function loadProducts() {
  const products = await api("/api/products");
  const container = $("productCards");
  container.innerHTML = "";
  if (products.length === 0) {
    container.innerHTML = `<div class="empty-hint">🛒 還沒有追蹤商品，點右上「+ 新增商品」開始追蹤零食/飼料/保健品/用品的價格。</div>`;
    return;
  }
  for (const product of products) {
    const card = document.createElement("div");
    card.className = "pet-card product-card";
    card.innerHTML = `<div class="emoji">${CATEGORY_EMOJI[product.category] || "📦"}</div><h3>${escapeHtml(product.name)}</h3><span class="category-tag cat-${product.category}">${escapeHtml(product.category)}</span>`;
    card.addEventListener("click", () => openProductDashboard(product.id));
    container.appendChild(card);
  }
}

$("addProductBtn").addEventListener("click", () => { $("productForm").reset(); $("productFormModal").style.display = "flex"; });
$("productFormCancel").addEventListener("click", () => { $("productFormModal").style.display = "none"; });

$("productForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.target;
  const body = Object.fromEntries(new FormData(form).entries());
  try {
    await api("/api/products", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    $("productFormModal").style.display = "none";
    await loadProducts();
  } catch (err) {
    alert(err.message);
  }
});

async function openProductDashboard(productId) {
  currentProductId = productId;
  const products = await api("/api/products");
  const product = products.find((p) => p.id === productId);
  if (!product) return;
  $("productListView").style.display = "none";
  $("productDashboard").style.display = "block";
  $("dashProductName").textContent = `${product.name} (${product.category})`;
  $("deleteProductBtn").onclick = async () => {
    if (!confirm(`確定要刪除「${product.name}」這個追蹤商品嗎？`)) return;
    await api(`/api/products/${productId}`, { method: "DELETE" });
    await backToProductList();
  };
  await Promise.all([loadProductPriceChart(), loadProductListings()]);
}

$("productBackBtn").addEventListener("click", backToProductList);
async function backToProductList() {
  currentProductId = null;
  $("productDashboard").style.display = "none";
  $("productListView").style.display = "block";
  await loadProducts();
}

async function loadProductPriceChart() {
  const rows = await api(`/api/products/${currentProductId}/price_history`);
  const seriesMap = new Map();
  for (const r of rows) {
    const key = `${r.platform}:${r.external_id}`;
    if (!seriesMap.has(key)) {
      seriesMap.set(key, { label: `${PLATFORM_LABELS[r.platform] || r.platform} - ${(r.title || "").slice(0, 20)}`, points: [] });
    }
    seriesMap.get(key).points.push({ x: r.scraped_at, y: r.price });
  }
  const colors = ["#e08a3e", "#4f7a8c", "#8c4f6a", "#6a8c4f", "#7a4f8c"];
  const datasets = [...seriesMap.values()].map((s, i) => ({
    label: s.label, data: s.points, borderColor: colors[i % colors.length],
    backgroundColor: colors[i % colors.length] + "33", tension: 0.2, spanGaps: true,
  }));
  const ctx = $("productPriceChart").getContext("2d");
  if (productPriceChart) productPriceChart.destroy();
  productPriceChart = new Chart(ctx, {
    type: "line",
    data: { datasets },
    options: {
      responsive: true, parsing: false,
      scales: { x: { type: "time", time: { unit: "day" } }, y: { title: { display: true, text: "TWD" } } },
      plugins: { legend: { display: datasets.length <= 6 } },
    },
  });
}

async function loadProductListings() {
  const rows = await api(`/api/products/${currentProductId}/listings`);
  const ul = $("productListingList");
  ul.innerHTML = "";
  if (rows.length === 0) {
    ul.innerHTML = `<li class="empty-hint">⏳ 尚未抓到任何在架商品。新增商品後要等排程(或手動觸發 /api/internal/run-product-scrape)跑過一次才會有資料。</li>`;
    return;
  }
  for (const r of rows) {
    const li = document.createElement("li");
    li.innerHTML = `<span><span class="platform-tag">${PLATFORM_LABELS[r.platform] || r.platform}</span><a href="${r.url}" target="_blank" rel="noopener">${escapeHtml(r.title || r.url)}</a></span><b>NT$${Math.round(r.price).toLocaleString()}</b>`;
    ul.appendChild(li);
  }
}

// ======================= 推播訂閱 =======================
function _urlBase64ToUint8Array(base64String) {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(base64);
  const arr = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i++) arr[i] = raw.charCodeAt(i);
  return arr;
}

function pushSupported() {
  return "serviceWorker" in navigator && "PushManager" in window;
}

async function updatePushButtonState() {
  const btn = $("pushToggleBtn");
  const status = $("pushStatus");
  if (!pushSupported()) {
    btn.disabled = true;
    btn.textContent = "🔕 不支援推播";
    status.textContent = "iOS要先「加入主畫面」變成App後才支援推播。";
    return;
  }
  const reg = await navigator.serviceWorker.getRegistration();
  const sub = reg ? await reg.pushManager.getSubscription() : null;
  if (sub) {
    btn.textContent = "🔕 關閉提醒推播";
    btn.classList.add("on");
    status.textContent = "已開啟，到期提醒會推播到這個裝置。";
  } else {
    btn.textContent = "🔔 開啟提醒推播";
    btn.classList.remove("on");
    status.textContent = "";
  }
}

async function togglePush() {
  const btn = $("pushToggleBtn");
  btn.disabled = true;
  try {
    const reg = await navigator.serviceWorker.register("/sw.js");
    const existing = await reg.pushManager.getSubscription();
    if (existing) {
      await existing.unsubscribe();
      await api("/api/push/unsubscribe", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ endpoint: existing.endpoint }) });
    } else {
      const perm = await Notification.requestPermission();
      if (perm !== "granted") {
        $("pushStatus").textContent = "沒有取得通知授權。";
        return;
      }
      const keyData = await api("/api/push/vapid_public_key");
      const newSub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: _urlBase64ToUint8Array(keyData.publicKey) });
      await api("/api/push/subscribe", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(newSub.toJSON()) });
    }
  } catch (e) {
    console.error("[push]", e);
    $("pushStatus").textContent = "操作失敗，請稍後再試。";
  } finally {
    btn.disabled = false;
    updatePushButtonState();
  }
}

if (pushSupported()) {
  $("pushToggleBtn").addEventListener("click", togglePush);
  updatePushButtonState();
}

loadPets();
