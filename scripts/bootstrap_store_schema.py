from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.errors import CollectionInvalid

from config import MONGO_URI


DB_NAME = 'salehzon_db'


STORE_CUSTOMERS_VALIDATOR = {
    '$jsonSchema': {
        'bsonType': 'object',
        'required': ['user_id', 'email', 'name'],
        'properties': {
            'user_id': {'bsonType': 'int'},
            'email': {'bsonType': 'string', 'description': 'Normalized customer email'},
            'name': {'bsonType': 'string'},
            'username': {'bsonType': 'string'},
            'password': {'bsonType': 'string'},
            'google_sub': {'bsonType': 'string'},
            'telegram_id': {'bsonType': 'string'},
            'balance_egp': {'bsonType': ['int', 'long', 'double', 'decimal']},
            'balance_usd': {'bsonType': ['int', 'long', 'double', 'decimal']},
            'is_banned': {'bsonType': 'bool'},
            'balance_frozen': {'bsonType': 'bool'},
            'avatar': {'bsonType': 'string'},
            'created_at': {'bsonType': 'string'},
        },
        'additionalProperties': True,
    }
}

STORE_SESSIONS_VALIDATOR = {
    '$jsonSchema': {
        'bsonType': 'object',
        'required': ['_id', 'user_id', 'email', 'created_at', 'expires_at'],
        'properties': {
            '_id': {'bsonType': 'string', 'description': 'SHA-256 digest of the raw session token'},
            'user_id': {'bsonType': 'int'},
            'email': {'bsonType': 'string'},
            'created_at': {'bsonType': 'date'},
            'updated_at': {'bsonType': 'date'},
            'last_seen_at': {'bsonType': 'date'},
            'expires_at': {'bsonType': 'date'},
            'ip_address': {'bsonType': 'string'},
            'user_agent': {'bsonType': 'string'},
        },
        'additionalProperties': False,
    }
}

STORE_OTP_CHALLENGES_VALIDATOR = {
    '$jsonSchema': {
        'bsonType': 'object',
        'required': ['_id', 'email', 'purpose', 'code_hash', 'created_at', 'expires_at'],
        'properties': {
            '_id': {'bsonType': 'string'},
            'email': {'bsonType': 'string'},
            'purpose': {'bsonType': 'string'},
            'code_hash': {'bsonType': 'string'},
            'payload': {'bsonType': 'object'},
            'attempts': {'bsonType': 'int'},
            'max_attempts': {'bsonType': 'int'},
            'created_at': {'bsonType': 'date'},
            'updated_at': {'bsonType': 'date'},
            'last_attempt_at': {'bsonType': 'date'},
            'expires_at': {'bsonType': 'date'},
        },
        'additionalProperties': False,
    }
}

STORE_ORDERS_VALIDATOR = {
    '$jsonSchema': {
        'bsonType': 'object',
        'required': ['_id', 'email', 'name', 'category', 'price', 'currency', 'date'],
        'properties': {
            '_id': {'bsonType': 'string'},
            'email': {'bsonType': 'string'},
            'name': {'bsonType': 'string'},
            'category': {'bsonType': 'string'},
            'code': {'bsonType': 'string'},
            'price': {'bsonType': ['int', 'long', 'double', 'decimal']},
            'currency': {'bsonType': 'string'},
            'date': {'bsonType': 'string'},
            'delivery_state': {'bsonType': 'string'},
            'created_at': {'bsonType': 'date'},
        },
        'additionalProperties': True,
    }
}

STORE_CATEGORIES_VALIDATOR = {
    '$jsonSchema': {
        'bsonType': 'object',
        'required': ['_id', 'name'],
        'properties': {
            '_id': {'bsonType': 'string'},
            'name': {'bsonType': 'string'},
            'icon': {'bsonType': 'string'},
            'image': {'bsonType': 'string'},
            'logo': {'bsonType': 'string'},
            'products': {
                'bsonType': 'array',
                'items': {
                    'bsonType': 'object',
                    'properties': {
                        'stock_key': {'bsonType': 'string'},
                        'name': {'bsonType': 'string'},
                        'image': {'bsonType': 'string'},
                        'prices': {'bsonType': 'object'},
                        'price_egp': {'bsonType': ['int', 'long', 'double', 'decimal']},
                        'price_usd': {'bsonType': ['int', 'long', 'double', 'decimal']},
                        'is_visible_web': {'bsonType': 'bool'},
                        'is_visible_bot': {'bsonType': 'bool'},
                        'allocation_web': {'bsonType': ['int', 'long', 'null']},
                        'allocation_bot': {'bsonType': ['int', 'long', 'null']},
                    },
                    'additionalProperties': True,
                },
            },
        },
        'additionalProperties': True,
    }
}

SUPPORT_TICKETS_VALIDATOR = {
    '$jsonSchema': {
        'bsonType': 'object',
        'required': ['_id', 'email', 'subject', 'status', 'created_at'],
        'properties': {
            '_id': {'bsonType': 'string'},
            'email': {'bsonType': 'string'},
            'name': {'bsonType': 'string'},
            'subject': {'bsonType': 'string'},
            'status': {'enum': ['open', 'in_progress', 'closed']},
            'created_at': {'bsonType': 'string'},
            'created_at_ts': {'bsonType': ['date', 'null']},
            'updated_at': {'bsonType': ['date', 'null']},
            'last_message_at': {'bsonType': ['date', 'null']},
            'last_message_at_label': {'bsonType': 'string'},
            'last_message_preview': {'bsonType': 'string'},
            'last_sender': {'bsonType': 'string'},
            'message_count': {'bsonType': 'int'},
            'unread_customer_count': {'bsonType': 'int'},
            'unread_admin_count': {'bsonType': 'int'},
            'messages': {'bsonType': 'array'},
        },
        'additionalProperties': True,
    }
}

