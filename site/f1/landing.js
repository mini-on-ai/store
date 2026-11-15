const F1_API = 'https://f1-api.kirozdormu.workers.dev';
let selectedTier = 'pro';

// ── Fetch live stats ──────────────────────────────────────────────────────────
async function loadLiveStats() {
  try {
    const res = await fetch(`${F1_API}/api/public-stats`);
    if (!res.ok) return;
    const data = await res.json();
    const m = data.last_30_days || {};
    const a = data.all_time || {};
    document.getElementById('live-usd-30d').textContent = '$' + (m.usd || 0).toFixed(4);
    document.getElementById('live-calls-30d').textContent = (m.calls || 0).toLocaleString();
    document.getElementById('live-tokens-30d').textContent = formatTokens(m.tokens || 0);
    document.getElementById('live-calls-all').textContent = (a.calls || 0).toLocaleString();
  } catch (_) {}
}
loadLiveStats();

function formatTokens(n) {
  if (n >= 1e9) return (n/1e9).toFixed(1) + 'B';
  if (n >= 1e6) return (n/1e6).toFixed(1) + 'M';
  if (n >= 1e3) return (n/1e3).toFixed(1) + 'K';
  return String(n);
}

// ── Checkout modal ────────────────────────────────────────────────────────────
function startCheckout(tier) {
  selectedTier = tier;
  document.getElementById('modal-tier-label').textContent = tier === 'scale' ? 'Get Scale — $99/mo' : 'Get Pro — $19/mo';
  document.getElementById('checkout-error').style.display = 'none';
  document.getElementById('checkout-modal').style.display = 'flex';
}

function closeModal() {
  document.getElementById('checkout-modal').style.display = 'none';
}

async function submitCheckout() {
  const email = document.getElementById('checkout-email').value.trim();
  const errEl = document.getElementById('checkout-error');
  errEl.style.display = 'none';
  if (!email || !email.includes('@')) {
    errEl.textContent = 'Please enter a valid email address.';
    errEl.style.display = 'block';
    return;
  }
  const btn = document.getElementById('checkout-submit');
  btn.textContent = 'Redirecting…';
  btn.disabled = true;
  try {
    const res = await fetch(`${F1_API}/api/checkout`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, tier: selectedTier }),
    });
    const data = await res.json();
    if (data.checkout_url) {
      window.location.href = data.checkout_url;
    } else {
      errEl.textContent = data.error || 'Payment setup failed. Please try again.';
      errEl.style.display = 'block';
      btn.textContent = 'Continue to payment →';
      btn.disabled = false;
    }
  } catch (e) {
    errEl.textContent = 'Network error. Please try again.';
    errEl.style.display = 'block';
    btn.textContent = 'Continue to payment →';
    btn.disabled = false;
  }
}

// Welcome message after Stripe redirect
if (new URLSearchParams(location.search).get('f1') === 'welcome') {
  document.querySelector('.f1-deadline-banner').innerHTML = '🎉 <strong>You\'re in!</strong> Check your email for your F1 API key + dashboard URL. If it doesn\'t arrive within 2 minutes, email <a href="mailto:hello@mini-on-ai.com" style="color:#f87171;">hello@mini-on-ai.com</a>';
}

// ── Event wiring ──────────────────────────────────────────────────────────────
// Listeners instead of inline on* attributes, so the CSP can forbid inline script.
document.querySelectorAll('[data-checkout]').forEach(btn => {
  btn.addEventListener('click', () => startCheckout(btn.dataset.checkout));
});
document.getElementById('checkout-close').addEventListener('click', closeModal);
document.getElementById('checkout-submit').addEventListener('click', submitCheckout);
