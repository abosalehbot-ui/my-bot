from fastapi import APIRouter

from .deps import *  # noqa: F401,F403

router = APIRouter()

@router.post("/api/store/admin/return-order")
async def admin_return_order(request: Request, order_id: str = Form(...)):
    if not admin_check(request):
        return JSONResponse({"success": False, "msg": "Unauthorized"}, status_code=401)

    ok, msg = await _process_store_order_return(order_id)
    return JSONResponse({"success": ok, "msg": msg}, status_code=200 if ok else 404)


@router.post("/api/store/admin/return-orders-bulk")
async def admin_return_orders_bulk(request: Request, order_ids: str = Form(...)):
    if not admin_check(request):
        return JSONResponse({"success": False, "msg": "Unauthorized"}, status_code=401)

    ids = _split_bulk_order_ids(order_ids)
    if not ids:
        return JSONResponse({"success": False, "msg": "No order IDs provided."}, status_code=400)

    done, failed = [], []
    for order_id in ids:
        ok, msg = await _process_store_order_return(order_id)
        if ok:
            done.append(order_id)
        else:
            failed.append(f"{order_id} ({msg})")

    return JSONResponse(
        {
            "success": len(done) > 0 and len(failed) == 0,
            "processed": len(done),
            "failed": len(failed),
            "done": done,
            "errors": failed,
            "msg": f"Processed {len(done)} returns, {len(failed)} failed.",
        },
        status_code=200 if len(done) > 0 or not failed else 400,
    )


@router.get("/api/store/admin/customer-orders")
async def admin_customer_orders(request: Request, email: str):
    if not admin_check(request):
        return JSONResponse({"success": False, "msg": "Unauthorized", "orders": []}, status_code=401)

    orders = await db.store_orders.find({"email": email}).sort("date", -1).to_list(200)
    serialized = [_serialize_admin_order(order) for order in orders]
    return JSONResponse({"success": True, "orders": serialized})




@router.post('/api/store/admin/orders/claim')
async def admin_claim_store_order(request: Request, order_id: str = Form(...)):
    staff = await _require_store_staff(request)
    if not staff:
        return JSONResponse({'success': False, 'msg': 'Unauthorized'}, status_code=401)

    role = _normalize_store_role(staff.get('role'))
    order_id = str(order_id or '').strip()
    order = await db.store_orders.find_one({'_id': order_id})
    if not order:
        return JSONResponse({'success': False, 'msg': 'Order not found.'}, status_code=404)
    if str(order.get('delivery_state') or '') in {'completed', 'cancelled'}:
        return JSONResponse({'success': False, 'msg': 'This order is already closed.'}, status_code=409)
    claimed_by = order.get('claimed_by_user_id')
    if claimed_by not in (None, '', 0) and claimed_by != staff.get('user_id') and role != 'admin':
        return JSONResponse({'success': False, 'msg': 'This order is already claimed by another staff member.'}, status_code=409)

    now = _utcnow()
    await db.store_orders.update_one(
        {'_id': order_id},
        {
            '$set': {
                'claimed_by_user_id': staff.get('user_id'),
                'claimed_by_name': staff.get('name', 'Staff'),
                'claimed_at': order.get('claimed_at') or now,
                'updated_at': now,
            }
        },
    )
    updated_order = await db.store_orders.find_one({'_id': order_id}) or order
    thread_id = _order_thread_id(order_id)
    await _ensure_chat_thread(
        'order',
        order_id,
        email=updated_order.get('email', ''),
        customer_name=updated_order.get('name', 'Customer'),
        subject=_order_thread_subject(updated_order),
        assigned_staff_user_id=staff.get('user_id'),
        assigned_staff_name=staff.get('name', 'Staff'),
        status_value='open',
        extra_fields={'delivery_state': updated_order.get('delivery_state')},
    )
    await _update_chat_thread_status(
        thread_id,
        'open',
        assigned_staff_user_id=staff.get('user_id'),
        assigned_staff_name=staff.get('name', 'Staff'),
        extra_fields={'delivery_state': updated_order.get('delivery_state')},
    )
    return JSONResponse({'success': True, 'msg': 'Order claimed.', 'order': _serialize_admin_order(updated_order)})


