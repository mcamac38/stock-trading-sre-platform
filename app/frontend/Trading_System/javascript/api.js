const API =
  (typeof window !== "undefined" && window.API_BASE_URL) ||
  "https://6hhdszthdg.execute-api.us-east-1.amazonaws.com/prod";


const BASE_URL = API; // change if needed

window.API_BASE_URL = API;
window.BASE_URL = BASE_URL;

function token(){ return localStorage.getItem("token") || ""; }
function setToken(t){ localStorage.setItem("token", t); }
function clearToken(){ localStorage.removeItem("token"); }
export function logout(){ clearToken(); location.href = "./login.html"; }

async function http(path, { method="GET", body, auth=false } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (auth) headers["Authorization"] = `Bearer ${token()}`;
  const res = await fetch(`${BASE_URL}${path}`, {
    method, headers, body: body ? JSON.stringify(body) : undefined
  });
  
  // NEW: bounce to login if token is missing/expired
  if (res.status === 401) {
    clearToken();
    const inPages = location.pathname.includes("/pages/");
    const loginPath = inPages ? "/pages/login.html" : "/login.html";
    location.href = loginPath;
    return; // stop further handling
  }

  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data?.detail || res.statusText);
  return data;
}

// Auth
export async function registerUser({ full_name, username, email, password }) {
  const r = await http("/auth/register", { method:"POST", body:{ full_name, username, email, password }});
  setToken(r.access_token); return r;
}
export async function loginUser({ username, password }) {
  const r = await http("/auth/login", { method:"POST", body:{ username, password }});
  setToken(r.access_token); return r;
}

// Market
export async function listTickers(){ return http("/market/tickers"); }
export async function getPublicMarketHours(){ return http("/market/hours"); }
export async function getMarketStatus(){ return http("/market/status"); }
export async function listTransactions({ type, symbol } = {}) {
	const params = new URLSearchParams();
	
	if (type && type !== "all") {
		params.set("type", type);
    }
	if (symbol) {
		params.set("symbol", symbol.trim());
	}
	
	const qs = params.toString();
	const path = qs ? `/transactions?${qs}` : "/transactions";
	
	return http(path, { auth: true });
}

// ADD: 7-day (or N) history for a ticker
export async function getTickerHistory(ticker, days = 7) {
  const t = (ticker || "").trim().toUpperCase();
  if (!t) return [];
  // GET /market/tickers/<ticker>/history?days=7
  return http(`/market/tickers/${encodeURIComponent(t)}/history?days=${days}`, {
    method: "GET",
    auth: true
  });
}

// Account & Cash
export async function getBalance(){ return http("/account", { auth:true }); }
export async function deposit(amount){ return http("/cash/deposit", { method:"POST", auth:true, body:{ amount: Number(amount) }}); }
export async function withdraw(amount){ return http("/cash/withdraw", { method:"POST", auth:true, body:{ amount: Number(amount) }}); }

// Trades & Portfolio
export async function placeOrder({ ticker, side, quantity }){
  return http("/trade/buy", { method:"POST", auth:true, body:{ ticker, side, quantity: Number(quantity) }});
}
export async function sellOrder({ticker, side, quantity }){
  return http("/trade/sell", {method:"POST", auth: true, body:{ticker, side, quantity: Number(quantity) }});
}
export async function getPortfolio(){ return http("/portfolio", { auth:true }); }
export async function getPortfolioHistory(days = 7) {
  const query = days ? `?days=${encodeURIComponent(days)}` : "";
  return http(`/portfolio/history${query}`, { auth: true });
}
export async function getTransactions(){ return http("/transactions", { auth:true }); }

// Guards/helpers
export function requireAuth(){
  if (!token()) {
    const inPages = location.pathname.includes("/pages/");
    const loginPath = inPages ? "/pages/login.html" : "/login.html";
    location.href = loginPath;
  }
}

export async function renderCash(spanId="cash-amount"){
  try {
    const { cash_balance } = await getBalance();
    const el = document.getElementById(spanId);
    if (el) el.textContent = Number(cash_balance).toLocaleString(undefined,{minimumFractionDigits:2, maximumFractionDigits:2});
  } catch {}
}

//Administrator Stock Creator
// In/assets/api.js - add this export note: If your backend route differs, change "/admin/stocks" accordingly
export async function adminCreateStock(payload) {
		//expects: { ticker, company_name, current_price, volume?, sector?, is_listed? }
		return http("/admin/stocks", {method: "POST", auth: true, body: payload });
}

// Admin: Market Hours & Schedule
export async function getMarketHours(){ 
    return http("/admin/market-hours", {auth:true}); 
}
export async function updateMarketHours({open_time, close_time, tz_name}){ 
    return http("/admin/market-hours", { method:"PUT", auth:true, body:{open_time, close_time, tz_name } }); 
}
export async function getMarketSchedule(){
    return http("/admin/market-schedule", { auth:true}); 
}	
export async function saveMarketScheduleEntry({close_date, is_closed, open_time, close_time, note }){
	return http("/admin/market-schedule", {
		method: "PUT",
		auth: true,
		body: {close_date, is_closed, open_time, close_time, note }
	});
}

export { token, setToken, clearToken };