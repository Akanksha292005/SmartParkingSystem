// Booking page interactivity: vehicle type toggle, floor tabs, live slot grid

const RATES = { car: { base: 30, hourly: 20 }, bike: { base: 15, hourly: 10 } };

let state = {
  vehicleType: 'car',
  floorId: window.FLOORS && window.FLOORS.length ? window.FLOORS[0].id : null,
  selectedSlot: null,
  pollTimer: null,
};

function calcEstimate(hours) {
  const r = RATES[state.vehicleType];
  if (hours <= 1) return r.base;
  return r.base + Math.ceil(hours - 1) * r.hourly;
}

const ICONS = {
  car: '<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M5 11l1.5-4.5A2 2 0 0 1 8.4 5h7.2a2 2 0 0 1 1.9 1.5L19 11" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/><path d="M3.5 11h17a1.5 1.5 0 0 1 1.5 1.5V16a1 1 0 0 1-1 1h-1.2M3.5 11A1.5 1.5 0 0 0 2 12.5V16a1 1 0 0 0 1 1h1.2" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/><circle cx="7.5" cy="17" r="1.7" stroke="currentColor" stroke-width="1.6"/><circle cx="16.5" cy="17" r="1.7" stroke="currentColor" stroke-width="1.6"/></svg>',
  bike: '<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><circle cx="5.5" cy="17" r="3" stroke="currentColor" stroke-width="1.6"/><circle cx="18.5" cy="17" r="3" stroke="currentColor" stroke-width="1.6"/><path d="M5.5 17l4-7h4l3.5 7" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/><path d="M9.5 10h-2M13.5 10l2-3h2.5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>',
};

function renderSlots(slots) {
  const map = document.getElementById('slotMap');
  if (!map) return;
  map.innerHTML = '';

  slots.forEach(slot => {
    const cell = document.createElement('div');
    let cls = 'slot-cell';
    if (slot.status === 'available') cls += ' available';
    else if (slot.status === 'disabled') cls += ' disabled-slot';
    else cls += ' taken';

    if (state.selectedSlot === slot.id) cls += ' selected';
    cell.className = cls;

    const icon = ICONS[slot.vehicle_type] || ICONS.car;
    cell.innerHTML = `${icon}${slot.slot_number}`;

    if (slot.status === 'available') {
      cell.addEventListener('click', () => {
        state.selectedSlot = slot.id;
        document.getElementById('slot_id').value = slot.id;
        document.getElementById('summarySlot').textContent = slot.slot_number;
        document.getElementById('bookBtn').disabled = false;
        fetchSlots(); // re-render to show selection
      });
    }
    map.appendChild(cell);
  });
}

function fetchSlots() {
  if (!state.floorId) return;
  fetch(`/api/slots/${state.floorId}?vehicle_type=${state.vehicleType}`)
    .then(r => r.json())
    .then(slots => renderSlots(slots))
    .catch(() => {});
}

function setVehicleType(type) {
  state.vehicleType = type;
  state.selectedSlot = null;
  document.getElementById('slot_id').value = '';
  document.getElementById('bookBtn').disabled = true;
  document.getElementById('summarySlot').textContent = '\u2014';
  document.querySelectorAll('.vehicle-toggle button').forEach(b => {
    b.classList.toggle('active', b.dataset.type === type);
  });
  document.querySelectorAll('input[name="vehicle_type_hidden"]').forEach(i => i.value = type);
  updateEstimate();
  fetchSlots();
}

function setFloor(floorId, btn) {
  state.floorId = floorId;
  state.selectedSlot = null;
  document.getElementById('slot_id').value = '';
  document.getElementById('bookBtn').disabled = true;
  document.getElementById('summarySlot').textContent = '\u2014';
  document.querySelectorAll('.floor-tabs button').forEach(b => b.classList.remove('active'));
  if (btn) btn.classList.add('active');
  document.getElementById('summaryFloor').textContent = btn ? btn.textContent : '';
  fetchSlots();
}

function updateEstimate() {
  const hoursInput = document.getElementById('expected_hours');
  const hours = parseFloat(hoursInput.value) || 1;
  const amount = calcEstimate(hours);
  document.getElementById('summaryAmount').textContent = '\u20b9' + amount;
  document.getElementById('summaryVehicle').textContent = state.vehicleType === 'car' ? 'Car' : 'Bike';
}

document.addEventListener('DOMContentLoaded', () => {
  if (!document.getElementById('slotMap')) return;

  document.querySelectorAll('.vehicle-toggle button').forEach(b => {
    b.addEventListener('click', () => setVehicleType(b.dataset.type));
  });

  document.querySelectorAll('.floor-tabs button').forEach(b => {
    b.addEventListener('click', () => setFloor(parseInt(b.dataset.floorId, 10), b));
  });

  const hoursInput = document.getElementById('expected_hours');
  if (hoursInput) hoursInput.addEventListener('input', updateEstimate);

  updateEstimate();
  fetchSlots();
  // Live refresh every 6s so users see real-time availability
  state.pollTimer = setInterval(fetchSlots, 6000);
});
