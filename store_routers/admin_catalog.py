from fastapi import APIRouter

from .deps import *  # noqa: F401,F403

router = APIRouter()

@router.get("/api/store/admin/catalog")
async def admin_catalog(request: Request):
    staff = await _require_store_staff(request)
    if not staff:
        return JSONResponse({"success": False, "msg": "Unauthorized", "categories": []}, status_code=401)

    categories = await _build_admin_catalog_payload()
    return JSONResponse({"success": True, "categories": categories})


@router.post("/api/store/admin/catalog/product-channel")
async def admin_update_product_channel(
    request: Request,
    cat_id: str = Form(...),
    stock_key: str = Form(...),
    is_visible_web: Optional[str] = Form(default=None),
    is_visible_bot: Optional[str] = Form(default=None),
    allocation_web: Optional[str] = Form(default=''),
    allocation_bot: Optional[str] = Form(default=''),
    description: Optional[str] = Form(default=''),
    estimated_completion_time: Optional[str] = Form(default=''),
    is_active: Optional[str] = Form(default=None),
    requires_id_fulfillment: Optional[str] = Form(default=None),
):
    staff = await _require_store_staff(request)
    if not staff:
        return JSONResponse({"success": False, "msg": "Unauthorized"}, status_code=401)

    cat_id = str(cat_id or '').strip()
    stock_key = str(stock_key or '').strip()
    if not cat_id or not stock_key:
        return JSONResponse({"success": False, "msg": "Category and stock key are required."}, status_code=400)

    web_ok, allocation_web_value = _parse_allocation_form_value(allocation_web)
    bot_ok, allocation_bot_value = _parse_allocation_form_value(allocation_bot)
    if not web_ok or not bot_ok:
        return JSONResponse({"success": False, "msg": "Allocations must be whole numbers or left blank for unlimited."}, status_code=400)

    category = await db.store_categories.find_one({'products.stock_key': stock_key}, {'_id': 1})
    if not category:
        return JSONResponse({"success": False, "msg": "Product not found."}, status_code=404)
    if cat_id and str(category.get('_id') or '') != cat_id:
        return JSONResponse({"success": False, "msg": "Product category mismatch."}, status_code=404)

    update_ops = {
        '$set': {
            'products.$.is_visible_web': _normalize_channel_flag(is_visible_web if is_visible_web is not None else 'false', True),
            'products.$.is_visible_bot': _normalize_channel_flag(is_visible_bot if is_visible_bot is not None else 'false', True),
        }
    }
    unset_ops = {}
    if allocation_web_value is None:
        unset_ops['products.$.allocation_web'] = ''
    else:
        update_ops['$set']['products.$.allocation_web'] = allocation_web_value

    if allocation_bot_value is None:
        unset_ops['products.$.allocation_bot'] = ''
    else:
        update_ops['$set']['products.$.allocation_bot'] = allocation_bot_value

    if unset_ops:
        update_ops['$unset'] = unset_ops

    result = await db.store_categories.update_one(
        {'_id': category.get('_id'), 'products.stock_key': stock_key},
        update_ops,
    )
    if result.matched_count == 0:
        return JSONResponse({"success": False, "msg": "Product not found."}, status_code=404)

    product_snapshot = await _build_inventory_product_snapshot(stock_key)
    return JSONResponse(
        {
            "success": True,
            "msg": "Product channel settings updated.",
            "product": product_snapshot,
        }
    )



@router.post('/api/store/admin/catalog/category-meta')
async def admin_update_category_meta(
    request: Request,
    cat_id: str = Form(...),
    description: str = Form(''),
    estimated_completion_time: str = Form(''),
    is_active: str = Form('true'),
):
    staff = await _require_store_staff(request)
    if not staff:
        return JSONResponse({'success': False, 'msg': 'Unauthorized'}, status_code=401)

    result = await db.store_categories.update_one(
        {'_id': str(cat_id or '').strip()},
        {
            '$set': {
                'description': _normalize_catalog_description(description),
                'estimated_completion_time': _normalize_catalog_eta(estimated_completion_time),
                'is_active': _normalize_catalog_active(is_active, True),
            }
        },
    )
    if result.matched_count == 0:
        return JSONResponse({'success': False, 'msg': 'Category not found.'}, status_code=404)

    categories = await _build_admin_catalog_payload()
    category = next((item for item in categories if item.get('id') == str(cat_id or '').strip()), None)
    return JSONResponse({'success': True, 'msg': 'Category details updated.', 'category': category})


@router.post('/api/store/admin/catalog/product-meta')
async def admin_update_product_meta(
    request: Request,
    cat_id: str = Form(...),
    stock_key: str = Form(...),
    description: Optional[str] = Form(default=''),
    estimated_completion_time: Optional[str] = Form(default=''),
    is_active: Optional[str] = Form(default=None),
    requires_id_fulfillment: Optional[str] = Form(default=None),
    is_visible_web: Optional[str] = Form(default=None),
    is_visible_bot: Optional[str] = Form(default=None),
    allocation_web: Optional[str] = Form(default=''),
    allocation_bot: Optional[str] = Form(default=''),
):
    staff = await _require_store_staff(request)
    if not staff:
        return JSONResponse({'success': False, 'msg': 'Unauthorized'}, status_code=401)

    stock_key = str(stock_key or '').strip()
    category = await db.store_categories.find_one({'products.stock_key': stock_key}, {'_id': 1})
    if not category:
        return JSONResponse({'success': False, 'msg': 'Product not found.'}, status_code=404)
    if str(cat_id or '').strip() and str(category.get('_id') or '') != str(cat_id or '').strip():
        return JSONResponse({'success': False, 'msg': 'Product category mismatch.'}, status_code=404)

    result = await db.store_categories.update_one(
        {'_id': category.get('_id'), 'products.stock_key': stock_key},
        {
            '$set': {
                'products.$.description': _normalize_catalog_description(description),
                'products.$.estimated_completion_time': _normalize_catalog_eta(estimated_completion_time),
                'products.$.is_active': _normalize_catalog_active(is_active if is_active is not None else 'false', True),
                'products.$.requires_id_fulfillment': _normalize_channel_flag(requires_id_fulfillment if requires_id_fulfillment is not None else 'false', False),
            }
        },
    )
    if result.matched_count == 0:
        return JSONResponse({'success': False, 'msg': 'Product not found.'}, status_code=404)

    product_snapshot = await _build_inventory_product_snapshot(stock_key)
    return JSONResponse({'success': True, 'msg': 'Product details updated.', 'product': product_snapshot})