SUPPORT_TICKET_MESSAGES_VALIDATOR = {
    '$jsonSchema': {
        'bsonType': 'object',
        'required': ['_id', 'thread_id', 'sender', 'name', 'message', 'created_at'],
        'properties': {
            '_id': {'bsonType': 'string'},
            'thread_id': {'bsonType': 'string'},
            'email': {'bsonType': 'string'},
            'sender': {'enum': ['customer', 'admin']},
            'name': {'bsonType': 'string'},
            'message': {'bsonType': 'string'},
            'created_at': {'bsonType': 'date'},
            'created_at_label': {'bsonType': 'string'},
            'read_by_customer_at': {'bsonType': ['date', 'null']},
            'read_by_admin_at': {'bsonType': ['date', 'null']},
            'transport': {'bsonType': 'string'},
        },
        'additionalProperties': True,
    }
}


def ensure_collection(db, name: str, validator: dict | None = None) -> None:
    try:
        if validator:
            db.create_collection(name, validator=validator, validationLevel='moderate')
        else:
            db.create_collection(name)
    except CollectionInvalid:
        if validator:
            db.command(
                'collMod',
                name,
                validator=validator,
                validationLevel='moderate',
            )


def bootstrap() -> None:
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]

    ensure_collection(db, 'store_customers', STORE_CUSTOMERS_VALIDATOR)
    ensure_collection(db, 'store_sessions', STORE_SESSIONS_VALIDATOR)
    ensure_collection(db, 'store_otp_challenges', STORE_OTP_CHALLENGES_VALIDATOR)
    ensure_collection(db, 'store_orders', STORE_ORDERS_VALIDATOR)
    ensure_collection(db, 'store_categories', STORE_CATEGORIES_VALIDATOR)
    ensure_collection(db, 'store_wallet_ledger')
    ensure_collection(db, 'store_txn_locks')
    ensure_collection(db, 'support_tickets', SUPPORT_TICKETS_VALIDATOR)
    ensure_collection(db, 'support_ticket_messages', SUPPORT_TICKET_MESSAGES_VALIDATOR)

    db.store_customers.create_index([('email', ASCENDING)], unique=True, name='uniq_store_customer_email')
    db.store_customers.create_index([('username', ASCENDING)], unique=True, sparse=True, name='uniq_store_customer_username')
    db.store_customers.create_index([('user_id', ASCENDING)], unique=True, sparse=True, name='uniq_store_customer_user_id')
    db.store_customers.create_index([('google_sub', ASCENDING)], unique=True, sparse=True, name='uniq_store_customer_google_sub')
    db.store_customers.create_index([('telegram_id', ASCENDING)], unique=True, sparse=True, name='uniq_store_customer_telegram_id')
    db.store_customers.create_index([('created_at', DESCENDING)], name='idx_store_customer_created_at')

    db.store_sessions.create_index([('user_id', ASCENDING), ('expires_at', DESCENDING)], name='idx_store_session_user_expiry')
    db.store_sessions.create_index([('email', ASCENDING), ('expires_at', DESCENDING)], name='idx_store_session_email_expiry')
    db.store_sessions.create_index('expires_at', expireAfterSeconds=0, name='ttl_store_session_expiry')

    db.store_otp_challenges.create_index([('email', ASCENDING), ('purpose', ASCENDING)], unique=True, name='uniq_store_otp_email_purpose')
    db.store_otp_challenges.create_index('expires_at', expireAfterSeconds=0, name='ttl_store_otp_expiry')

    db.store_orders.create_index([('email', ASCENDING), ('date', DESCENDING)], name='idx_store_orders_email_date')
    db.store_orders.create_index([('currency', ASCENDING), ('date', DESCENDING)], name='idx_store_orders_currency_date')
    db.store_orders.create_index([('category', ASCENDING), ('date', DESCENDING)], name='idx_store_orders_category_date')
    db.store_categories.create_index([('products.stock_key', ASCENDING)], name='idx_store_categories_product_stock_key')

    db.store_wallet_ledger.create_index([('email', ASCENDING), ('ts', DESCENDING)], name='idx_store_wallet_email_ts')
    db.store_wallet_ledger.create_index([('ref', ASCENDING)], sparse=True, name='idx_store_wallet_ref')

    db.store_txn_locks.create_index([('email', ASCENDING), ('created_at', DESCENDING)], name='idx_store_txn_email_created')
    db.store_txn_locks.create_index([('status', ASCENDING), ('finished_at', DESCENDING)], sparse=True, name='idx_store_txn_status_finished')
    db.store_txn_locks.create_index('expires_at', expireAfterSeconds=0, name='ttl_store_txn_expiry')

    db.support_tickets.create_index([('email', ASCENDING), ('created_at', DESCENDING)], name='idx_support_ticket_email_created')
    db.support_tickets.create_index([('status', ASCENDING), ('created_at', DESCENDING)], name='idx_support_ticket_status_created')
    db.support_tickets.create_index([('last_message_at', DESCENDING)], name='idx_support_ticket_last_message_at')

    db.support_ticket_messages.create_index([('thread_id', ASCENDING), ('created_at', DESCENDING)], name='idx_support_ticket_messages_thread_created')
    db.support_ticket_messages.create_index([('thread_id', ASCENDING), ('sender', ASCENDING), ('created_at', DESCENDING)], name='idx_support_ticket_messages_thread_sender_created')

    db.stock.create_index([('category', ASCENDING)], name='idx_stock_category')

    print('Store schema bootstrap completed successfully.')


if __name__ == '__main__':
    bootstrap()


