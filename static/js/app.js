/* SplitBill main frontend application logic */
// The Base URL config points to your FastAPI backend
const API_URL = '/api'; 
let token = localStorage.getItem('token');
let isLoginMode = true;
let activeUser = null;
let currentBillId = null;
let currentBillData = null; // Store fetched bill for reference

const ui = {
    authView: document.getElementById('auth-view'),
    dashboardView: document.getElementById('dashboard-view'),
    navUser: document.getElementById('nav-user'),
    navUsername: document.getElementById('nav-username'),
    billsList: document.getElementById('bills-list'),
    billDetails: document.getElementById('bill-details'),
    billEmpty: document.getElementById('bill-empty')
};

function _createToastContainer() {
    let container = document.getElementById('toast-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toast-container';
        container.className = 'fixed top-5 right-5 z-[100] flex flex-col gap-3';
        document.body.appendChild(container);
    }
    return container;
}

function showToast(message, type = 'success') {
    const container = _createToastContainer();
    const toast = document.createElement('div');
    let bgColor = 'bg-green-500'; // for success
    if (type === 'info') bgColor = 'bg-blue-500';
    if (type === 'error') bgColor = 'bg-red-500';

    toast.className = `p-4 rounded-lg shadow-lg text-white text-sm ${bgColor} transition-all duration-300 transform translate-x-full opacity-0 max-w-sm`;
    toast.innerText = message;
    container.appendChild(toast);

    setTimeout(() => { // Animate in
        toast.classList.remove('translate-x-full', 'opacity-0');
    }, 100);

    setTimeout(() => { // Animate out and remove
        toast.classList.add('opacity-0', 'translate-x-full');
        toast.addEventListener('transitionend', () => toast.remove());
    }, 4000);
}

function showError(msg) {
    showToast(msg, 'error');
}

// Centralized fetch wrapper to handle auth and common errors
async function fetchAPI(endpoint, options = {}) {
    const headers = { ...options.headers };
    if (token && !headers['Authorization']) {
        headers['Authorization'] = `Bearer ${token}`;
    }
    const res = await fetch(`${API_URL}${endpoint}`, { ...options, headers });
    
    if (res.status === 401) {
        logout();
        throw new Error('Session expired. Please log in again.');
    }
    if (!res.ok && res.status !== 404) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || `Request failed with status ${res.status}`);
    }
    return res;
}

async function init() {
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get('activated')) {
        showToast('Account activated successfully! You can now log in.', 'success');
        window.history.replaceState({}, document.title, window.location.pathname);
    } else if (urlParams.get('error')) {
        showError(urlParams.get('error'));
        window.history.replaceState({}, document.title, window.location.pathname);
    }

    if (token) {
        try {
            const res = await fetchAPI('/users/me');
            if(res.ok) {
                activeUser = await res.json();
                showDashboard(activeUser);
            }
        } catch(e) {
            logout();
        }
    } else {
        showAuth();
    }
}

function toggleAuthMode() {
    isLoginMode = !isLoginMode;
    document.getElementById('auth-title').innerText = isLoginMode ? 'Login' : 'Create Account';
    
    const usernameInput = document.getElementById('auth-username');
    const usernameField = document.getElementById('username-field') || usernameInput.parentElement;
    usernameField.style.display = isLoginMode ? 'none' : 'block';
    usernameInput.required = !isLoginMode;
    
    const emailInput = document.getElementById('auth-email');
    const emailField = document.getElementById('email-field') || emailInput.parentElement;
    emailField.style.display = 'block';
    emailInput.required = true;
    document.getElementById('auth-toggle').innerText = isLoginMode ? "Don't have an account? Register" : "Already have an account? Login";
}

