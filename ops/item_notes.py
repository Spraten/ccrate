"""Journaled standalone notes stored as native Homebox maintenance entries."""
import hashlib
from datetime import datetime, timezone

from ledger import Conflict, uuid

MAX_NOTE_CHARS = 1000
MAX_DESCRIPTION_BYTES = 2500


def marker(job_id):
    return '[Kiosk note '+uuid(job_id)+']'


def _text(value):
    if not isinstance(value, str) or not value.strip() or len(value) > MAX_NOTE_CHARS:
        raise ValueError('Item note is required and must be at most 1000 characters')
    try:
        value.encode('utf-8')
    except UnicodeEncodeError:
        raise ValueError('Item note contains invalid Unicode') from None
    return value


def _author(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 255:
        raise ValueError('A trusted note author name is required')
    return value.strip()


def _description(note, job_id):
    controlled_marker = marker(job_id)
    description = note+'\n\n'+controlled_marker
    if len(description.encode('utf-8')) > MAX_DESCRIPTION_BYTES:
        raise ValueError('Item note exceeds the native 2500-byte description limit')
    return controlled_marker, description


def _verified_metadata(value, job_id):
    fields = {'maintenance_id', 'entity_id', 'actor_id', 'author_name', 'content_sha256', 'marker'}
    if not isinstance(value, dict) or set(value) != fields:
        raise Conflict('Verified item note metadata is incomplete; inspect Recovery')
    try:
        metadata = dict(value, maintenance_id=uuid(value['maintenance_id']),
                        entity_id=uuid(value['entity_id']), actor_id=uuid(value['actor_id']),
                        author_name=_author(value['author_name']))
    except (ValueError, TypeError):
        raise Conflict('Verified item note metadata is invalid; inspect Recovery') from None
    digest = metadata['content_sha256']
    if (not isinstance(digest, str) or len(digest) != 64
            or any(char not in '0123456789abcdef' for char in digest)
            or metadata['marker'] != marker(job_id)):
        raise Conflict('Verified item note metadata is invalid; inspect Recovery')
    return metadata


def _first_verified_metadata(jobs, group, job_id):
    rows = [event['detail'] for event in jobs.events(group, job_id) if event['kind'] == 'note_verified']
    if not rows:
        return None
    first = _verified_metadata(rows[0], job_id)
    if any(row != rows[0] for row in rows[1:]):
        raise Conflict('Verified item note history is contradictory; inspect Recovery')
    return first


def _entry_data(job_id, job):
    payload, context = job.get('payload') or {}, job.get('context') or {}
    note = _text(payload.get('note'))
    entity_id = uuid(payload.get('entity_id'))
    if context.get('entity_id') != entity_id:
        raise Conflict('Saved item note does not match its selected equipment')
    controlled_marker, description = _description(note, job_id)
    return entity_id, note, controlled_marker, description, {
        'name': 'Item note',
        'description': description,
        'completedDate': context.get('completed_date'),
        'scheduledDate': '',
        'cost': '0',
    }


def _entity(client, entity_id):
    entity = client.entity(entity_id)
    if entity.get('id') != entity_id:
        raise Conflict('C-Crate returned a different equipment record')
    if entity.get('archived') or (entity.get('entityType') or {}).get('isLocation'):
        raise ValueError('Choose active, individually tracked equipment')
    return entity


def _maintenance(client, entity_id):
    rows = client.call('/api/v1/entities/'+entity_id+'/maintenance')
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise Conflict('Native maintenance records could not be verified')
    return rows


def _references(rows, controlled_marker):
    return [row for row in rows if controlled_marker in str(row.get('description') or '')]


def _verify_entry(client, jobs, group, job_id, job=None):
    job = job or jobs.detail(group, job_id)
    entity_id, note, controlled_marker, description, expected = _entry_data(job_id, job)
    original_metadata = _first_verified_metadata(jobs, group, job_id)
    if not (job.get('context') or {}).get('note_creation_started'):
        raise Conflict('No durable note creation start exists; a marker alone cannot confirm this note')
    _entity(client, entity_id)
    references = _references(_maintenance(client, entity_id), controlled_marker)
    if len(references) != 1:
        raise Conflict('Item note reference is missing or duplicated; inspect C-Crate before resolving')
    entry = references[0]
    if (entry.get('name') != expected['name'] or entry.get('description') != description
            or entry.get('completedDate') != expected['completedDate']
            or entry.get('scheduledDate') != '' or str(entry.get('cost')) != '0'):
        raise Conflict('Native item note changed or does not match its journal; inspect C-Crate')
    try:
        maintenance_id = uuid(entry.get('id'))
    except (ValueError, TypeError):
        raise Conflict('Native item note has no valid maintenance ID; inspect C-Crate') from None
    metadata = {
        'maintenance_id': maintenance_id,
        'entity_id': entity_id,
        'actor_id': uuid(job['actor_id']),
        'author_name': _author((job.get('context') or {}).get('author_name')),
        'content_sha256': hashlib.sha256(note.encode('utf-8')).hexdigest(),
        'marker': controlled_marker,
    }
    if original_metadata is not None:
        if metadata != original_metadata:
            raise Conflict('Native item note no longer matches its first verified maintenance record')
    else:
        jobs.record(group, job_id, 'note_verified', metadata)
    jobs.complete(group, job_id)
    return {'id': job_id, 'status': 'completed', 'entity_id': entity_id, 'maintenance_id': maintenance_id}


def _completed_result(jobs, group, job):
    metadata = _first_verified_metadata(jobs, group, job['id'])
    if (metadata is None or metadata['entity_id'] != job['result_id']
            or metadata['actor_id'] != job['actor_id']):
        raise Conflict('Completed item note has no consistent verified native reference')
    return {'id': job['id'], 'status': 'completed', 'entity_id': job['result_id'],
            'maintenance_id': metadata['maintenance_id']}


def submit_note(client, jobs, group, actor, key, data, author_name):
    """Create one native maintenance note; never retry a possibly committed POST."""
    if not isinstance(data, dict) or set(data) != {'entity_id', 'note'}:
        raise ValueError('Item note request must contain only equipment and note')
    entity_id, note = uuid(data.get('entity_id')), _text(data.get('note'))
    payload = {'entity_id': entity_id, 'note': note}
    job = jobs.existing(group, actor, 'add_note', key, payload)
    if job and job['status'] == 'completed':
        return _completed_result(jobs, group, job)
    if job and job['status'] != 'prepared':
        raise Conflict('Item note needs Recovery; do not submit another copy')
    if job is None:
        author_name = _author(author_name)
        # The UUID text has a fixed 36-byte form, so validate the full description
        # bound before this request can create either a job row or event.
        _description(note, '00000000-0000-0000-0000-000000000000')
        _entity(client, entity_id)
        context = {'entity_id': entity_id, 'author_name': author_name,
                   'completed_date': datetime.now(timezone.utc).date().isoformat()}
        job = jobs.prepare(group, actor, 'add_note', key, payload, context=context)
    if job['status'] == 'completed':
        return _completed_result(jobs, group, job)
    if job['status'] != 'prepared':
        raise Conflict('Item note needs Recovery; do not submit another copy')

    try:
        entity_id, note, controlled_marker, description, entry = _entry_data(job['id'], job)
        _entity(client, entity_id)
        # A marker found before this journal starts its one POST is a collision, not proof.
        if _references(_maintenance(client, entity_id), controlled_marker):
            raise Conflict('A matching note marker already exists without this journaled create; inspect C-Crate')
        jobs.start_note(group, job['id'], entity_id)
        # This is the sole create call. Any error after it remains review-only.
        client.call('/api/v1/entities/'+entity_id+'/maintenance', 'POST', entry)
        return _verify_entry(client, jobs, group, job['id'])
    except Exception as error:
        current = jobs.detail(group, job['id'])
        if current['status'] == 'prepared':
            jobs.cancel(group, job['id'])
            raise
        if current['status'] == 'sent':
            jobs.review(group, job['id'], 'Item note create requires native verification')
        if current['status'] in ('sent', 'review'):
            raise Conflict('Item note outcome needs Recovery; do not submit another copy') from None
        raise error


def recover_note(client, jobs, group, job_id, outcome):
    job = jobs.detail(group, job_id)
    if job['kind'] != 'add_note':
        raise ValueError('Not an item note')
    if job['status'] == 'completed':
        return _completed_result(jobs, group, job)
    if outcome == 'cancel':
        if job['status'] != 'prepared' or (job.get('context') or {}).get('note_creation_started'):
            raise Conflict('A started note cannot be cancelled; inspect its native maintenance entry')
        entity_id = uuid((job.get('payload') or {}).get('entity_id'))
        controlled_marker = marker(job_id)
        _entity(client, entity_id)
        if _references(_maintenance(client, entity_id), controlled_marker):
            jobs.review(group, job_id, 'A note marker exists without a started journal create')
            raise Conflict('A native note marker exists; inspect C-Crate before resolving')
        jobs.cancel(group, job_id)
        return {'id': job_id, 'status': 'cancelled', 'entity_id': entity_id}
    if outcome != 'complete':
        raise ValueError('Choose complete or cancel')
    if job['status'] not in ('sent', 'review') or not (job.get('context') or {}).get('note_creation_started'):
        raise Conflict('No started native note can be confirmed; inspect the request before resolving')
    try:
        return _verify_entry(client, jobs, group, job_id, job)
    except Exception:
        current = jobs.detail(group, job_id)
        if current['status'] == 'sent':
            jobs.review(group, job_id, 'Item note recovery could not verify the native record')
        raise


def project_note_history(row, client, jobs, group, requested_entity):
    """Attach current native text only through its journal-verified maintenance UUID."""
    if row.get('action') != 'add_note' or not requested_entity or requested_entity not in row.get('assets', []):
        return row
    try:
        metadata = _first_verified_metadata(jobs, group, row['id'])
    except Conflict:
        metadata = None
    if metadata is None:
        row['note_state'] = row.get('status') if row.get('status') != 'completed' else 'unavailable'
        return row
    if (row.get('status') != 'completed' or metadata.get('entity_id') != requested_entity
            or metadata.get('actor_id') != row.get('actor_id')):
        row['note_state'] = row.get('status', 'unavailable')
        return row
    maintenance_id = metadata['maintenance_id']
    row.update({'note_author_id': metadata['actor_id'],
                'note_author': metadata['author_name'],
                'note_maintenance_id': maintenance_id})
    try:
        entries = _maintenance(client, requested_entity)
        found = [entry for entry in entries if entry.get('id') == maintenance_id]
    except (OSError, ValueError, KeyError, TypeError):
        found = []
    if len(found) != 1:
        row['note_state'] = 'unavailable'
        return row
    description = found[0].get('description')
    if not isinstance(description, str):
        row['note_state'] = 'unavailable'
        return row
    suffix = '\n\n'+str(metadata.get('marker') or '')
    marker_preserved = bool(metadata.get('marker')) and description.endswith(suffix)
    current_text = description[:-len(suffix)] if marker_preserved else description
    current = (marker_preserved and hashlib.sha256(current_text.encode('utf-8')).hexdigest()
               == metadata.get('content_sha256'))
    row.update({'note_text': current_text,
                'note_state': 'current' if current else 'edited',
                'note_current_text_attribution': 'journaled' if current else 'unknown',
                'note_maintenance_id': maintenance_id})
    return row
