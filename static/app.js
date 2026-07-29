const apiBase = "/";

const pacienteSelect = document.getElementById("paciente-select");
const medicoSelect = document.getElementById("medico-select");
const resultado = document.getElementById("resultado");
const calendarEl = document.getElementById("calendar");
const calendarTitle = document.getElementById("calendar-title");
const slotsGrid = document.getElementById("slots-grid");
const selectedDateLabel = document.getElementById("selected-date-label");
const dateInput = document.getElementById("cita-fecha");
const horaInicioInput = document.getElementById("cita-hora-inicio");
const horaFinInput = document.getElementById("cita-hora-fin");
const operarioForm = document.getElementById("form-operario");
const operarioCorreo = document.getElementById("operario-correo");
const operarioPassword = document.getElementById("operario-password");
const operarioInfo = document.getElementById("operario-info");
const operarioStatus = document.getElementById("operario-status");
const operarioLogout = document.getElementById("operario-logout");
const reminderResults = document.getElementById("reminder-results");
const appShell = document.getElementById("app-shell");
const agendaSection = document.getElementById("agenda-section");
const loginBlock = document.getElementById("login-block");
const registerBlock = document.getElementById("register-block");
const loginError = document.getElementById("login-error");
const registerError = document.getElementById("register-error");
const operarioRegisterForm = document.getElementById("form-operario-register");
const showRegisterButton = document.getElementById("show-register");
const showLoginButton = document.getElementById("show-login");
const operarioNombre = document.getElementById("operario-nombre");
const operarioRegCorreo = document.getElementById("operario-reg-correo");
const operarioRegPassword = document.getElementById("operario-reg-password");
const operarioRegTelefono = document.getElementById("operario-reg-telefono");

let authToken = localStorage.getItem("authToken") || null;

const state = {
  usuarios: [],
  medicos: [],
  citas: [],
  currentMonth: new Date(),
  selectedDoctorId: null,
  selectedDate: null,
  selectedSlot: null,
};

function formatDateInput(date) {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

function formatTime(minutes) {
  const hours = String(Math.floor(minutes / 60)).padStart(2, "0");
  const mins = String(minutes % 60).padStart(2, "0");
  return `${hours}:${mins}`;
}

function toMinutes(value) {
  const [hours, minutes] = value.split(":").map(Number);
  return hours * 60 + minutes;
}

function overlaps(startA, endA, startB, endB) {
  return startA < endB && endA > startB;
}

function getAvailableSlots(doctorId, dateString) {
  const totalSlots = [];
  for (let minutes = 8 * 60; minutes < 21 * 60; minutes += 30) {
    totalSlots.push({ start: formatTime(minutes), end: formatTime(minutes + 30) });
  }

  const doctorCitas = state.citas.filter((cita) => cita.medico_id === doctorId && cita.fecha === dateString);
  return totalSlots.filter((slot) => {
    const slotStart = toMinutes(slot.start);
    const slotEnd = toMinutes(slot.end);
    return !doctorCitas.some((cita) => {
      const citaStart = toMinutes(cita.hora_inicio);
      const citaEnd = toMinutes(cita.hora_fin);
      return overlaps(slotStart, slotEnd, citaStart, citaEnd);
    });
  });
}

function getDayStatus(doctorId, dateString) {
  const slots = getAvailableSlots(doctorId, dateString);
  const total = 26;
  if (slots.length === total) {
    return { label: "Libre", css: "status-free" };
  }
  if (slots.length === 0) {
    return { label: "Completo", css: "status-full" };
  }
  return { label: "Parcial", css: "status-partial" };
}

async function fetchJSON(path, options = {}) {
  options.headers = options.headers || {};
  if (authToken) {
    options.headers.Authorization = `Bearer ${authToken}`;
  }
  const res = await fetch(apiBase + path, options);
  if (!res.ok) {
    const error = await res.json().catch(() => ({}));
    throw new Error(error.detail || res.statusText);
  }
  return res.json();
}

function updateOperarioUI(user) {
  operarioInfo.classList.remove("hidden");
  operarioStatus.textContent = `Operario: ${user.nombre} (${user.correo})`;
  loginBlock.classList.add("hidden");
  registerBlock.classList.add("hidden");
  appShell.classList.remove("hidden");
  agendaSection.classList.remove("hidden");
}

function logoutOperario() {
  authToken = null;
  localStorage.removeItem("authToken");
  operarioInfo.classList.add("hidden");
  loginBlock.classList.remove("hidden");
  registerBlock.classList.add("hidden");
  operarioStatus.textContent = "Sesión cerrada";
  reminderResults.innerHTML = "";
  appShell.classList.add("hidden");
  agendaSection.classList.add("hidden");
}

async function loadOperario() {
  if (!authToken) {
    return;
  }
  try {
    const user = await fetchJSON("operario/me");
    updateOperarioUI(user);
    await cargarDatos();
  } catch (error) {
    logoutOperario();
  }
}

function showLogin() {
  loginBlock.classList.remove("hidden");
  registerBlock.classList.add("hidden");
  loginError.classList.add("hidden");
  registerError.classList.add("hidden");
}

function showRegister() {
  loginBlock.classList.add("hidden");
  registerBlock.classList.remove("hidden");
  loginError.classList.add("hidden");
  registerError.classList.add("hidden");
}

function showLoginPanel() {
  loginBlock.classList.remove("hidden");
  registerBlock.classList.add("hidden");
  loginError.classList.add("hidden");
  registerError.classList.add("hidden");
}

async function loadSetupStatus() {
  try {
    const status = await fetchJSON("setup/status");
    if (status.has_operario) {
      showLogin();
    } else {
      showRegister();
    }
  } catch (error) {
    showLogin();
  }
}

async function loginOperario(event) {
  event.preventDefault();
  const correo = operarioCorreo.value.trim();
  const contrasena = operarioPassword.value.trim();
  if (!correo || !contrasena) {
    loginError.textContent = "Ingresa correo y contraseña para iniciar sesión.";
    loginError.classList.remove("hidden");
    return;
  }
  try {
    const data = await fetchJSON("login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ correo, contrasena }),
    });
    authToken = data.access_token;
    localStorage.setItem("authToken", authToken);
    operarioCorreo.value = "";
    operarioPassword.value = "";
    await loadOperario();
  } catch (error) {
    loginError.textContent = error.message;
    loginError.classList.remove("hidden");
  }
}