async function handleAuth(e) {
    e.preventDefault();
    const btn = document.getElementById('auth-btn');
    btn.innerHTML = '<span class="loader"></span>';
    btn.disabled = true;

    const username = document.getElementById('auth-username').value;
    const password = document.getElementById('auth-password').value;
    const email = document.getElementById('auth-email').value;

    try {
        if (isLoginMode) {
            const formData = new URLSearchParams();
            formData.append('username', email);
            formData.append('password', password);
            
            const res = await fetch(`${API_URL}/auth/token`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                body: formData
            });
            if (!res.ok) {
                const d = await res.json().catch(()=>({}));
                throw new Error(d.detail || 'Login failed. Please check your credentials.');
            }
            const data = await res.json();
            token = data.access_token;
            localStorage.setItem('token', token);
            await init();
        } else {
            const res = await fetch(`${API_URL}/users/register`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, password, email })
            });
            if (!res.ok) {
                const d = await res.json().catch(()=>({}));
                throw new Error(d.detail || 'Registration failed');
            }
            showToast('Registration successful! Check your email for an activation link.', 'success');
            toggleAuthMode();
        }
    } catch (err) {
        showError(err.message);
    } finally {
        btn.innerHTML = 'Submit';
        btn.disabled = false;
    }
}

function logout() {
    token = null;
    activeUser = null;
    localStorage.removeItem('token');
    showAuth();
}

function showAuth() {
    ui.authView.classList.remove('hidden');
    ui.dashboardView.classList.add('hidden');
    ui.navUser.classList.add('hidden');
    
    const usernameInput = document.getElementById('auth-username');
    const usernameField = document.getElementById('username-field') || usernameInput.parentElement;
    if (usernameField) usernameField.style.display = isLoginMode ? 'none' : 'block';
    if (usernameInput) usernameInput.required = !isLoginMode;
    
    const emailInput = document.getElementById('auth-email');
    const emailField = document.getElementById('email-field') || emailInput.parentElement;
    if (emailField) emailField.style.display = 'block';
    if (emailInput) emailInput.required = true;
}

function showDashboard(user) {
    ui.authView.classList.add('hidden');
    ui.dashboardView.classList.remove('hidden');
    ui.navUser.classList.remove('hidden');
    ui.navUsername.innerText = `@${user.username}`;
    ui.billDetails.style.display = 'none';
    ui.billEmpty.style.display = 'flex';
    loadBills();
}

async function loadBills() {
    ui.billsList.innerHTML = '<li class="text-center p-4"><span class="loader border-blue-500"></span></li>';
    try {
        const res = await fetchAPI('/splitbills/');
        if (res.status === 404) {
            ui.billsList.innerHTML = '<li class="p-4 text-slate-500 text-sm text-center border-2 border-dashed border-slate-200 rounded-lg">No splitbills found. Create one to get started!</li>';
            return;
        }
        const bills = await res.json();
        
        ui.billsList.innerHTML = '';
        bills.forEach(bill => {
            const li = document.createElement('li');
            li.className = 'p-3 border border-slate-200 rounded-lg bg-white hover:border-blue-300 hover:shadow-sm cursor-pointer transition flex flex-col gap-1';
            li.innerHTML = `
                <div class="flex justify-between items-center">
                    <span class="font-bold text-slate-800">${bill.title}</span>
                    <span class="text-xs font-bold text-slate-500 bg-slate-100 px-2 py-1 rounded">${bill.currency}</span>
                </div>
                <div class="flex justify-between items-center text-xs text-slate-500">
                    <span>${new Date(bill.date_created).toLocaleDateString()}</span>
                    <span class="${bill.status === 'active' ? 'text-green-600' : 'text-slate-400'} capitalize">${bill.status}</span>
                </div>
            `;
            li.onclick = () => loadBillDetails(bill.id);
            ui.billsList.appendChild(li);
        });
    } catch (err) {
        showError(err.message);
        ui.billsList.innerHTML = '';
    }
}

