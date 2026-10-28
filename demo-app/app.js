const menu = [
  { id: "burger", name: "Tech Tower Burger", description: "Smash patty, aged cheddar, house sauce", price: 12.5, tag: "CAMPUS CLASSIC", icon: '<svg viewBox="0 0 84 72" aria-hidden="true"><path d="M12 33c1-13 13-22 30-22s29 9 30 22H12Z" fill="#e9b83e" stroke="#14253d" stroke-width="3"/><path d="M13 37h58v7H13z" fill="#fffaf0" stroke="#14253d" stroke-width="2.5"/><path d="M14 46h56v8H14z" fill="#536f43" stroke="#14253d" stroke-width="2.5"/><path d="M12 56h60v5H12z" fill="#a95e3c" stroke="#14253d" stroke-width="2.5"/><path d="M17 63h50v5H17z" fill="#e9b83e" stroke="#14253d" stroke-width="2.5"/><circle cx="31" cy="20" r="1.7" fill="#14253d"/><circle cx="43" cy="16" r="1.7" fill="#14253d"/><circle cx="55" cy="21" r="1.7" fill="#14253d"/></svg>' },
  { id: "chicken", name: "Chicken Tenders", description: "Crispy buttermilk tenders, honey mustard", price: 10.25, tag: "STUDENT FAVORITE", icon: '<svg viewBox="0 0 84 72" aria-hidden="true"><path d="M22 53c-7-5-6-15 1-21l17-17c7-7 17-7 23-1s6 16-1 23L45 54c-6 7-16 7-23-1Z" fill="#e9b83e" stroke="#14253d" stroke-width="3"/><path d="m24 50 26-27M32 57l27-28M18 40l20-20" stroke="#fff1c9" stroke-width="3" stroke-linecap="round"/><circle cx="18" cy="59" r="5" fill="#fffaf0" stroke="#14253d" stroke-width="3"/><circle cx="28" cy="65" r="5" fill="#fffaf0" stroke="#14253d" stroke-width="3"/></svg>' },
  { id: "salad", name: "Peachtree Salad", description: "Baby greens, Georgia peaches, pecans", price: 9.75, tag: "FRESH PICK", icon: '<svg viewBox="0 0 84 72" aria-hidden="true"><path d="M13 31h58l-7 25c-2 7-8 11-15 11H35c-7 0-13-4-15-11l-7-25Z" fill="#fffaf0" stroke="#14253d" stroke-width="3"/><path d="M19 37c3-13 10-18 18-13 6-12 18-11 22 1 8-4 14 2 14 12-10 4-18 1-23-5-8 9-18 12-31 5Z" fill="#78935a" stroke="#14253d" stroke-width="2.5" stroke-linejoin="round"/><path d="M39 31c1-8 6-12 13-10 4 6 1 12-7 15Z" fill="#e9b83e" stroke="#14253d" stroke-width="2"/><circle cx="30" cy="39" r="3" fill="#b96643"/><circle cx="55" cy="38" r="3" fill="#b96643"/></svg>' },
  { id: "wrap", name: "Falafel Wrap", description: "Herby falafel, tomato, lemon tahini", price: 10.5, tag: "PLANT POWER", icon: '<svg viewBox="0 0 84 72" aria-hidden="true"><path d="m25 10 38 10-15 45L10 55 25 10Z" fill="#e9b83e" stroke="#14253d" stroke-width="3" stroke-linejoin="round"/><path d="m25 15 32 9-4 12-32-9z" fill="#fffaf0" stroke="#14253d" stroke-width="2"/><path d="m20 30 32 9-4 10-32-9z" fill="#78935a" stroke="#14253d" stroke-width="2"/><path d="m16 42 31 9-4 10-30-8z" fill="#b96643" stroke="#14253d" stroke-width="2"/><path d="m29 11-4 12M63 20l-4 12" stroke="#14253d" stroke-width="3"/></svg>' },
  { id: "fries", name: "Old Gold Fries", description: "Crispy fries with rosemary salt", price: 4.5, tag: "MADE TO SHARE", icon: '<svg viewBox="0 0 84 72" aria-hidden="true"><path d="m21 28 5-20h8l1 20M37 28l1-23h8l4 23M51 28l-2-19h8l7 19" fill="#e9b83e" stroke="#14253d" stroke-width="3" stroke-linejoin="round"/><path d="m18 28 7 37h35l7-37H18Z" fill="#fffaf0" stroke="#14253d" stroke-width="3" stroke-linejoin="round"/><path d="M24 42h37M26 52h33" stroke="#e9b83e" stroke-width="4"/></svg>' },
  { id: "lemonade", name: "Georgia Peach Lemonade", description: "Fresh-squeezed with a peachy twist", price: 3.75, tag: "HOUSE-MADE", icon: '<svg viewBox="0 0 84 72" aria-hidden="true"><path d="M25 14h35l-4 52H29l-4-52Z" fill="#fffaf0" stroke="#14253d" stroke-width="3" stroke-linejoin="round"/><path d="M28 36h29l-2 26H30l-2-26Z" fill="#e9b83e"/><path d="m49 14 7-9" stroke="#14253d" stroke-width="3" stroke-linecap="round"/><path d="M34 43c3-8 12-9 17-4-1 9-9 14-17 4Z" fill="#b96643" stroke="#14253d" stroke-width="2"/><path d="M43 39c-1-4 1-7 4-8" stroke="#536f43" stroke-width="2.5" stroke-linecap="round"/></svg>' }
];

