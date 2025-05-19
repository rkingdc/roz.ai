import logging
from flask import Blueprint, request, jsonify
from app import database as db_ops # Use alias for clarity
from datetime import datetime

logger = logging.getLogger(__name__)
bp = Blueprint('todo', __name__, url_prefix='/api/todos')

VALID_TODO_FIELDS = ['name', 'details', 'category', 'priority', 'status', 'due_date']
VALID_SORT_FIELDS = ['name', 'category', 'priority', 'status', 'due_date', 'created_at', 'updated_at']
VALID_STATUS_VALUES = ['pending', 'in-progress', 'completed', 'not started', 'paused', 'blocked']
VALID_PRIORITY_VALUES = ['low', 'medium', 'high', 'backlog']

@bp.route('', methods=['POST'])
def create_todo():
    data = request.get_json()
    if not data or not data.get('name'):
        logger.warning("Create TODO failed: Missing required field 'name'.")
        return jsonify({'error': "Missing required field: name"}), 400

    name = data.get('name')
    details = data.get('details')
    category = data.get('category')
    priority = data.get('priority', 'medium').lower()
    status = data.get('status', 'pending').lower()
    due_date_str = data.get('due_date')
    
    if priority not in VALID_PRIORITY_VALUES:
        logger.warning(f"Create TODO failed: Invalid priority value '{priority}'.")
        return jsonify({'error': f"Invalid priority value. Must be one of {VALID_PRIORITY_VALUES}."}), 400
    if status not in VALID_STATUS_VALUES:
        logger.warning(f"Create TODO failed: Invalid status value '{status}'.")
        return jsonify({'error': f"Invalid status value. Must be one of {VALID_STATUS_VALUES}."}), 400

    due_date = None
    if due_date_str:
        try:
            due_date = datetime.strptime(due_date_str, '%Y-%m-%d').date()
        except ValueError:
            logger.warning(f"Create TODO failed: Invalid due_date format '{due_date_str}'.")
            return jsonify({'error': 'Invalid due_date format. Use YYYY-MM-DD.'}), 400

    logger.info(f"Received request to create TODO: Name='{name}', Due='{due_date_str}'")
    
    new_todo_data = db_ops.create_new_todo_item(
        name=name,
        details=details,
        category=category,
        priority=priority,
        status=status,
        due_date=due_date
    )
    
    if new_todo_data:
        logger.info(f"TODO item created successfully with ID: {new_todo_data.get('id')}")
        return jsonify(new_todo_data), 201
    else:
        logger.error("Failed to create TODO item in database.")
        return jsonify({'error': 'Failed to create TODO item'}), 500

@bp.route('', methods=['GET'])
def get_todos():
    sort_by = request.args.get('sort_by', 'due_date').lower()
    sort_order = request.args.get('sort_order', 'asc').lower()

    if sort_by not in VALID_SORT_FIELDS:
        logger.warning(f"Get TODOs: Invalid sort_by parameter '{sort_by}'. Defaulting to 'due_date'.")
        sort_by = 'due_date'
    if sort_order not in ['asc', 'desc']:
        logger.warning(f"Get TODOs: Invalid sort_order parameter '{sort_order}'. Defaulting to 'asc'.")
        sort_order = 'asc'
    
    logger.info(f"Received request to get all TODOs. Sort by: {sort_by}, Order: {sort_order}")
    
    todos = db_ops.get_all_todo_items_from_db(sort_by=sort_by, sort_order=sort_order)
    logger.info(f"Retrieved {len(todos)} TODO items from database.")
    return jsonify(todos), 200

@bp.route('/<int:todo_id>', methods=['GET'])
def get_todo(todo_id):
    logger.info(f"Received request to get TODO item with ID: {todo_id}")
    todo = db_ops.get_todo_item_from_db(todo_id)
    if todo:
        logger.info(f"TODO item with ID: {todo_id} found.")
        return jsonify(todo), 200
    else:
        logger.warning(f"TODO item with ID: {todo_id} not found.")
        return jsonify({'error': 'TODO item not found'}), 404

@bp.route('/<int:todo_id>', methods=['PUT'])
def update_todo(todo_id):
    data = request.get_json()
    if not data:
        logger.warning(f"Update TODO ID {todo_id} failed: No data provided.")
        return jsonify({'error': 'No data provided for update'}), 400

    logger.info(f"Received request to update TODO item ID: {todo_id} with data: {data}")
    
    update_payload = {}
    for key, value in data.items():
        if key not in VALID_TODO_FIELDS:
            logger.warning(f"Update TODO ID {todo_id}: Invalid field '{key}' in request. Ignoring.")
            continue

        if key == 'due_date':
            if value is None:
                update_payload[key] = None
            else:
                try:
                    update_payload[key] = datetime.strptime(str(value), '%Y-%m-%d').date()
                except (ValueError, TypeError):
                    logger.error(f"Update TODO ID {todo_id} failed: Invalid due_date format '{value}'.")
                    return jsonify({'error': 'Invalid due_date format. Use YYYY-MM-DD or null.'}), 400
        elif key == 'priority':
            priority_val = str(value).lower()
            if priority_val not in VALID_PRIORITY_VALUES:
                logger.warning(f"Update TODO ID {todo_id} failed: Invalid priority value '{priority_val}'.")
                return jsonify({'error': f"Invalid priority value. Must be one of {VALID_PRIORITY_VALUES}."}), 400
            update_payload[key] = priority_val
        elif key == 'status':
            status_val = str(value).lower()
            if status_val not in VALID_STATUS_VALUES:
                logger.warning(f"Update TODO ID {todo_id} failed: Invalid status value '{status_val}'.")
                return jsonify({'error': f"Invalid status value. Must be one of {VALID_STATUS_VALUES}."}), 400
            update_payload[key] = status_val
        else:
            update_payload[key] = value
            
    if not update_payload:
         logger.warning(f"Update TODO ID {todo_id} failed: No valid fields provided for update.")
         return jsonify({'error': 'No valid fields provided for update or all fields were invalid.'}), 400

    updated_todo_data = db_ops.update_todo_item_in_db(todo_id, update_payload)
    
    if updated_todo_data:
        logger.info(f"TODO item ID: {todo_id} updated successfully.")
        return jsonify(updated_todo_data), 200
    else: # Could be not found or DB error during update
        # Check if it was not found vs. other error
        if db_ops.get_todo_item_from_db(todo_id) is None:
             logger.warning(f"Update failed: TODO item ID: {todo_id} not found.")
             return jsonify({'error': 'TODO item not found'}), 404
        logger.error(f"Failed to update TODO item ID: {todo_id} in database (possible commit error).")
        return jsonify({'error': 'Failed to update TODO item'}), 500

@bp.route('/<int:todo_id>', methods=['DELETE'])
def delete_todo(todo_id):
    logger.info(f"Received request to delete TODO item ID: {todo_id}")
    success = db_ops.delete_todo_item_from_db(todo_id)
    if success:
        logger.info(f"TODO item ID: {todo_id} deleted successfully.")
        return jsonify({'message': 'TODO item deleted successfully'}), 200
    else:
        if db_ops.get_todo_item_from_db(todo_id) is None: # Check if it was not found
            logger.warning(f"Delete failed: TODO item ID: {todo_id} not found.")
            return jsonify({'error': 'TODO item not found'}), 404
        logger.error(f"Failed to delete TODO item ID: {todo_id} from database (possible commit error).")
        return jsonify({'error': 'Failed to delete TODO item'}), 500
