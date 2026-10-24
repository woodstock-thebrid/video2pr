const menu = [
  { id: "burger", name: "Tech Tower Burger", description: "Smash patty, aged cheddar, house sauce", price: 12.5, emoji: "🍔", tag: "CAMPUS CLASSIC" },
  { id: "chicken", name: "Chicken Tenders", description: "Crispy buttermilk tenders, honey mustard", price: 10.25, emoji: "🍗", tag: "STUDENT FAVORITE" },
  { id: "salad", name: "Peachtree Salad", description: "Baby greens, Georgia peaches, pecans", price: 9.75, emoji: "🥗", tag: "FRESH PICK" },
  { id: "wrap", name: "Falafel Wrap", description: "Herby falafel, tomato, lemon tahini", price: 10.5, emoji: "🌯", tag: "PLANT POWER" },
  { id: "fries", name: "Old Gold Fries", description: "Crispy fries with rosemary salt", price: 4.5, emoji: "🍟", tag: "MADE TO SHARE" },
  { id: "lemonade", name: "Georgia Peach Lemonade", description: "Fresh-squeezed with a peachy twist", price: 3.75, emoji: "🍋", tag: "HOUSE-MADE" }
];

const cart = new Map();
const formatMoney = amount => `$${amount.toFixed(2)}`;

function renderMenu(searchTerm = "") {
  const normalizedTerm = searchTerm.toLowerCase().replace(/\s/g, "");
  const matches = menu.filter(item => item.name.toLowerCase().includes(normalizedTerm) || item.description.toLowerCase().includes(normalizedTerm));
  document.querySelector("#menu-items").innerHTML = matches.map(item => `
    <article class="menu-item">
      <div class="item-art">${item.emoji}</div>
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