async function loadBillDetails(id) {
    currentBillId = id;
    ui.billEmpty.style.display = 'none';
    ui.billDetails.style.display = 'block';
    document.getElementById('bd-title').innerText = 'Loading...';
    document.getElementById('bd-members').innerHTML = '';
    document.getElementById('bd-balances').innerHTML = '';
    document.getElementById('bd-expenses').innerHTML = '';
    if (document.getElementById('bd-comments')) document.getElementById('bd-comments').innerHTML = '';

    try {
        const res = await fetchAPI(`/splitbills/${id}`);
        const bill = await res.json();
        currentBillData = bill; // cache the active bill data
        
        document.getElementById('bd-title').innerText = bill.title;
        document.getElementById('bd-status').innerText = bill.status.toUpperCase();
        document.getElementById('bd-status').className = bill.status === 'active' 
            ? 'px-2 py-0.5 rounded-full bg-green-100 text-green-800 font-bold text-xs tracking-wide' 
            : 'px-2 py-0.5 rounded-full bg-slate-200 text-slate-700 font-bold text-xs tracking-wide';
        document.getElementById('bd-meta').innerText = `Created ${new Date(bill.date_created).toLocaleDateString()}`;
        
        const isOwner = activeUser && bill.owner_id === activeUser.id;

        // Populate Actions Header
        let actionHTML = '';
        if (isOwner) {
            actionHTML += `<button onclick="handleGetGuestLink()" class="bg-slate-50 text-slate-600 border border-slate-200 px-3 py-1.5 rounded-lg text-sm font-medium hover:bg-slate-100 transition">Copy Guest Link</button>`;
            if (bill.status === 'active') {
                actionHTML += `<button onclick="handleCloseBill()" class="bg-amber-50 text-amber-600 border border-amber-200 px-3 py-1.5 rounded-lg text-sm font-medium hover:bg-amber-100 transition">Settle Bill</button>`;
            }
            actionHTML += `<button onclick="showAddMemberModal()" class="bg-blue-50 text-blue-600 border border-blue-200 px-3 py-1.5 rounded-lg text-sm font-medium hover:bg-blue-100 transition">Add Member</button>`;
            actionHTML += `<button onclick="handleDeleteBill()" class="bg-red-50 text-red-600 border border-red-200 px-3 py-1.5 rounded-lg text-sm font-medium hover:bg-red-100 transition">Delete Bill</button>`;
        }
        document.getElementById('bd-actions').innerHTML = actionHTML;

        // Populate Members
        document.getElementById('bd-members').innerHTML = bill.members.map(m => {
            const name = m.alias || m.email || 'Unknown';
            const initial = name[0].toUpperCase();
            let actionBtns = '';
            if (isOwner && m.user_id !== bill.owner_id) {
                actionBtns = `
                    <div class="ml-auto flex items-center gap-2">
                        <button onclick="showEditMemberModal(${m.id})" class="text-blue-400 hover:text-blue-600" title="Edit Member"><svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z"></path></svg></button>
                        <button onclick="handleRemoveMember(${m.id})" class="text-red-400 hover:text-red-600" title="Remove Member"><svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg></button>
                    </div>
                `;
            }
            return `<li class="flex items-center"><div class="w-6 h-6 rounded-full bg-blue-100 text-blue-700 flex items-center justify-center text-xs font-bold mr-2">${initial}</div> <span>${name}</span> ${actionBtns}</li>`;
        }).join('');
        
        // Populate Balances
        const balancesList = document.getElementById('bd-balances');
        const activeBalances = bill.balances.filter(b => b.status === 'active');
        if(activeBalances.length === 0) {
            balancesList.innerHTML = '<li class="text-slate-400 flex items-center"><svg class="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg> All settled up!</li>';
        } else {
            balancesList.innerHTML = activeBalances.map(b => {
                const from = bill.members.find(m => m.id === b.from_member_id)?.alias || 'Unknown';
                const to = bill.members.find(m => m.id === b.to_member_id)?.alias || 'Unknown';
                return `<li class="flex items-center justify-between border-b border-slate-100 pb-1 last:border-0 last:pb-0">
                    <div><span class="font-semibold text-slate-700">${from}</span> owes <span class="font-semibold text-slate-700">${to}</span></div>
                    <div class="font-bold text-red-500">${b.amount} ${bill.currency}</div>
                </li>`;
            }).join('');
        }

        // Populate Expenses & Payments Chronologically
        const expList = document.getElementById('bd-expenses');
        const allActivity = [
            ...bill.expenses.map(e => ({ ...e, _isPayment: false, _date: new Date(e.date_created) })),
            ...bill.money_given.map(m => ({ ...m, _isPayment: true, _date: new Date(m.date_created) }))
        ].sort((a, b) => b._date - a._date);

        if(allActivity.length === 0) {
            expList.innerHTML = '<li class="p-4 text-center text-slate-400 text-sm">No expenses or payments yet.</li>';
        } else {
            expList.innerHTML = allActivity.map(item => {
                const delBtn = isOwner ? `<button onclick="${item._isPayment ? `handleDeletePayment(${item.id})` : `handleDeleteExpense(${item.id})`}" class="text-slate-400 hover:text-red-500 ml-4 flex-shrink-0" title="Delete"><svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path></svg></button>` : '';
                if (item._isPayment) {
                    const from = bill.members.find(m => m.id === item.given_by)?.alias || bill.members.find(m => m.id === item.given_by)?.email || 'Unknown';
                    const to = bill.members.find(m => m.id === item.given_to)?.alias || bill.members.find(m => m.id === item.given_to)?.email || 'Unknown';
                    return `
                        <li class="p-4 flex justify-between bg-emerald-50/50 hover:bg-emerald-50 transition border-l-4 border-emerald-400">
                            <div class="flex-grow">
                                <div class="font-bold text-slate-800">${item.title || 'Payment'}: ${from} &rarr; ${to}</div>
                                <div class="text-xs font-medium text-slate-500 mt-1">${item._date.toLocaleDateString()}</div>
                            </div>
                            <div class="flex items-center text-right">
                                <div class="font-bold text-lg text-emerald-600">+${item.amount} <span class="text-sm font-normal opacity-75">${bill.currency}</span></div>
                                ${delBtn}
                            </div>
                        </li>
                    `;
                } else {
                    const paidBy = bill.members.find(m => m.id === item.paid_by_id)?.alias || bill.members.find(m => m.id === item.paid_by_id)?.email || 'Unknown';
                    return `
                        <li class="p-4 flex justify-between hover:bg-slate-50 transition">
                            <div class="flex-grow">
                                <div class="font-bold text-slate-800">${item.title}</div>
                                <div class="text-xs font-medium text-slate-500 mt-1"><span class="bg-slate-200 px-1.5 py-0.5 rounded text-slate-600 mr-1 capitalize">${item.type}</span> Paid by ${paidBy} on ${item._date.toLocaleDateString()}</div>
                            </div>
                            <div class="flex items-center text-right">
                                <div class="font-bold text-lg text-slate-800">${item.amount} <span class="text-sm font-normal text-slate-500">${bill.currency}</span></div>
                                ${delBtn}
                            </div>
                        </li>
                    `;
                }
            }).join('');
        }

        // Populate Comments
        const commentsList = document.getElementById('bd-comments');
        if(bill.comments && bill.comments.length > 0) {
            commentsList.innerHTML = bill.comments.map(c => {
                const author = bill.members.find(m => m.id === c.author_id)?.alias || 'Unknown';
                return `<li class="bg-slate-50 p-3 rounded-lg border border-slate-100">
                    <div class="flex justify-between items-center mb-1">
                        <span class="font-semibold text-sm text-slate-700">${author}</span>
                        <span class="text-xs text-slate-400">${new Date(c.date_created).toLocaleString()}</span>
                    </div>
                    <p class="text-sm text-slate-600 mt-1">${c.text}</p>
                </li>`;
            }).join('');
        } else {
            commentsList.innerHTML = '<li class="text-sm text-slate-400 text-center py-4 bg-slate-50 rounded-lg border border-slate-100 border-dashed">No comments yet. Start the discussion!</li>';
        }
        
    } catch (err) {
        showError(err.message);
    }
}