async function cargarDatos() {
  const [usuarios, medicos, citas] = await Promise.all([fetchJSON("usuarios"), fetchJSON("medicos"), fetchJSON("citas")]);
  state.usuarios = usuarios;
  state.medicos = medicos;
  state.citas = citas;

  pacienteSelect.innerHTML = "";
  medicoSelect.innerHTML = "";

  usuarios.forEach((usuario) => {
    if (usuario.rol === "paciente") {
      pacienteSelect.innerHTML += `<option value="${usuario.id}">${usuario.nombre || usuario.telefono}</option>`;
    }
  });

  medicos.forEach((medico) => {
    medicoSelect.innerHTML += `<option value="${medico.id}">${medico.nombre || medico.correo}</option>`;
  });

  if (!state.selectedDoctorId && medicos.length) {
    state.selectedDoctorId = medicos[0].id;
    medicoSelect.value = state.selectedDoctorId;
  }

  if (!state.selectedDate) {
    state.selectedDate = formatDateInput(new Date());
    dateInput.value = state.selectedDate;
  }

  renderCalendar();
  renderSlots();
  renderAgenda();
}

function renderCalendar() {
  const year = state.currentMonth.getFullYear();
  const month = state.currentMonth.getMonth();
  calendarTitle.textContent = new Date(year, month).toLocaleDateString("es-ES", { month: "long", year: "numeric" });

  const firstDay = new Date(year, month, 1);
  const lastDay = new Date(year, month + 1, 0);
  const startOffset = firstDay.getDay() === 0 ? 6 : firstDay.getDay() - 1;
  const totalCells = Math.ceil((startOffset + lastDay.getDate()) / 7) * 7;

  const dayNames = ["L", "M", "X", "J", "V", "S", "D"];
  const cells = [
    ...dayNames.map((day) => `<div class="calendar-weekday">${day}</div>`),
    ...Array.from({ length: totalCells }, (_, index) => {
      const dayNumber = index - startOffset + 1;
      const isCurrentMonth = dayNumber > 0 && dayNumber <= lastDay.getDate();
      if (!isCurrentMonth) {
        return '<div class="calendar-day muted"></div>';
      }

      const date = new Date(year, month, dayNumber);
      const dateString = formatDateInput(date);
      const status = state.selectedDoctorId ? getDayStatus(state.selectedDoctorId, dateString) : { label: "—", css: "status-neutral" };
      const isSelected = state.selectedDate === dateString;
      return `
        <button type="button" class="calendar-day ${isSelected ? "selected" : ""}" data-date="${dateString}">
          <span>${dayNumber}</span>
          <small class="${status.css}">${status.label}</small>
        </button>
      `;
    }),
  ];

  calendarEl.innerHTML = cells.join("");
}

