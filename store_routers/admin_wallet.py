from fastapi import APIRouter

from .deps import *  # noqa: F401,F403

router = APIRouter()

@router.get('/api/store/admin/payment-methods')
async def admin_list_payment_methods(request: Request):
    staff = await _require_store_staff(request, {'admin'})
    if not staff:
        return JSONResponse({'success': False, 'msg': 'Unauthorized'}, status_code=401)

    methods = await db.payment_methods.find().sort('name', 1).to_list(200)
    return JSONResponse({'success': True, 'payment_methods': [_serialize_payment_method(method) for method in methods]})


@router.post('/api/store/admin/payment-methods/save')
async def admin_save_payment_method(request: Request):
    staff = await _require_store_staff(request, {'admin'})
    if not staff:
        return JSONResponse({'success': False, 'msg': 'Unauthorized'}, status_code=401)

    form = await request.form()
    method_id = str(form.get('method_id') or '').strip() or uuid.uuid4().hex
    name = str(form.get('name') or '').strip()
    if not name:
        return JSONResponse({'success': False, 'msg': 'Payment method name is required.'}, status_code=400)

    method_type = str(form.get('type') or 'both').strip().lower()
    if method_type not in {'deposit', 'withdrawal', 'both'}:
        method_type = 'both'

    tax_fee = {
        'mode': _payment_fee_mode({'mode': form.get('tax_fee_mode')}),
        'value': _payment_fee_value({'value': form.get('tax_fee_value')}),
    }
    existing = await db.payment_methods.find_one({'_id': method_id})
    doc = _normalize_payment_method(
        {
            '_id': method_id,
            'name': name,
            'image_url': str(form.get('image_url') or '').strip(),
            'type': method_type,
            'is_active': _normalize_channel_flag(form.get('is_active'), True),
            'tax_fee': tax_fee,
            'created_at': (existing or {}).get('created_at') or _utcnow(),
            'updated_at': _utcnow(),
        }
    )
    await db.payment_methods.update_one({'_id': method_id}, {'$set': doc}, upsert=True)
    return JSONResponse({'success': True, 'msg': 'Payment method saved.', 'payment_method': _serialize_payment_method(doc)})


@router.post('/api/store/admin/payment-methods/delete')
async def admin_delete_payment_method(request: Request, method_id: str = Form(...)):
    staff = await _require_store_staff(request, {'admin'})
    if not staff:
        return JSONResponse({'success': False, 'msg': 'Unauthorized'}, status_code=401)

    result = await db.payment_methods.delete_one({'_id': str(method_id or '').strip()})
    if result.deleted_count == 0:
        return JSONResponse({'success': False, 'msg': 'Payment method not found.'}, status_code=404)
    return JSONResponse({'success': True, 'msg': 'Payment method deleted.'})


@router.get('/api/store/admin/wallet-logs')
async def admin_wallet_logs(request: Request):
    staff = await _require_store_staff(request, {'admin'})
    if not staff:
        return JSONResponse({'success': False, 'msg': 'Unauthorized'}, status_code=401)

    txns = await db.wallet_transactions.find().sort([('updated_at', -1), ('created_at', -1)]).to_list(500)
    return JSONResponse({'success': True, 'transactions': [_serialize_wallet_transaction(txn) for txn in txns]})


@router.get('/api/store/admin/wallet-requests')
async def admin_wallet_requests(request: Request):
    staff = await _require_store_staff(request)
    if not staff:
        return JSONResponse({'success': False, 'msg': 'Unauthorized'}, status_code=401)

    txns = await db.wallet_transactions.find().sort([('updated_at', -1), ('created_at', -1)]).to_list(300)
    return JSONResponse({'success': True, 'transactions': [_serialize_wallet_transaction(txn) for txn in txns]})


@router.post('/api/store/admin/wallet-requests/claim')
async def admin_claim_wallet_request(request: Request, transaction_id: str = Form(...)):
    staff = await _require_store_staff(request)
    if not staff:
        return JSONResponse({'success': False, 'msg': 'Unauthorized'}, status_code=401)

    role = _normalize_store_role(staff.get('role'))
    transaction_id = str(transaction_id or '').strip()
    txn = await db.wallet_transactions.find_one({'_id': transaction_id})
    if not txn:
        return JSONResponse({'success': False, 'msg': 'Wallet request not found.'}, status_code=404)
    if str(txn.get('status') or '') != 'pending':
        return JSONResponse({'success': False, 'msg': 'This wallet request is already closed.'}, status_code=409)
    claimed_by = txn.get('claimed_by_user_id')
    if claimed_by not in (None, '', 0) and claimed_by != staff.get('user_id') and role != 'admin':
        return JSONResponse({'success': False, 'msg': 'This wallet request is already claimed by another staff member.'}, status_code=409)

    now = _utcnow()
    await db.wallet_transactions.update_one(
        {'_id': transaction_id},
        {
            '$set': {
                'claimed_by_user_id': staff.get('user_id'),
                'claimed_by_name': staff.get('name', 'Staff'),
                'claimed_at': txn.get('claimed_at') or now,
                'updated_at': now,
            }
        },
    )
    updated_txn = await db.wallet_transactions.find_one({'_id': transaction_id}) or txn
    thread_id = _wallet_thread_id(transaction_id)
    await _ensure_chat_thread(
        'wallet',
        transaction_id,
        email=updated_txn.get('user_email', ''),
        customer_name=updated_txn.get('user_name', 'Customer'),
        subject=_wallet_thread_subject(updated_txn),
        assigned_staff_user_id=staff.get('user_id'),
        assigned_staff_name=staff.get('name', 'Staff'),
        status_value='open',
        extra_fields={'transaction_status': updated_txn.get('status')},
    )
    await _update_chat_thread_status(
        thread_id,
        'open',
        assigned_staff_user_id=staff.get('user_id'),
        assigned_staff_name=staff.get('name', 'Staff'),
        extra_fields={'transaction_status': updated_txn.get('status')},
    )
    return JSONResponse({'success': True, 'msg': 'Wallet request claimed.', 'transaction': _serialize_wallet_transaction(updated_txn)})