// Modal Triggers
function showCreateModal() { document.getElementById('create-modal').classList.remove('hidden'); }
function hideCreateModal() { document.getElementById('create-modal').classList.add('hidden'); }

async function handleCreateBill(e) {
    e.preventDefault();
    const btn = document.getElementById('cb-btn');
    btn.innerHTML = '<span class="loader"></span>';
    btn.disabled = true;

    const title = document.getElementById('cb-title').value;
    const currency = document.getElementById('cb-currency').value;
    const membersStr = document.getElementById('cb-members').value;
    
    // Convert comma separated string to array of objects
    const members = membersStr.split(',').map(e => e.trim()).filter(e => e).map(input => {
        if (input.includes('@')) {
            return { email: input, alias: input.split('@')[0] };
        }
        return { alias: input, email: null };
    });
    
    try {
        const res = await fetchAPI('/splitbills/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title, currency, members })
        });
        
        hideCreateModal();
        document.getElementById('cb-title').value = '';
        document.getElementById('cb-members').value = '';
        loadBills();
    } catch (err) {
        showError(err.message);
    } finally {
        btn.innerHTML = 'Create';
        btn.disabled = false;
    }
}

// Password Reset Request Modal Triggers
function showResetPasswordRequestModal() {
    document.getElementById('reset-password-request-modal').classList.remove('hidden');
}
function hideResetPasswordRequestModal() {
    document.getElementById('reset-password-request-modal').classList.add('hidden');
}