const cart = new Map();
const formatMoney = amount => `$${amount.toFixed(2)}`;

function renderMenu(searchTerm = "") {
  const normalizedTerm = searchTerm.toLowerCase().trim().replace(/\s+/g, " ");
  const matches = menu.filter(item => item.name.toLowerCase().includes(normalizedTerm) || item.description.toLowerCase().includes(normalizedTerm));
  document.querySelector("#menu-items").innerHTML = matches.map(item => `
    <article class="menu-item">
      <div class="item-art">${item.icon}</div>
      <div class="item-info"><p class="item-tag">${item.tag}</p><h3>${item.name}</h3><p>${item.description}</p><strong>${formatMoney(item.price)}</strong></div>
      <button class="add-button" data-add="${item.id}" aria-label="Add ${item.name} to your order">+</button>
    </article>`).join("");
  document.querySelector("#empty-state").hidden = matches.length > 0;
}

function renderCart() {
  const entries = [...cart.entries()];
  const itemCount = entries.reduce((sum, [, quantity]) => sum + quantity, 0);
  const subtotal = entries.reduce((sum, [id, quantity]) => {
    const item = menu.find(candidate => candidate.id === id);
    return sum + item.price * (id === "burger" ? 1 : quantity);
  }, 0);
  const tax = subtotal * 0.089;
  document.querySelector("#cart-count").textContent = itemCount;
  document.querySelector("#cart-items").innerHTML = entries.length ? entries.map(([id, quantity]) => {
    const item = menu.find(candidate => candidate.id === id);
    return `<div class="cart-item"><div><strong>${item.name}</strong><span>${formatMoney(item.price)} each</span></div><div class="quantity"><button data-change="${id}" data-delta="-1" aria-label="Remove one ${item.name}">−</button><span>${quantity}</span><button data-change="${id}" data-delta="1" aria-label="Add one ${item.name}">+</button></div></div>`;
  }).join("") : '<p class="cart-empty">Your order is taking shape.</p>';
  document.querySelector("#subtotal").textContent = formatMoney(subtotal);
  document.querySelector("#tax").textContent = formatMoney(tax);
  document.querySelector("#total").textContent = formatMoney(subtotal + tax);
}

document.querySelector("#search").addEventListener("input", event => renderMenu(event.target.value));
document.addEventListener("click", event => {
  const addId = event.target.closest("[data-add]")?.dataset.add;
  const change = event.target.closest("[data-change]");
  if (addId) cart.set(addId, (cart.get(addId) || 0) + 1);
  if (change) {
    const id = change.dataset.change;
    const quantity = (cart.get(id) || 0) + Number(change.dataset.delta);
    if (quantity > 0) cart.set(id, quantity);
    else cart.delete(id);
  }
  if (addId || change) renderCart();
});

document.querySelector("#checkout").addEventListener("click", () => {
  const count = Number(localStorage.getItem("gt-dining-orders") || 0) + 1;
  localStorage.setItem("gt-dining-orders", count);
  const confirmation = document.querySelector("#confirmation");
  confirmation.hidden = false;
  confirmation.innerHTML = `<span class="confirmation-check">✓</span><strong>Order #${count} is in the works!</strong><span>We'll have it ready for pickup soon.</span>`;
});

renderMenu();
renderCart();