@router.post('/api/store/admin/orders/status')
async def admin_update_store_order_status(request: Request, order_id: str = Form(...), delivery_state: str = Form(...)):
    staff = await _require_store_staff(request)
    if not staff:
        return JSONResponse({'success': False, 'msg': 'Unauthorized'}, status_code=401)

    role = _normalize_store_role(staff.get('role'))
    new_state = str(delivery_state or '').strip().lower()
    if new_state not in {'processing', 'completed'}:
        return JSONResponse({'success': False, 'msg': 'Invalid order status.'}, status_code=400)

    order_id = str(order_id or '').strip()
    existing = await db.store_orders.find_one({'_id': order_id})
    if not existing:
        return JSONResponse({'success': False, 'msg': 'Order not found.'}, status_code=404)
    claimed_by = existing.get('claimed_by_user_id')
    if claimed_by not in (None, '', 0) and claimed_by != staff.get('user_id') and role != 'admin':
        return JSONResponse({'success': False, 'msg': 'This order is claimed by another staff member.'}, status_code=409)

    try:
        if new_state == 'processing':
            now = _utcnow()
            updated_order = await db.store_orders.find_one_and_update(
                {'_id': order_id},
                {
                    '$set': {
                        'delivery_state': 'processing',
                        'processing_at': now,
                        'updated_at': now,
                        'claimed_by_user_id': staff.get('user_id'),
                        'claimed_by_name': staff.get('name', 'Staff'),
                        'claimed_at': existing.get('claimed_at') or now,
                    }
                },
                return_document=ReturnDocument.AFTER,
            )
        else:
            async def operation(session):
                current_order = await db.store_orders.find_one({'_id': order_id}, session=session)
                if not current_order:
                    raise StoreCheckoutError('Order not found.', status_code=404)
                if str(current_order.get('delivery_state') or '') in {'completed', 'cancelled'}:
                    raise StoreCheckoutError('This order is already closed.', status_code=409)
                current_claimed_by = current_order.get('claimed_by_user_id')
                if current_claimed_by not in (None, '', 0) and current_claimed_by != staff.get('user_id') and role != 'admin':
                    raise StoreCheckoutError('This order is claimed by another staff member.', status_code=409)

                now = _utcnow()
                update_fields = {
                    'delivery_state': 'completed',
                    'updated_at': now,
                    'completed_at': now,
                    'claimed_by_user_id': staff.get('user_id'),
                    'claimed_by_name': staff.get('name', 'Staff'),
                    'claimed_at': current_order.get('claimed_at') or now,
                }
                if not current_order.get('requires_id_fulfillment') and not current_order.get('code'):
                    stock_doc = await db.stock.find_one_and_delete({'category': current_order.get('category')}, session=session)
                    if not stock_doc:
                        raise StoreCheckoutError('No stock code is available to complete this pre-order yet.', status_code=409)
                    code_value = str(stock_doc.get('code') or stock_doc.get('_id'))
                    update_fields['code'] = code_value
                    update_fields['code_masked'] = _mask_code(code_value)
                    await db.codes_map.insert_one(
                        {
                            'code': code_value,
                            'order_id': order_id,
                            'name': f"{staff.get('name', 'Staff')} (Store Staff)",
                            'time': datetime.now().strftime('%Y-%m-%d %H:%M'),
                            'source': 'Store Staff Completion',
                        },
                        session=session,
                    )
                return await db.store_orders.find_one_and_update(
                    {'_id': order_id},
                    {'$set': update_fields},
                    return_document=ReturnDocument.AFTER,
                    session=session,
                )

            updated_order = await _run_transaction(operation)
    except StoreCheckoutError as exc:
        return JSONResponse({'success': False, 'msg': exc.message}, status_code=exc.status_code)

    thread_id = _order_thread_id(order_id)
    thread_status = 'closed' if new_state == 'completed' else 'open'
    await _ensure_chat_thread(
        'order',
        order_id,
        email=updated_order.get('email', ''),
        customer_name=updated_order.get('name', 'Customer'),
        subject=_order_thread_subject(updated_order),
        assigned_staff_user_id=staff.get('user_id'),
        assigned_staff_name=staff.get('name', 'Staff'),
        status_value=thread_status,
        extra_fields={'delivery_state': updated_order.get('delivery_state')},
    )
    await _update_chat_thread_status(
        thread_id,
        thread_status,
        assigned_staff_user_id=staff.get('user_id'),
        assigned_staff_name=staff.get('name', 'Staff'),
        extra_fields={'delivery_state': updated_order.get('delivery_state')},
    )
    if new_state == 'completed':
        if updated_order.get('code'):
            await _append_and_broadcast_system_message(thread_id, f'Order #{order_id} has been completed. Your secure code is now ready to reveal from My Orders.')
        else:
            await _append_and_broadcast_system_message(thread_id, f'Order #{order_id} has been completed successfully.')
    return JSONResponse({'success': True, 'msg': f'Order updated to {new_state}.', 'order': _serialize_admin_order(updated_order)})