async function handleResetPasswordRequest(e) {
    e.preventDefault();
    const btn = document.getElementById('rpr-btn');
    btn.innerHTML = '<span class="loader"></span>';
    btn.disabled = true;

    const email = document.getElementById('rpr-email').value;

    try {
        const res = await fetchAPI('/users/reset-password', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email: email })
        });

        if (!res.ok) {
            const d = await res.json().catch(() => ({}));
            throw new Error(d.detail || 'Failed to send password reset email.');
        }

        showToast('Password reset email sent! Check your inbox.', 'success');
        hideResetPasswordRequestModal();
        document.getElementById('rpr-email').value = '';
    } catch (err) {
        showError(err.message);
    } finally {
        btn.innerHTML = 'Send Reset Link';
        btn.disabled = false;
    }
}

// --- Further Actions: Members & Expenses ---

// Add Member Logic
function showAddMemberModal() { document.getElementById('add-member-modal').classList.remove('hidden'); }
function hideAddMemberModal() { document.getElementById('add-member-modal').classList.add('hidden'); }

async function handleAddMember(e) {
    e.preventDefault();
    if (!currentBillId) return;

    const btn = document.getElementById('am-btn');
    btn.innerHTML = '<span class="loader"></span>';
    btn.disabled = true;

    const email = document.getElementById('am-email').value.trim() || null;
    const alias = document.getElementById('am-alias').value.trim() || null;
    
    if (!email && !alias) {
        showError("Please provide an email or an alias.");
        btn.innerHTML = 'Add Member';
        btn.disabled = false;
        return;
    }
    
    try {
        await fetchAPI(`/splitbills/${currentBillId}/add-members`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, alias })
        });
        
        hideAddMemberModal();
        document.getElementById('am-email').value = '';
        document.getElementById('am-alias').value = '';
        loadBillDetails(currentBillId); // Refresh details
    } catch (err) {
        showError(err.message);
    } finally {
        btn.innerHTML = 'Add Member';
        btn.disabled = false;
    }
}

// Add Expense Logic
function showAddExpenseModal() { 
    if (!currentBillData) return;
    document.getElementById('ae-type').value = 'equal';
    const paidBySelect = document.getElementById('ae-paid-by');
    paidBySelect.innerHTML = currentBillData.members.map(m =>
        `<option value="${m.id}" ${m.email === activeUser.email ? 'selected' : ''}>${m.alias || m.email}</option>`
    ).join('');
    renderExpenseAssignments();
    document.getElementById('add-expense-modal').classList.remove('hidden'); 
}
function hideAddExpenseModal() { document.getElementById('add-expense-modal').classList.add('hidden'); }

