from fastapi import APIRouter

from .deps import *  # noqa: F401,F403

router = APIRouter()

@router.websocket('/ws/store-chat')
async def store_chat_websocket(websocket: WebSocket):
    actor = await _authenticate_store_chat_socket(websocket)
    if not actor:
        await websocket.close(code=4401)
        return

    connection_id = await store_chat_manager.connect(websocket, actor)
    await store_chat_manager.send_to_connection(
        connection_id,
        {
            'event': 'system:connected',
            'role': actor.get('role'),
            'name': actor.get('name'),
        },
    )

    try:
        while True:
            payload = await websocket.receive_json()
            action = str(payload.get('action') or '').strip().lower()
            thread_id = str(payload.get('thread_id') or '').strip()

            if action == 'ping':
                await store_chat_manager.send_to_connection(connection_id, {'event': 'pong'})
                continue

            if action == 'join_room':
                thread = await _get_chat_thread_for_actor(thread_id, actor)
                if not thread:
                    await store_chat_manager.send_to_connection(
                        connection_id,
                        {'event': 'error', 'thread_id': thread_id, 'msg': 'Thread not found.'},
                    )
                    continue

                room = _chat_room_name(thread_id)
                store_chat_manager.join(connection_id, room)
                await store_chat_manager.send_to_connection(
                    connection_id,
                    {
                        'event': 'system:joined',
                        'thread_id': thread_id,
                        'thread': _serialize_chat_thread(thread),
                    },
                )
                await _broadcast_chat_presence(thread_id)
                continue

            if action == 'leave_room':
                if thread_id:
                    store_chat_manager.leave(connection_id, _chat_room_name(thread_id))
                    await _broadcast_chat_presence(thread_id)
                continue

            if action == 'send_message':
                thread = await _get_chat_thread_for_actor(thread_id, actor)
                if not thread:
                    await store_chat_manager.send_to_connection(
                        connection_id,
                        {'event': 'error', 'thread_id': thread_id, 'msg': 'Thread not found.'},
                    )
                    continue
                if actor.get('spectator'):
                    await store_chat_manager.send_to_connection(
                        connection_id,
                        {'event': 'error', 'thread_id': thread_id, 'msg': 'Spectator mode is read-only.'},
                    )
                    continue
                if actor.get('role') == 'customer' and thread.get('status') == 'closed':
                    await store_chat_manager.send_to_connection(
                        connection_id,
                        {'event': 'error', 'thread_id': thread_id, 'msg': 'This ticket is closed.'},
                    )
                    continue

                room = _chat_room_name(thread_id)
                store_chat_manager.join(connection_id, room)
                try:
                    message_doc, updated_thread = await _append_chat_message(
                        thread,
                        actor.get('role', 'customer'),
                        actor.get('name', 'Customer'),
                        payload.get('message', ''),
                        transport='ws',
                    )
                except ValueError as exc:
                    await store_chat_manager.send_to_connection(
                        connection_id,
                        {'event': 'error', 'thread_id': thread_id, 'msg': str(exc)},
                    )
                    continue

                await _broadcast_chat_message(thread_id, updated_thread, message_doc)
                continue

            if action == 'mark_read':
                thread = await _get_chat_thread_for_actor(thread_id, actor)
                if not thread:
                    await store_chat_manager.send_to_connection(
                        connection_id,
                        {'event': 'error', 'thread_id': thread_id, 'msg': 'Thread not found.'},
                    )
                    continue

                if actor.get('spectator'):
                    await store_chat_manager.send_to_connection(
                        connection_id,
                        {'event': 'error', 'thread_id': thread_id, 'msg': 'Spectator mode is read-only.'},
                    )
                    continue

                room = _chat_room_name(thread_id)
                store_chat_manager.join(connection_id, room)
                read_count = await _mark_thread_read(thread_id, actor)
                updated_thread = await _chat_threads_collection().find_one({'_id': thread_id})
                await store_chat_manager.broadcast(
                    room,
                    {
                        'event': 'message:read',
                        'thread_id': thread_id,
                        'reader_role': actor.get('role'),
                        'read_count': read_count,
                        'thread': _serialize_chat_thread(updated_thread or thread),
                    },
                )
                continue

            await store_chat_manager.send_to_connection(
                connection_id,
                {'event': 'error', 'thread_id': thread_id, 'msg': 'Unsupported chat action.'},
            )
    except WebSocketDisconnect:
        pass
    finally:
        affected_rooms = await store_chat_manager.disconnect(connection_id)
        for room in affected_rooms:
            if room.startswith('room:'):
                await _broadcast_chat_presence(room.split(':', 1)[1])


