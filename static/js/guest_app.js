const ui = {
    loading: document.getElementById('loading'),
    billDetails: document.getElementById('bill-details'),
    alertBox: document.getElementById('alert-box'),
    alertMessage: document.getElementById('alert-message')
};

function showError(msg) {
    ui.alertMessage.innerText = msg;
    ui.alertBox.classList.remove('hidden');
    ui.loading.classList.add('hidden');
    ui.billDetails.classList.add('hidden');
}

async function initGuestView() {
    // Extract token from URL path, e.g., /guest-access/TOKEN
    const urlObj = new URL(window.location.href);
    const pathParts = urlObj.pathname.split('/').filter(p => p.length > 0);
    const token = pathParts[pathParts.length - 1]?.trim();

    if (!token) {
        showError("Invalid or missing guest link token.");
        return;
    }

    try {
        // Tell the FastAPI backend that we explicitly want JSON data
        const res = await fetch(`/guest-access/${token}?api=true`, {
            headers: { 'Accept': 'application/json' }
        });
        
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            let errorMsg = err.detail || "Failed to load bill details. The link may have expired or is invalid.";
            
            
            if (Array.isArray(err.detail)) {
                errorMsg = err.detail.map(e => `${e.loc.join(' -> ')}: ${e.msg}`).join('\n');
            }
            
            throw new Error(errorMsg);
        }
        
        const bill = await res.json();
        renderBill(bill);
    } catch (err) {
        showError(err.message);
    }
}

function renderBill(bill) {
    ui.loading.classList.add('hidden');
    ui.billDetails.classList.remove('hidden');

    document.getElementById('bd-title').innerText = bill.title;
    document.getElementById('bd-status').innerText = bill.status.toUpperCase();
    document.getElementById('bd-status').className = bill.status === 'active' 
        ? 'px-2 py-0.5 rounded-full bg-green-100 text-green-800 font-bold text-xs tracking-wide' 
        : 'px-2 py-0.5 rounded-full bg-slate-200 text-slate-700 font-bold text-xs tracking-wide';
    document.getElementById('bd-meta').innerText = `Created ${new Date(bill.date_created).toLocaleDateString()}`;

    // Populate Members
    document.getElementById('bd-members').innerHTML = bill.members.map(m => {
        const name = m.alias || m.email || 'Unknown';
        const initial = name[0].toUpperCase();
        return `<li class="flex items-center"><div class="w-6 h-6 rounded-full bg-blue-100 text-blue-700 flex items-center justify-center text-xs font-bold mr-2">${initial}</div> <span>${name}</span></li>`;
    }).join('');

    // Populate Balances
    const balancesList = document.getElementById('bd-balances');
    const activeBalances = bill.balances.filter(b => b.status === 'active');
    if(activeBalances.length === 0) {
        balancesList.innerHTML = '<li class="text-slate-400">All settled up!</li>';
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

    // Populate Expenses & Payments (Chronological)
    const expList = document.getElementById('bd-expenses');
    const allActivity = [
        ...(bill.expenses || []).map(e => ({ ...e, _isPayment: false, _date: new Date(e.date_created) })),
        ...(bill.money_given || []).map(m => ({ ...m, _isPayment: true, _date: new Date(m.date_created) }))
    ].sort((a, b) => b._date - a._date);

    if(allActivity.length === 0) {
        expList.innerHTML = '<li class="p-4 text-center text-slate-400 text-sm">No expenses or payments yet.</li>';
    } else {
        expList.innerHTML = allActivity.map(item => {
            if (item._isPayment) {
                const from = bill.members.find(m => m.id === item.given_by)?.alias || 'Unknown';
                const to = bill.members.find(m => m.id === item.given_to)?.alias || 'Unknown';
                return `<li class="p-4 flex justify-between bg-emerald-50/50 border-l-4 border-emerald-400"><div><div class="font-bold text-slate-800">${item.title || 'Payment'}: ${from} &rarr; ${to}</div><div class="text-xs font-medium text-slate-500 mt-1">${item._date.toLocaleDateString()}</div></div><div class="text-right font-bold text-lg text-emerald-600">+${item.amount} <span class="text-sm font-normal opacity-75">${bill.currency}</span></div></li>`;
            } else {
                const paidBy = bill.members.find(m => m.id === item.paid_by_id)?.alias || 'Unknown';
                return `<li class="p-4 flex justify-between bg-slate-50 hover:bg-slate-100 transition"><div><div class="font-bold text-slate-800">${item.title}</div><div class="text-xs font-medium text-slate-500 mt-1"><span class="bg-slate-200 px-1.5 py-0.5 rounded text-slate-600 mr-1 capitalize">${item.type}</span> Paid by ${paidBy} on ${item._date.toLocaleDateString()}</div></div><div class="text-right font-bold text-lg text-slate-800">${item.amount} <span class="text-sm font-normal text-slate-500">${bill.currency}</span></div></li>`;
            }
        }).join('');
    }

    // Populate Comments
    const commentsList = document.getElementById('bd-comments');
    if(bill.comments && bill.comments.length > 0) {
        commentsList.innerHTML = bill.comments.map(c => {
            const author = bill.members.find(m => m.id === c.author_id)?.alias || 'Unknown';
            return `<li class="bg-slate-50 p-3 rounded-lg border border-slate-100"><div class="flex justify-between items-center mb-1"><span class="font-semibold text-sm text-slate-700">${author}</span><span class="text-xs text-slate-400">${new Date(c.date_created).toLocaleString()}</span></div><p class="text-sm text-slate-600 mt-1">${c.text}</p></li>`;
        }).join('');
    } else {
        commentsList.innerHTML = '<li class="text-sm text-slate-400 text-center py-4 bg-slate-50 rounded-lg border border-slate-100 border-dashed">No comments yet.</li>';
    }
}

initGuestView();