function renderExpenseAssignments() {
    if (!currentBillData) return;
    const type = document.getElementById('ae-type').value;
    const container = document.getElementById('ae-assignments');
    if (type === 'equal') {
        container.innerHTML = '<p class="text-sm text-slate-500 text-center py-2">Cost will be split equally among all members.</p>';
        return;
    }
    const label = type === 'percentage' ? '%' : currentBillData.currency;
    container.innerHTML = currentBillData.members.map(m => `
        <div class="flex justify-between items-center mb-2">
            <label class="text-sm text-slate-700 font-medium truncate pr-2">${m.alias || m.email || 'Unknown'}</label>
            <div class="flex items-center shrink-0">
                <input type="number" step="0.01" min="0" class="ae-share border border-slate-300 p-1.5 rounded-lg w-24 text-right focus:ring-2 focus:ring-blue-500 focus:outline-none" data-member-id="${m.id}" value="0">
                <span class="ml-2 text-sm text-slate-500 w-6 font-medium">${label}</span>
            </div>
        </div>
    `).join('');
}

async function handleAddExpense(e) {
    e.preventDefault();
    if (!currentBillId || !currentBillData) return;

    const btn = document.getElementById('ae-btn');
    btn.innerHTML = '<span class="loader"></span>';
    btn.disabled = true;

    const title = document.getElementById('ae-title').value;
    const amount = parseFloat(document.getElementById('ae-amount').value);
    const type = document.getElementById('ae-type').value;
    const paid_by_id = parseInt(document.getElementById('ae-paid-by').value);
    
    const assignments = [];
    if (type !== 'equal') {
        const inputs = document.querySelectorAll('.ae-share');
        inputs.forEach(input => {
            const val = parseFloat(input.value);
            if (val > 0) {
                assignments.push({
                    member_id: parseInt(input.dataset.memberId),
                    share_amount: val
                });
            }
        });
    }

    try {
        await fetchAPI(`/splitbills/${currentBillId}/expenses`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                title, 
                amount, 
                type, 
                paid_by_id,
                assignments
            }) 
        });
        
        hideAddExpenseModal();
        document.getElementById('ae-title').value = '';
        document.getElementById('ae-amount').value = '';
        loadBillDetails(currentBillId); // Refresh details
    } catch (err) {
        showError(err.message);
    } finally {
        btn.innerHTML = 'Add Expense';
        btn.disabled = false;
    }
}

// Record Payment Logic
function showRecordPaymentModal() {
    if (!currentBillData) return;
    const options = currentBillData.members.map(m =>
        `<option value="${m.id}">${m.alias || m.email}</option>`
    ).join('');
    
    document.getElementById('rp-given-by').innerHTML = options;
    
    // Attempt to select current user as default giver
    const currentUserMember = currentBillData.members.find(m => m.email === activeUser.email);
    if (currentUserMember) {
        document.getElementById('rp-given-by').value = currentUserMember.id;
    }

    document.getElementById('rp-given-to').innerHTML = options;
    document.getElementById('record-payment-modal').classList.remove('hidden');
}
function hideRecordPaymentModal() { document.getElementById('record-payment-modal').classList.add('hidden'); }

async function handleRecordPayment(e) {
    e.preventDefault();
    if (!currentBillId || !currentBillData) return;

    const btn = document.getElementById('rp-btn');
    btn.innerHTML = '<span class="loader"></span>';
    btn.disabled = true;

    const title = document.getElementById('rp-title').value;
    const amount = parseFloat(document.getElementById('rp-amount').value);
    const given_by = parseInt(document.getElementById('rp-given-by').value);
    const given_to = parseInt(document.getElementById('rp-given-to').value);

    if (given_by === given_to) {
        showError("Sender and receiver cannot be the same person.");
        btn.innerHTML = 'Save Payment';
        btn.disabled = false;
        return;
    }

    try {
        await fetchAPI(`/splitbills/${currentBillId}/money-given`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title, amount, given_by, given_to }) 
        });
        
        hideRecordPaymentModal();
        document.getElementById('rp-title').value = 'Payment';
        document.getElementById('rp-amount').value = '';
        loadBillDetails(currentBillId);
    } catch (err) {
        showError(err.message);
    } finally {
        btn.innerHTML = 'Save Payment';
        btn.disabled = false;
    }
}