@router.post('/api/store/tickets/create')
async def create_ticket(
    request: Request,
    subject: str = Form(...),
    message: str = Form(...),
):
    email = await _get_authenticated_email(request)
    if not email:
        return JSONResponse({'success': False, 'msg': 'Please login first.'}, status_code=401)

    user = await db.store_customers.find_one({'email': email})
    if not user:
        return JSONResponse({'success': False, 'msg': 'Account not found.'}, status_code=404)

    try:
        clean_subject = _sanitize_chat_text(subject, 'Subject', CHAT_SUBJECT_MAX_LENGTH)
        clean_message = _sanitize_chat_text(message, 'Message', CHAT_MESSAGE_MAX_LENGTH)
    except ValueError as exc:
        return JSONResponse({'success': False, 'msg': str(exc)}, status_code=400)

    ticket_id = await _generate_ticket_id()
    now = _utcnow()
    thread_doc = {
        '_id': ticket_id,
        'email': _normalize_email(email),
        'name': _sanitize_chat_name(user.get('name', 'Customer'), 'Customer'),
        'subject': clean_subject,
        'status': 'open',
        'created_at': _chat_time_label(now),
        'created_at_ts': now,
        'updated_at': now,
        'last_message_at': now,
        'last_message_at_label': _chat_time_label(now),
        'last_message_preview': '',
        'message_count': 0,
        'unread_customer_count': 0,
        'unread_admin_count': 0,
        'messages': [],
    }

    try:
        await _chat_threads_collection().insert_one(thread_doc)
        message_doc, updated_thread = await _append_chat_message(
            thread_doc,
            'customer',
            user.get('name', 'Customer'),
            clean_message,
            transport='rest',
        )
    except Exception:
        await _chat_threads_collection().delete_one({'_id': ticket_id})
        raise

    return JSONResponse(
        {
            'success': True,
            'msg': f'Ticket {ticket_id} submitted!',
            'ticket_id': ticket_id,
            'thread': _serialize_chat_thread(updated_thread),
            'message': _serialize_chat_message(message_doc),
        }
    )


@router.get('/api/store/tickets/my')
async def get_my_tickets(request: Request):
    email = await _get_authenticated_email(request)
    if not email:
        return JSONResponse({'success': False, 'tickets': [], 'force_logout': True}, status_code=401)

    tickets = (
        await _chat_threads_collection()
        .find({'email': _normalize_email(email)})
        .sort([('last_message_at', -1), ('created_at_ts', -1)])
        .to_list(100)
    )
    serialized = [_serialize_chat_thread(ticket) for ticket in tickets]
    return JSONResponse({'success': True, 'tickets': serialized})


@router.get('/api/store/tickets/history')
async def get_ticket_history(
    request: Request,
    ticket_id: str,
    page: int = Query(1, ge=1),
    limit: int = Query(30, ge=1, le=CHAT_HISTORY_LIMIT_MAX),
):
    email = await _get_authenticated_email(request)
    if not email:
        return JSONResponse({'success': False, 'msg': 'Please login first.'}, status_code=401)

    actor = {'role': 'customer', 'email': _normalize_email(email)}
    thread = await _get_chat_thread_for_actor(ticket_id, actor)
    if not thread:
        return JSONResponse({'success': False, 'msg': 'Ticket not found.'}, status_code=404)

    messages, total_messages, has_more = await _load_thread_history(thread, page, limit)
    return JSONResponse(
        {
            'success': True,
            'thread': _serialize_chat_thread(thread),
            'messages': [_serialize_chat_message(message) for message in messages],
            'page': page,
            'limit': limit,
            'has_more': has_more,
            'total_messages': total_messages,
        }
    )


@router.post('/api/store/tickets/reply')
async def customer_reply_ticket(
    request: Request,
    ticket_id: str = Form(...),
    message: str = Form(...),
):
    email = await _get_authenticated_email(request)
    if not email:
        return JSONResponse({'success': False, 'msg': 'Please login first.'}, status_code=401)

    actor = {'role': 'customer', 'email': _normalize_email(email)}
    thread = await _get_chat_thread_for_actor(ticket_id, actor)
    if not thread:
        return JSONResponse({'success': False, 'msg': 'Ticket not found.'}, status_code=404)
    if thread.get('status') == 'closed':
        return JSONResponse({'success': False, 'msg': 'This ticket is closed.'}, status_code=409)

    user = await db.store_customers.find_one({'email': _normalize_email(email)})
    try:
        message_doc, updated_thread = await _append_chat_message(
            thread,
            'customer',
            (user or {}).get('name', 'Customer'),
            message,
            transport='rest',
        )
    except ValueError as exc:
        return JSONResponse({'success': False, 'msg': str(exc)}, status_code=400)

    await _broadcast_chat_message(ticket_id, updated_thread, message_doc)
    return JSONResponse(
        {
            'success': True,
            'msg': 'Reply sent!',
            'thread': _serialize_chat_thread(updated_thread),
            'message': _serialize_chat_message(message_doc),
        }
    )