function renderSlots() {
  const selectedDate = state.selectedDate;
  selectedDateLabel.textContent = selectedDate ? new Date(`${selectedDate}T12:00:00`).toLocaleDateString("es-ES", { weekday: "long", day: "numeric", month: "long" }) : "Selecciona un día";

  if (!state.selectedDoctorId || !selectedDate) {
    slotsGrid.innerHTML = '<p class="empty">Selecciona un médico y una fecha para ver los horarios.</p>';
    return;
  }

  const slots = getAvailableSlots(state.selectedDoctorId, selectedDate);
  if (!slots.length) {
    slotsGrid.innerHTML = '<p class="empty">No hay horarios libres para esta fecha. Prueba otro día.</p>';
    return;
  }

  slotsGrid.innerHTML = slots
    .map((slot) => {
      const selected = state.selectedSlot === `${slot.start}-${slot.end}`;
      return `
        <button type="button" class="slot-pill ${selected ? "active" : ""}" data-start="${slot.start}" data-end="${slot.end}">
          ${slot.start} - ${slot.end}
        </button>
      `;
    })
    .join("");
}

function renderAgenda() {
  const sorted = [...state.citas].sort((a, b) => `${a.fecha} ${a.hora_inicio}`.localeCompare(`${b.fecha} ${b.hora_inicio}`));
  if (!sorted.length) {
    resultado.innerHTML = '<p class="empty">No hay citas agendadas aún.</p>';
    return;
  }

  resultado.innerHTML = sorted
    .slice(0, 8)
    .map((cita) => {
      const medico = state.medicos.find((item) => item.id === cita.medico_id);
      const paciente = state.usuarios.find((item) => item.id === cita.paciente_id);
      return `
        <div class="card">
          <strong>${cita.fecha} · ${cita.hora_inicio} - ${cita.hora_fin}</strong>
          <div>Paciente: ${paciente ? paciente.nombre : `#${cita.paciente_id}`}</div>
          <div>Médico: ${medico ? medico.nombre : `#${cita.medico_id}`}</div>
          <div>Estado: ${cita.estado}</div>
          <div>Motivo: ${cita.motivo || "-"}</div>
          <div class="card-actions">
            <button class="primary remind-btn" data-id="${cita.id}">📲 Enviar WA</button>
            <button class="secondary cancel-btn" data-id="${cita.id}">Cancelar</button>
            <button class="secondary delete-btn" data-id="${cita.id}">Eliminar</button>
          </div>
        </div>
      `;
    })
    .join("");
}

async function registrarPaciente(event) {
  event.preventDefault();
  
  const nombre = document.getElementById("paciente-nombre").value.trim();
  const telefono = document.getElementById("paciente-telefono").value.trim();

  if (!nombre || !telefono) {
    alert("Por favor, ingresa el nombre y el teléfono.");
    return;
  }

  try {
    await fetchJSON("usuarios", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ nombre, telefono }),
    });

    await cargarDatos();
    event.target.reset();
    alert("Paciente registrado con éxito.");
  } catch (error) {
    alert("Error al registrar: " + error.message);
  }
}

async function agendarCita(event) {
  event.preventDefault();
  const paciente_id = Number(pacienteSelect.value);
  const medico_id = Number(medicoSelect.value);
  const fecha = dateInput.value;
  const hora_inicio = horaInicioInput.value;
  const hora_fin = horaFinInput.value;
  const motivo = document.getElementById("cita-motivo").value.trim();

  if (!fecha || !hora_inicio || !hora_fin) {
    alert("Selecciona un día y una franja horaria antes de confirmar.");
    return;
  }

  await fetchJSON("citas", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ paciente_id, medico_id, fecha, hora_inicio, hora_fin, motivo, estado: "pendiente" }),
  });

  await cargarDatos();
  state.selectedSlot = null;
  event.target.reset();
  document.getElementById("cita-fecha").value = state.selectedDate;
  horaInicioInput.value = "";
  horaFinInput.value = "";
  alert("Cita agendada con éxito.");
}

async function cancelarCita(citaId) {
  if (!confirm("¿Seguro quieres cancelar esta cita?")) {
    return;
  }
  await fetchJSON(`citas/${citaId}/cancelar`, { method: "POST" });
  await cargarDatos();
}

async function eliminarCita(citaId) {
  if (!confirm("¿Seguro quieres eliminar esta cita?")) {
    return;
  }
  await fetchJSON(`citas/${citaId}`, { method: "DELETE" });
  await cargarDatos();
}

async function enviarRecordatorioCita(citaId) {
  try {
    const res = await fetchJSON(`whatsapp/remind/${citaId}`, { method: "POST" });
    alert(res.detail);
  } catch (error) {
    alert("Error: " + error.message);
  }
}

async function registerOperario(event) {
  event.preventDefault();
  const nombre = operarioNombre.value.trim();
  const correo = operarioRegCorreo.value.trim();
  const contrasena = operarioRegPassword.value.trim();
  const telefono = operarioRegTelefono.value.trim();
  if (!nombre || !correo || !contrasena) {
    registerError.textContent = "Completa nombre, correo y contraseña.";
    registerError.classList.remove("hidden");
    return;
  }
  try {
    const data = await fetchJSON("operarios/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ nombre, correo, contrasena, telefono }),
    });
    authToken = data.access_token;
    localStorage.setItem("authToken", authToken);
    operarioNombre.value = "";
    operarioRegCorreo.value = "";
    operarioRegPassword.value = "";
    operarioRegTelefono.value = "";
    await loadOperario();
  } catch (error) {
    registerError.textContent = error.message;
    registerError.classList.remove("hidden");
  }
}

function attachEvents() {
  document.getElementById("form-paciente").addEventListener("submit", registrarPaciente);
  document.getElementById("form-cita").addEventListener("submit", agendarCita);
  document.getElementById("btn-refresh").addEventListener("click", cargarDatos);
  document.getElementById("prev-month").addEventListener("click", () => {
    state.currentMonth = new Date(state.currentMonth.getFullYear(), state.currentMonth.getMonth() - 1, 1);
    renderCalendar();
  });
  document.getElementById("next-month").addEventListener("click", () => {
    state.currentMonth = new Date(state.currentMonth.getFullYear(), state.currentMonth.getMonth() + 1, 1);
    renderCalendar();
  });

  medicoSelect.addEventListener("change", (event) => {
    state.selectedDoctorId = Number(event.target.value);
    state.selectedSlot = null;
    renderCalendar();
    renderSlots();
  });

  dateInput.addEventListener("change", (event) => {
    state.selectedDate = event.target.value;
    state.selectedSlot = null;
    renderSlots();
  });

  operarioForm.addEventListener("submit", loginOperario);
  operarioRegisterForm.addEventListener("submit", registerOperario);
  showRegisterButton.addEventListener("click", showRegister);
  showLoginButton.addEventListener("click", showLoginPanel);
  operarioLogout.addEventListener("click", logoutOperario);
  
  resultado.addEventListener("click", async (event) => {
    const cancelButton = event.target.closest(".cancel-btn");
    const deleteButton = event.target.closest(".delete-btn");
    const remindButton = event.target.closest(".remind-btn");

    if (remindButton) {
      const citaId = remindButton.dataset.id;
      await enviarRecordatorioCita(citaId);
      return;
    }
    if (cancelButton) {
      const citaId = cancelButton.dataset.id;
      await cancelarCita(citaId);
      return;
    }
    if (deleteButton) {
      const citaId = deleteButton.dataset.id;
      await eliminarCita(citaId);
      return;
    }
  });

  calendarEl.addEventListener("click", (event) => {
    const button = event.target.closest(".calendar-day");
    if (!button) {
      return;
    }
    state.selectedDate = button.dataset.date;
    dateInput.value = state.selectedDate;
    state.selectedSlot = null;
    renderCalendar();
    renderSlots();
  });

  slotsGrid.addEventListener("click", (event) => {
    const button = event.target.closest(".slot-pill");
    if (!button) {
      return;
    }
    state.selectedSlot = `${button.dataset.start}-${button.dataset.end}`;
    horaInicioInput.value = button.dataset.start;
    horaFinInput.value = button.dataset.end;
    renderSlots();
  });
}

window.addEventListener("DOMContentLoaded", async () => {
  dateInput.min = formatDateInput(new Date());
  state.selectedDate = formatDateInput(new Date());
  dateInput.value = state.selectedDate;
  attachEvents();
  await loadSetupStatus();
  await loadOperario();
});