// --- Additional Advanced Operations ---
async function handleAddComment(e) {
    e.preventDefault();
    if (!currentBillId) return;
    const textInput = document.getElementById('new-comment');
    const text = textInput.value;
    const btn = document.getElementById('comment-btn');
    btn.disabled = true;
    try {
        await fetchAPI(`/splitbills/${currentBillId}/comments`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text })
        });
        textInput.value = '';
        loadBillDetails(currentBillId);
    } catch (err) {
        showError(err.message);
    } finally {
        btn.disabled = false;
    }
}

async function handleCloseBill() {
    if(!confirm("Are you sure you want to mark this bill as settled? All active balances must be zero.")) return;
    try {
        await fetchAPI(`/splitbills/${currentBillId}/close-splitbill`, { method: 'PATCH' });
        showToast("Bill closed successfully.", 'success');
        loadBills();
        loadBillDetails(currentBillId);
    } catch(err) {
        showError(err.message);
    }
}

async function handleGetGuestLink() {
    try {
        const res = await fetchAPI(`/splitbills/${currentBillId}/guest-link`);
        const data = await res.json();
        navigator.clipboard.writeText(data.link).then(() => {
            showToast("Guest link copied to clipboard!", 'info');
        });
    } catch(err) {
        showError(err.message);
    }
}

async function handleRemoveMember(memberId) {
    if(!confirm("Remove this member from the bill?")) return;
    try {
        await fetchAPI(`/splitbills/${currentBillId}/remove-member`, {
            method: 'DELETE',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id: memberId })
        });
        loadBillDetails(currentBillId);
    } catch(err) {
        showError(err.message);
    }
}

async function handleDeleteExpense(expenseId) {
    if(!confirm("Delete this expense?")) return;
    try {
        await fetchAPI(`/splitbills/${currentBillId}/expenses/${expenseId}`, { method: 'DELETE' });
        loadBillDetails(currentBillId);
    } catch(err) {
        showError(err.message);
    }
}

async function handleDeletePayment(paymentId) {
    if(!confirm("Delete this payment?")) return;
    try {
        await fetchAPI(`/splitbills/${currentBillId}/money-given/${paymentId}`, { method: 'DELETE' });
        loadBillDetails(currentBillId);
    } catch(err) {
        showError(err.message);
    }
}

// --- User Cabinet / Profile ---
function showProfileModal() {
    document.getElementById('profile-username').value = activeUser.username;
    document.getElementById('profile-email').value = activeUser.email;
    document.getElementById('profile-password').value = '';
    document.getElementById('profile-modal').classList.remove('hidden');
}
function hideProfileModal() { document.getElementById('profile-modal').classList.add('hidden'); }