@router.get('/api/store/admin/tickets/history')
async def admin_ticket_history(
    request: Request,
    ticket_id: str,
    page: int = Query(1, ge=1),
    limit: int = Query(30, ge=1, le=CHAT_HISTORY_LIMIT_MAX),
):
    staff = await _require_store_staff(request)
    if not staff:
        return JSONResponse({'success': False, 'msg': 'Unauthorized'}, status_code=401)

    actor = {
        'role': _normalize_store_role(staff.get('role')),
        'staff_user_id': staff.get('user_id'),
    }
    thread = await _get_chat_thread_for_actor(ticket_id, actor)
    if not thread:
        return JSONResponse({'success': False, 'msg': 'Ticket not found.'}, status_code=404)

    messages, total_messages, has_more = await _load_thread_history(thread, page, limit)
    return JSONResponse(
        {
            'success': True,
            'thread': _serialize_chat_thread(thread),
            'messages': [_serialize_chat_message(message) for message in messages],
            'page': page,
            'limit': limit,
            'has_more': has_more,
            'total_messages': total_messages,
        }
    )

@router.post('/api/store/admin/tickets/reply')
async def admin_reply_ticket(
    request: Request,
    ticket_id: str = Form(...),
    message: str = Form(...),
):
    staff = await _require_store_staff(request)
    if not staff:
        return JSONResponse({'success': False, 'msg': 'Unauthorized'}, status_code=401)

    actor = {
        'role': _normalize_store_role(staff.get('role')),
        'staff_user_id': staff.get('user_id'),
    }
    thread = await _get_chat_thread_for_actor(ticket_id, actor)
    if not thread:
        return JSONResponse({'success': False, 'msg': 'Ticket not found.'}, status_code=404)

    sender_role = actor['role'] if actor['role'] in {'employee', 'admin'} else 'employee'
    try:
        message_doc, updated_thread = await _append_chat_message(
            thread,
            sender_role,
            staff.get('name', 'Support Team'),
            message,
            transport='rest',
        )
    except ValueError as exc:
        return JSONResponse({'success': False, 'msg': str(exc)}, status_code=400)

    await _broadcast_chat_message(ticket_id, updated_thread, message_doc)
    return JSONResponse(
        {
            'success': True,
            'msg': 'Reply sent!',
            'thread': _serialize_chat_thread(updated_thread),
            'message': _serialize_chat_message(message_doc),
        }
    )

@router.post('/api/store/admin/tickets/change-status')
async def admin_change_ticket_status(
    request: Request,
    ticket_id: str = Form(...),
    status: str = Form(...),
):
    staff = await _require_store_staff(request)
    if not staff:
        return JSONResponse({'success': False, 'msg': 'Unauthorized'}, status_code=401)

    if status not in ('open', 'in_progress', 'closed'):
        return JSONResponse({'success': False, 'msg': 'Invalid status.'}, status_code=400)

    result = await _chat_threads_collection().update_one(
        {'_id': ticket_id},
        {
            '$set': {
                'status': status,
                'updated_at': _utcnow(),
                'messages': [],
                'assigned_staff_user_id': staff.get('user_id'),
                'assigned_staff_name': staff.get('name', 'Support Team'),
            }
        },
    )
    if result.matched_count == 0:
        return JSONResponse({'success': False, 'msg': 'Ticket not found.'}, status_code=404)

    updated_thread = await _chat_threads_collection().find_one({'_id': ticket_id})
    await _broadcast_thread_status_change(ticket_id, updated_thread)
    return JSONResponse({'success': True, 'msg': f'Status updated to {status}.', 'thread': _serialize_chat_thread(updated_thread)})

@router.get('/api/store/admin/tickets/view')
async def admin_view_ticket(request: Request, ticket_id: str):
    staff = await _require_store_staff(request)
    if not staff:
        return JSONResponse({'success': False, 'msg': 'Unauthorized'}, status_code=401)

    actor = {
        'role': _normalize_store_role(staff.get('role')),
        'staff_user_id': staff.get('user_id'),
    }
    thread = await _get_chat_thread_for_actor(ticket_id, actor)
    if not thread:
        return JSONResponse({'success': False, 'msg': 'Ticket not found.'}, status_code=404)

    return JSONResponse({'success': True, 'ticket': _serialize_chat_thread(thread)})










# ==========================================
# Storefront + Staff Ops Upgrade Overrides# ==========================================
# Storefront + Staff Ops Upgrade Overrides
# ==========================================