@router.post('/api/store/admin/wallet-requests/confirm')
async def admin_confirm_wallet_request(request: Request, transaction_id: str = Form(...), actual_received_amount: float = Form(...)):
    staff = await _require_store_staff(request)
    if not staff:
        return JSONResponse({'success': False, 'msg': 'Unauthorized'}, status_code=401)

    role = _normalize_store_role(staff.get('role'))
    transaction_id = str(transaction_id or '').strip()
    actual_received_amount = round(float(actual_received_amount or 0), 2)
    if actual_received_amount <= 0:
        return JSONResponse({'success': False, 'msg': 'Actual amount received must be greater than zero.'}, status_code=400)

    try:
        async def operation(session):
            txn = await db.wallet_transactions.find_one({'_id': transaction_id}, session=session)
            if not txn:
                raise StoreCheckoutError('Wallet request not found.', status_code=404)
            if str(txn.get('status') or '') != 'pending':
                raise StoreCheckoutError('This wallet request is already closed.', status_code=409)
            claimed_by = txn.get('claimed_by_user_id')
            if claimed_by not in (None, '', 0) and claimed_by != staff.get('user_id') and role != 'admin':
                raise StoreCheckoutError('This wallet request is claimed by another staff member.', status_code=409)

            customer = await db.store_customers.find_one({'email': txn.get('user_email')}, session=session)
            if not customer:
                raise StoreCheckoutError('Customer account not found.', status_code=404)

            currency = str(txn.get('currency') or 'EGP').upper()
            balance_field = _order_currency_balance_field(currency)
            requested_amount = round(float(txn.get('requested_amount') or 0), 2)
            fee_snapshot = txn.get('fee_snapshot') if isinstance(txn.get('fee_snapshot'), dict) else {'mode': 'fixed', 'value': 0}
            fee_basis = actual_received_amount if str(txn.get('type') or '') == 'deposit' else requested_amount
            fee_amount = _compute_wallet_fee(fee_basis, fee_snapshot)
            now = _utcnow()

            if str(txn.get('type') or '') == 'deposit':
                credit_amount = round(actual_received_amount - fee_amount, 2)
                if credit_amount <= 0:
                    raise StoreCheckoutError('The credited amount must remain positive after fees.', status_code=400)
                await db.store_customers.update_one({'email': txn.get('user_email')}, {'$inc': {balance_field: credit_amount}}, session=session)
                await log_wallet_txn(
                    txn.get('user_email', ''),
                    credit_amount,
                    currency,
                    f'Wallet deposit confirmed #{transaction_id}',
                    ref=transaction_id,
                    session=session,
                    extra={'entry_type': 'wallet_deposit', 'agent_id': staff.get('user_id'), 'actual_received_amount': actual_received_amount, 'fee_amount': fee_amount},
                )
            else:
                current_balance = float(customer.get(balance_field, 0) or 0)
                if current_balance < requested_amount:
                    raise StoreCheckoutError(f'Customer no longer has enough {currency} balance to complete this withdrawal.', status_code=409)
                await db.store_customers.update_one({'email': txn.get('user_email')}, {'$inc': {balance_field: -requested_amount}}, session=session)
                await log_wallet_txn(
                    txn.get('user_email', ''),
                    -requested_amount,
                    currency,
                    f'Wallet withdrawal confirmed #{transaction_id}',
                    ref=transaction_id,
                    session=session,
                    extra={'entry_type': 'wallet_withdrawal', 'agent_id': staff.get('user_id'), 'actual_received_amount': actual_received_amount, 'fee_amount': fee_amount},
                )

            return await db.wallet_transactions.find_one_and_update(
                {'_id': transaction_id},
                {
                    '$set': {
                        'status': 'completed',
                        'actual_received_amount': actual_received_amount,
                        'fee_amount': fee_amount,
                        'agent_id': staff.get('user_id'),
                        'agent_name': staff.get('name', 'Staff'),
                        'claimed_by_user_id': staff.get('user_id'),
                        'claimed_by_name': staff.get('name', 'Staff'),
                        'claimed_at': txn.get('claimed_at') or now,
                        'completed_at': now,
                        'updated_at': now,
                    }
                },
                return_document=ReturnDocument.AFTER,
                session=session,
            )

        updated_txn = await _run_transaction(operation)
    except StoreCheckoutError as exc:
        return JSONResponse({'success': False, 'msg': exc.message}, status_code=exc.status_code)

    thread_id = _wallet_thread_id(transaction_id)
    await _update_chat_thread_status(
        thread_id,
        'closed',
        assigned_staff_user_id=staff.get('user_id'),
        assigned_staff_name=staff.get('name', 'Staff'),
        extra_fields={'transaction_status': 'completed'},
    )
    await _append_and_broadcast_system_message(
        thread_id,
        f'{str(updated_txn.get("type") or "wallet").capitalize()} request #{transaction_id} has been confirmed by {staff.get("name", "Staff")}.',
    )
    return JSONResponse({'success': True, 'msg': 'Wallet request confirmed.', 'transaction': _serialize_wallet_transaction(updated_txn)})


@router.post('/api/store/admin/wallet-requests/reject')