async function handleUpdateProfile(e) {
    e.preventDefault();
    const btn = document.getElementById('profile-btn');
    btn.innerHTML = '<span class="loader"></span>';
    btn.disabled = true;

    const username = document.getElementById('profile-username').value;
    const email = document.getElementById('profile-email').value;
    const password = document.getElementById('profile-password').value;
    
    const payload = {};
    if (username && username !== activeUser.username) payload.username = username;
    if (email && email !== activeUser.email) payload.email = email;
    if (password) payload.password = password;

    try {
        await fetchAPI('/users/me/update', {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        hideProfileModal();
        showToast('Profile updated successfully', 'success');
        init(); // reload user data and view
    } catch (err) {
        showError(err.message);
    } finally {
        btn.innerHTML = 'Save Changes';
        btn.disabled = false;
    }
}

async function handleDeleteAccount() {
    if(!confirm('Are you sure you want to delete your account? This cannot be undone.')) return;
    try {
        await fetchAPI('/users/delete', { method: 'DELETE' });
        hideProfileModal();
        logout();
        showToast('Account deleted', 'success');
    } catch (err) {
        showError(err.message);
    }
}

// --- Edit Member Logic ---
let editMemberModalInjected = false;
function injectEditMemberModal() {
    if (editMemberModalInjected) return;
    const modalHtml = `
    <div id="edit-member-modal" class="hidden fixed inset-0 bg-slate-900/50 backdrop-blur-sm flex items-center justify-center z-50">
        <div class="bg-white rounded-2xl shadow-xl w-full max-w-md overflow-hidden">
            <div class="px-6 py-4 border-b border-slate-100 flex justify-between items-center bg-slate-50">
                <h3 class="font-bold text-slate-800">Edit Member</h3>
                <button type="button" onclick="hideEditMemberModal()" class="text-slate-400 hover:text-slate-600 transition">
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>
                </button>
            </div>
            <form onsubmit="submitEditMember(event)" class="p-6">
                <input type="hidden" id="em-id">
                <div class="mb-4">
                    <label class="block text-sm font-medium text-slate-700 mb-1">Alias / Name</label>
                    <input type="text" id="em-alias" class="w-full border border-slate-300 rounded-lg px-4 py-2 focus:ring-2 focus:ring-blue-500 focus:outline-none transition">
                </div>
                <div class="mb-6">
                    <label class="block text-sm font-medium text-slate-700 mb-1">Email Address (Optional)</label>
                    <input type="email" id="em-email" class="w-full border border-slate-300 rounded-lg px-4 py-2 focus:ring-2 focus:ring-blue-500 focus:outline-none transition" placeholder="Adding an email sends an invite">
                </div>
                <div class="flex justify-end gap-3">
                    <button type="button" onclick="hideEditMemberModal()" class="px-4 py-2 text-slate-600 font-medium hover:bg-slate-100 rounded-lg transition">Cancel</button>
                    <button type="submit" id="em-btn" class="bg-blue-600 text-white px-5 py-2 rounded-lg font-medium hover:bg-blue-700 transition shadow-sm">Save Changes</button>
                </div>
            </form>
        </div>
    </div>
    `;
    document.body.insertAdjacentHTML('beforeend', modalHtml);
    editMemberModalInjected = true;
}

function showEditMemberModal(memberId) {
    injectEditMemberModal();
    const member = currentBillData.members.find(m => m.id === memberId);
    if (!member) return;
    document.getElementById('em-id').value = member.id;
    document.getElementById('em-alias').value = member.alias || '';
    document.getElementById('em-email').value = member.email || '';
    document.getElementById('edit-member-modal').classList.remove('hidden');
}

function hideEditMemberModal() {
    const modal = document.getElementById('edit-member-modal');
    if (modal) modal.classList.add('hidden');
}

async function submitEditMember(e) {
    e.preventDefault();
    const btn = document.getElementById('em-btn');
    btn.innerHTML = '<span class="loader"></span>';
    btn.disabled = true;

    const id = parseInt(document.getElementById('em-id').value);
    const alias = document.getElementById('em-alias').value.trim() || null;
    const email = document.getElementById('em-email').value.trim() || null;

    try {
        await fetchAPI(`/splitbills/${currentBillId}/modify-member`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id, alias, email })
        });
        hideEditMemberModal();
        loadBillDetails(currentBillId);
    } catch (err) {
        showError(err.message);
    } finally {
        btn.innerHTML = 'Save Changes';
        btn.disabled = false;
    }
}

// --- Delete Bill ---
async function handleDeleteBill() {
    if(!currentBillId) return;
    if(!confirm('Are you sure you want to delete this bill? This action is irreversible.')) return;
    try {
        await fetchAPI(`/splitbills/${currentBillId}`, { method: 'DELETE' });
        currentBillId = null;
        currentBillData = null;
        ui.billDetails.style.display = 'none';
        ui.billEmpty.style.display = 'flex';
        loadBills(); // Refresh sidebar list
    } catch (err) {
        showError(err.message);
    }
}

// Boot
init();