@router.get('/api/store/chat/history')
async def get_store_chat_history(
    request: Request,
    thread_id: str,
    page: int = Query(1, ge=1),
    limit: int = Query(30, ge=1, le=CHAT_HISTORY_LIMIT_MAX),
):
    email = await _get_authenticated_email(request)
    if not email:
        return JSONResponse({'success': False, 'msg': 'Please login first.', 'force_logout': True}, status_code=401)

    actor = {'role': 'customer', 'email': _normalize_email(email)}
    thread = await _get_chat_thread_for_actor(thread_id, actor)
    if not thread:
        return JSONResponse({'success': False, 'msg': 'Thread not found.'}, status_code=404)

    messages, total_messages, has_more = await _load_thread_history(thread, page, limit)
    await _mark_thread_read(thread_id, actor)
    updated_thread = await _chat_threads_collection().find_one({'_id': thread_id}) or thread
    return JSONResponse(
        {
            'success': True,
            'thread': _serialize_chat_thread(updated_thread),
            'messages': [_serialize_chat_message(message) for message in messages],
            'page': page,
            'limit': limit,
            'has_more': has_more,
            'total_messages': total_messages,
        }
    )


@router.post('/api/store/chat/reply')
async def customer_reply_store_chat(
    request: Request,
    thread_id: str = Form(...),
    message: str = Form(...),
):
    email = await _get_authenticated_email(request)
    if not email:
        return JSONResponse({'success': False, 'msg': 'Please login first.', 'force_logout': True}, status_code=401)

    actor = {'role': 'customer', 'email': _normalize_email(email)}
    thread = await _get_chat_thread_for_actor(thread_id, actor)
    if not thread:
        return JSONResponse({'success': False, 'msg': 'Thread not found.'}, status_code=404)
    if thread.get('status') == 'closed':
        return JSONResponse({'success': False, 'msg': 'This chat is closed.'}, status_code=409)

    customer = await db.store_customers.find_one({'email': _normalize_email(email)})
    try:
        message_doc, updated_thread = await _append_chat_message(
            thread,
            'customer',
            (customer or {}).get('name', 'Customer'),
            message,
            transport='rest',
        )
    except ValueError as exc:
        return JSONResponse({'success': False, 'msg': str(exc)}, status_code=400)

    await _broadcast_chat_message(thread_id, updated_thread, message_doc)
    return JSONResponse({'success': True, 'thread': _serialize_chat_thread(updated_thread), 'message': _serialize_chat_message(message_doc)})


@router.get('/api/store/admin/chat/history')
async def admin_store_chat_history(
    request: Request,
    thread_id: str,
    page: int = Query(1, ge=1),
    limit: int = Query(30, ge=1, le=CHAT_HISTORY_LIMIT_MAX),
):
    staff = await _require_store_staff(request)
    if not staff:
        return JSONResponse({'success': False, 'msg': 'Unauthorized'}, status_code=401)

    actor = {
        'role': _normalize_store_role(staff.get('role')),
        'email': staff.get('email', ''),
        'name': staff.get('name', 'Staff'),
        'user_id': staff.get('user_id'),
    }
    thread = await _get_chat_thread_for_actor(thread_id, actor)
    if not thread:
        return JSONResponse({'success': False, 'msg': 'Thread not found.'}, status_code=404)

    messages, total_messages, has_more = await _load_thread_history(thread, page, limit)
    await _mark_thread_read(thread_id, actor)
    updated_thread = await _chat_threads_collection().find_one({'_id': thread_id}) or thread
    return JSONResponse(
        {
            'success': True,
            'thread': _serialize_chat_thread(updated_thread),
            'messages': [_serialize_chat_message(message) for message in messages],
            'page': page,
            'limit': limit,
            'has_more': has_more,
            'total_messages': total_messages,
        }
    )


@router.post('/api/store/admin/chat/reply')
async def admin_reply_store_chat(
    request: Request,
    thread_id: str = Form(...),
    message: str = Form(...),
):
    staff = await _require_store_staff(request)
    if not staff:
        return JSONResponse({'success': False, 'msg': 'Unauthorized'}, status_code=401)

    actor = {
        'role': _normalize_store_role(staff.get('role')),
        'email': staff.get('email', ''),
        'name': staff.get('name', 'Staff'),
        'user_id': staff.get('user_id'),
    }
    thread = await _get_chat_thread_for_actor(thread_id, actor)
    if not thread:
        return JSONResponse({'success': False, 'msg': 'Thread not found.'}, status_code=404)

    try:
        message_doc, updated_thread = await _append_chat_message(
            thread,
            actor['role'],
            actor['name'],
            message,
            transport='rest',
        )
    except ValueError as exc:
        return JSONResponse({'success': False, 'msg': str(exc)}, status_code=400)

    await _broadcast_chat_message(thread_id, updated_thread, message_doc)
    return JSONResponse({'success': True, 'thread': _serialize_chat_thread(updated_thread), 'message': _serialize_chat_message(message_doc)})


